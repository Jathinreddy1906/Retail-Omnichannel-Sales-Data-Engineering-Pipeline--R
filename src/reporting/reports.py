import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from config.settings import (
    CLEAN_DATA_DIR,
    CURATED_DATA_DIR,
    INGESTED_DATA_DIR,
    QUARANTINE_DATA_DIR,
    REPORT_DIR,
)

SOURCE_TARGET_MAPPING = [
    {
        "source": "customers.csv",
        "source_field": "customer_id, first_name, last_name, email, phone, city, state, updated_at",
        "target_layer": "clean/customers.csv",
        "target_field": "matching customer fields",
        "rule": "Required fields validated; email normalized to lowercase; latest customer_id retained.",
    },
    {
        "source": "products.csv",
        "source_field": "product_id, sku, product_name, category, unit_price, updated_at",
        "target_layer": "clean/products.csv",
        "target_field": "matching product fields",
        "rule": "Required fields and non-negative price validated; latest product_id retained.",
    },
    {
        "source": "orders.csv and API sales JSON",
        "source_field": "order_id, customer_id, product_id, order_date, quantity, unit_price, discount, order_status, updated_at",
        "target_layer": "clean/orders.csv",
        "target_field": "matching order fields plus late_arriving",
        "rule": "Schema and sales amounts validated; latest order_id retained; late orders flagged.",
    },
    {
        "source": "clean/customers.csv",
        "source_field": "customer_id, customer attributes",
        "target_layer": "curated/customers.csv",
        "target_field": "customer dimension attributes",
        "rule": "Passed into curated layer for sales enrichment and future SCD Type 2 loading.",
    },
    {
        "source": "clean/products.csv",
        "source_field": "product_id, sku, product_name, category",
        "target_layer": "curated/products.csv",
        "target_field": "product dimension attributes",
        "rule": "Passed into curated layer for sales enrichment.",
    },
    {
        "source": "clean/orders.csv",
        "source_field": "order_id, customer_id, product_id, quantities, prices, order_date",
        "target_layer": "curated/sales.csv",
        "target_field": "sales line, customer/product attributes, gross_sales, net_sales, sales_date",
        "rule": "Many-to-one dimension joins; gross_sales = quantity * unit_price; net_sales = gross_sales - discount.",
    },
    {
        "source": "curated customer/product/sales CSV snapshots",
        "source_field": "curated entity fields",
        "target_layer": "PostgreSQL retail_dw",
        "target_field": "dim_customer, dim_product, dim_date, fact_sales",
        "rule": "Incremental upserts and customer SCD Type 2 when WAREHOUSE_DATABASE_URL is configured.",
    },
]


def _csv_row_count(path: Path) -> int:
    if not path.exists():
        return 0
    return len(pd.read_csv(path))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def write_pipeline_reports(
    run_id: str,
    started_at: datetime,
    status: str,
    stage_metrics: dict[str, dict[str, Any]],
    error: str | None = None,
    report_dir: Path = REPORT_DIR,
) -> dict[str, Path]:
    """Write execution, data-quality, reconciliation, and mapping reports."""
    report_dir.mkdir(parents=True, exist_ok=True)
    completed_at = datetime.now(timezone.utc)
    quarantine_path = QUARANTINE_DATA_DIR / "invalid_records.csv"
    quarantine_count = _csv_row_count(quarantine_path)

    quality = {
        "run_id": run_id,
        "generated_at": completed_at.isoformat(),
        "status": status,
        "datasets": {
            name: {
                **metrics,
                "quality_status": (
                    "passed" if metrics.get("quarantined", 0) == 0 else "warnings"
                ),
            }
            for name, metrics in (
                stage_metrics.get("validation", {}).get("datasets", {}).items()
            )
        },
        "total_quarantined_rows": quarantine_count,
        "quarantine_report": str(quarantine_path),
    }

    reconciliation_rows: list[dict[str, Any]] = []
    for name in ("customers", "products", "orders"):
        input_count = _csv_row_count(INGESTED_DATA_DIR / f"{name}.csv")
        clean_count = _csv_row_count(CLEAN_DATA_DIR / f"{name}.csv")
        validation = (
            stage_metrics.get("validation", {})
            .get("datasets", {})
            .get(name, {})
        )
        curated_entity = "sales" if name == "orders" else name
        curated_count = _csv_row_count(
            CURATED_DATA_DIR / f"{curated_entity}.csv"
        )
        quarantined = validation.get("quarantined", 0)
        duplicates_removed = validation.get("duplicate_records_removed", 0)
        reconciliation_rows.append(
            {
                "dataset": name,
                "ingested_count": input_count,
                "quarantined_count": quarantined,
                "duplicate_records_removed": duplicates_removed,
                "clean_count": clean_count,
                "curated_count": curated_count,
                "ingested_minus_quarantined": input_count - quarantined,
                "validated_minus_duplicates": (
                    validation.get("valid", 0) - duplicates_removed
                ),
                "ingested_to_clean_balanced": (
                    input_count - quarantined - duplicates_removed == clean_count
                ),
            }
        )

    reconciliation_path = report_dir / "reconciliation_report.csv"
    with reconciliation_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=reconciliation_rows[0].keys())
        writer.writeheader()
        writer.writerows(reconciliation_rows)

    mapping_path = report_dir / "source_to_target_mapping.csv"
    with mapping_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=SOURCE_TARGET_MAPPING[0].keys())
        writer.writeheader()
        writer.writerows(SOURCE_TARGET_MAPPING)

    execution = {
        "run_id": run_id,
        "status": status,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "duration_seconds": round((completed_at - started_at).total_seconds(), 3),
        "stages": stage_metrics,
        "error": error,
    }
    execution_path = report_dir / "pipeline_execution_report.json"
    _write_json(execution_path, execution)

    quality_path = report_dir / "data_quality_report.json"
    _write_json(quality_path, quality)

    return {
        "execution": execution_path,
        "quality": quality_path,
        "reconciliation": reconciliation_path,
        "mapping": mapping_path,
    }
