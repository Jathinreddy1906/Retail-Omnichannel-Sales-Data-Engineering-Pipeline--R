import logging
from typing import Any

import pandas as pd
from sqlalchemy import create_engine, text

from config.settings import CURATED_DATA_DIR, WAREHOUSE_DATABASE_URL

logger = logging.getLogger(__name__)

WATERMARK_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS retail_dw.pipeline_watermark (
    entity_name TEXT PRIMARY KEY,
    last_updated_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

WATERMARKS = {
    "customers": ("customers", "updated_at"),
    "products": ("products", "updated_at"),
    "sales": ("sales", "updated_at"),
}


def rows_after_watermark(
    data: pd.DataFrame,
    watermark: Any,
    timestamp_column: str = "updated_at",
) -> pd.DataFrame:
    """Return records newer than a stored UTC watermark."""
    if timestamp_column not in data.columns:
        raise ValueError(f"Missing incremental timestamp column: {timestamp_column}")
    timestamps = pd.to_datetime(data[timestamp_column], errors="coerce", utc=True)
    if timestamps.isna().any():
        raise ValueError(f"{timestamp_column} contains missing or invalid timestamps")
    if watermark is None:
        return data.copy()
    watermark_timestamp = pd.to_datetime(watermark, utc=True)
    # Re-read the watermark boundary to avoid losing records with tied timestamps.
    # Database upserts make this overlap safe to replay.
    return data.loc[timestamps >= watermark_timestamp].copy()


def _max_timestamp(data: pd.DataFrame, column: str) -> pd.Timestamp | None:
    if data.empty:
        return None
    timestamps = pd.to_datetime(data[column], errors="coerce", utc=True)
    if timestamps.isna().any():
        raise ValueError(f"{column} contains missing or invalid timestamps")
    return timestamps.max()


def _date_key(value: Any) -> int:
    parsed = pd.Timestamp(value).date()
    return parsed.year * 10000 + parsed.month * 100 + parsed.day


def _load_curated_snapshots() -> dict[str, pd.DataFrame]:
    datasets = {
        name: pd.read_csv(CURATED_DATA_DIR / f"{name}.csv")
        for name in ("customers", "products", "sales")
    }
    required = {
        "customers": {"customer_id", "updated_at"},
        "products": {"product_id", "updated_at"},
        "sales": {
            "order_id",
            "customer_id",
            "product_id",
            "order_date",
            "quantity",
            "unit_price",
            "discount",
            "order_status",
            "late_arriving",
            "source",
            "updated_at",
        },
    }
    for name, columns in required.items():
        missing = columns - set(datasets[name].columns)
        if missing:
            raise ValueError(
                f"Curated {name} snapshot is missing columns: "
                f"{', '.join(sorted(missing))}"
            )
    return datasets


def _advance_watermark(connection: Any, entity: str, watermark: pd.Timestamp) -> None:
    connection.execute(
        text(
            """
            INSERT INTO retail_dw.pipeline_watermark (entity_name, last_updated_at)
            VALUES (:entity_name, :last_updated_at)
            ON CONFLICT (entity_name) DO UPDATE
            SET last_updated_at = GREATEST(
                    retail_dw.pipeline_watermark.last_updated_at,
                    EXCLUDED.last_updated_at
                ),
                updated_at = CURRENT_TIMESTAMP
            """
        ),
        {
            "entity_name": entity,
            "last_updated_at": watermark.to_pydatetime(),
        },
    )


def _get_watermarks(connection: Any) -> dict[str, pd.Timestamp | None]:
    rows = connection.execute(
        text(
            "SELECT entity_name, last_updated_at "
            "FROM retail_dw.pipeline_watermark"
        )
    )
    stored = {row.entity_name: row.last_updated_at for row in rows}
    return {
        name: pd.Timestamp(stored[name])
        if name in stored
        else None
        for name in WATERMARKS
    }


def _write_temp_frame(
    connection: Any,
    data: pd.DataFrame,
    table_name: str,
) -> None:
    schemas = {
        "stage_products": """
            product_id TEXT NOT NULL,
            sku TEXT NOT NULL,
            product_name TEXT NOT NULL,
            category TEXT NOT NULL
        """,
        "stage_sales": """
            order_id TEXT NOT NULL,
            customer_id TEXT NOT NULL,
            product_id TEXT NOT NULL,
            order_date TIMESTAMPTZ NOT NULL,
            sales_date DATE NOT NULL,
            quantity NUMERIC NOT NULL,
            unit_price NUMERIC NOT NULL,
            discount NUMERIC NOT NULL,
            gross_sales NUMERIC NOT NULL,
            net_sales NUMERIC NOT NULL,
            order_status TEXT NOT NULL,
            late_arriving BOOLEAN NOT NULL,
            source TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        """,
    }
    if table_name not in schemas:
        raise ValueError(f"Unknown temporary staging table: {table_name}")

    connection.exec_driver_sql(
        f"CREATE TEMPORARY TABLE {table_name} ({schemas[table_name]}) "
        "ON COMMIT DROP"
    )
    stage_data = data
    if table_name == "stage_sales":
        stage_data = data[
            [
                "order_id",
                "customer_id",
                "product_id",
                "order_date",
                "sales_date",
                "quantity",
                "unit_price",
                "discount",
                "gross_sales",
                "net_sales",
                "order_status",
                "late_arriving",
                "source",
                "updated_at",
            ]
        ].copy()
        stage_data["order_date"] = pd.to_datetime(
            stage_data["order_date"], errors="raise", utc=True
        )
        stage_data["updated_at"] = pd.to_datetime(
            stage_data["updated_at"], errors="raise", utc=True
        )
        stage_data["sales_date"] = pd.to_datetime(
            stage_data["sales_date"], errors="raise"
        ).dt.date
    stage_data.to_sql(
        table_name,
        connection,
        if_exists="append",
        index=False,
        method="multi",
    )


def _load_customer_changes(connection: Any, customers: pd.DataFrame) -> None:
    if customers.empty:
        return
    stage = customers[
        [
            "customer_id",
            "first_name",
            "last_name",
            "email",
            "phone",
            "city",
            "state",
            "updated_at",
        ]
    ].rename(columns={"updated_at": "effective_start"})
    connection.execute(text("DELETE FROM retail_dw.stg_customer"))
    stage.to_sql(
        "stg_customer",
        connection,
        schema="retail_dw",
        if_exists="append",
        index=False,
        method="multi",
    )
    connection.execute(text("CALL retail_dw.apply_customer_scd2()"))
    connection.execute(text("DELETE FROM retail_dw.stg_customer"))


def _upsert_products(connection: Any) -> None:
    connection.execute(
        text(
            """
            INSERT INTO retail_dw.dim_product (
                product_id, sku, product_name, category
            )
            SELECT product_id, sku, product_name, category
            FROM stage_products
            ON CONFLICT (product_id) DO UPDATE
            SET sku = EXCLUDED.sku,
                product_name = EXCLUDED.product_name,
                category = EXCLUDED.category
            WHERE retail_dw.dim_product.sku IS DISTINCT FROM EXCLUDED.sku
               OR retail_dw.dim_product.product_name
                    IS DISTINCT FROM EXCLUDED.product_name
               OR retail_dw.dim_product.category
                    IS DISTINCT FROM EXCLUDED.category
            """
        )
    )


def _upsert_dates(connection: Any) -> None:
    connection.execute(
        text(
            """
            INSERT INTO retail_dw.dim_date (
                date_key, full_date, calendar_year, quarter, month_number,
                month_name, day_of_month, day_of_week, day_name, is_weekend
            )
            SELECT DISTINCT
                EXTRACT(YEAR FROM sales_date::date)::INTEGER * 10000
                    + EXTRACT(MONTH FROM sales_date::date)::INTEGER * 100
                    + EXTRACT(DAY FROM sales_date::date)::INTEGER,
                sales_date::date,
                EXTRACT(YEAR FROM sales_date::date)::SMALLINT,
                EXTRACT(QUARTER FROM sales_date::date)::SMALLINT,
                EXTRACT(MONTH FROM sales_date::date)::SMALLINT,
                to_char(sales_date::date, 'FMMonth'),
                EXTRACT(DAY FROM sales_date::date)::SMALLINT,
                EXTRACT(ISODOW FROM sales_date::date)::SMALLINT,
                to_char(sales_date::date, 'FMDay'),
                EXTRACT(ISODOW FROM sales_date::date) IN (6, 7)
            FROM stage_sales
            ON CONFLICT (date_key) DO NOTHING
            """
        )
    )


def _upsert_sales(connection: Any) -> int:
    unmatched = connection.execute(
        text(
            """
            SELECT COUNT(*)
            FROM stage_sales AS sales
            WHERE NOT EXISTS (
                SELECT 1
                FROM retail_dw.dim_customer AS customer
                WHERE customer.customer_id = sales.customer_id
                  AND customer.effective_start <= sales.order_date::timestamptz
                  AND (
                      customer.effective_end IS NULL
                      OR sales.order_date::timestamptz < customer.effective_end
                  )
            )
               OR NOT EXISTS (
                SELECT 1
                FROM retail_dw.dim_product AS product
                WHERE product.product_id = sales.product_id
            )
            """
        )
    ).scalar_one()
    if unmatched:
        raise ValueError(
            f"{unmatched} sales rows do not match a customer history version "
            "or product dimension"
        )

    result = connection.execute(
        text(
            """
            INSERT INTO retail_dw.fact_sales (
                order_id, customer_key, product_key, date_key, quantity,
                unit_price, discount, gross_sales, net_sales, order_status,
                late_arriving, source
            )
            SELECT
                sales.order_id,
                customer.customer_key,
                product.product_key,
                EXTRACT(YEAR FROM sales.sales_date::date)::INTEGER * 10000
                    + EXTRACT(MONTH FROM sales.sales_date::date)::INTEGER * 100
                    + EXTRACT(DAY FROM sales.sales_date::date)::INTEGER,
                sales.quantity::integer,
                sales.unit_price::numeric(12, 2),
                sales.discount::numeric(12, 2),
                sales.gross_sales::numeric(14, 2),
                sales.net_sales::numeric(14, 2),
                sales.order_status,
                sales.late_arriving::boolean,
                sales.source
            FROM stage_sales AS sales
            JOIN retail_dw.dim_customer AS customer
              ON customer.customer_id = sales.customer_id
             AND customer.effective_start <= sales.order_date::timestamptz
             AND (
                 customer.effective_end IS NULL
                 OR sales.order_date::timestamptz < customer.effective_end
             )
            JOIN retail_dw.dim_product AS product
              ON product.product_id = sales.product_id
            ON CONFLICT (order_id) DO UPDATE
            SET customer_key = EXCLUDED.customer_key,
                product_key = EXCLUDED.product_key,
                date_key = EXCLUDED.date_key,
                quantity = EXCLUDED.quantity,
                unit_price = EXCLUDED.unit_price,
                discount = EXCLUDED.discount,
                gross_sales = EXCLUDED.gross_sales,
                net_sales = EXCLUDED.net_sales,
                order_status = EXCLUDED.order_status,
                late_arriving = EXCLUDED.late_arriving,
                source = EXCLUDED.source,
                loaded_at = CURRENT_TIMESTAMP
            WHERE retail_dw.fact_sales.customer_key
                    IS DISTINCT FROM EXCLUDED.customer_key
               OR retail_dw.fact_sales.product_key
                    IS DISTINCT FROM EXCLUDED.product_key
               OR retail_dw.fact_sales.date_key
                    IS DISTINCT FROM EXCLUDED.date_key
               OR retail_dw.fact_sales.quantity
                    IS DISTINCT FROM EXCLUDED.quantity
               OR retail_dw.fact_sales.unit_price
                    IS DISTINCT FROM EXCLUDED.unit_price
               OR retail_dw.fact_sales.discount
                    IS DISTINCT FROM EXCLUDED.discount
               OR retail_dw.fact_sales.gross_sales
                    IS DISTINCT FROM EXCLUDED.gross_sales
               OR retail_dw.fact_sales.net_sales
                    IS DISTINCT FROM EXCLUDED.net_sales
               OR retail_dw.fact_sales.order_status
                    IS DISTINCT FROM EXCLUDED.order_status
               OR retail_dw.fact_sales.late_arriving
                    IS DISTINCT FROM EXCLUDED.late_arriving
               OR retail_dw.fact_sales.source IS DISTINCT FROM EXCLUDED.source
            """
        )
    )
    return result.rowcount


def load_warehouse() -> dict[str, int] | None:
    """Incrementally upsert curated datasets and their watermarks in one transaction."""
    if not WAREHOUSE_DATABASE_URL:
        logger.info(
            "Warehouse load skipped: WAREHOUSE_DATABASE_URL is not configured."
        )
        return None

    datasets = _load_curated_snapshots()
    changes: dict[str, pd.DataFrame] = {}
    high_watermarks: dict[str, pd.Timestamp] = {}
    for entity, (dataset_name, timestamp_column) in WATERMARKS.items():
        full_data = datasets[dataset_name]
        high_watermark = _max_timestamp(full_data, timestamp_column)
        if high_watermark is not None:
            high_watermarks[entity] = high_watermark
        changes[entity] = rows_after_watermark(
            full_data,
            None,
            timestamp_column,
        )

    engine = create_engine(WAREHOUSE_DATABASE_URL)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "SELECT pg_advisory_xact_lock("
                    "hashtext('retail_dw.incremental_loader'))"
                )
            )
            connection.execute(text(WATERMARK_TABLE_SQL))
            stored_watermarks = _get_watermarks(connection)
            for entity, (dataset_name, timestamp_column) in WATERMARKS.items():
                changes[entity] = rows_after_watermark(
                    datasets[dataset_name],
                    stored_watermarks[entity],
                    timestamp_column,
                )

            customer_changes = changes["customers"]
            product_changes = changes["products"]
            sales_changes = changes["sales"]

            _load_customer_changes(connection, customer_changes)

            all_products = datasets["products"]
            _write_temp_frame(
                connection,
                all_products[["product_id", "sku", "product_name", "category"]],
                "stage_products",
            )
            _upsert_products(connection)

            _write_temp_frame(connection, sales_changes, "stage_sales")
            _upsert_dates(connection)
            sales_loaded = _upsert_sales(connection) if not sales_changes.empty else 0

            for entity, watermark in high_watermarks.items():
                _advance_watermark(connection, entity, watermark)

            counts = {
                "customers": len(customer_changes),
                "products": len(product_changes),
                "sales": sales_loaded,
            }
    finally:
        engine.dispose()

    logger.info(
        "Incremental warehouse upsert completed: customers=%d products=%d sales=%d",
        counts["customers"],
        counts["products"],
        counts["sales"],
    )
    return counts
