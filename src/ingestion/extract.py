import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from sqlalchemy import create_engine, text

from config.settings import (
    INGESTED_DATA_DIR,
    POSTGRES_SOURCE_QUERY,
    POSTGRES_SOURCE_URL,
    RAW_DATA_DIR,
    SALES_API_TIMEOUT_SECONDS,
    SALES_API_URL,
)


def _add_ingestion_metadata(data: pd.DataFrame, source: str) -> pd.DataFrame:
    result = data.copy()
    result["source"] = source
    result["ingestion_timestamp"] = datetime.now(timezone.utc).isoformat()
    return result


def read_csv_source(file_name: str, source_name: str) -> pd.DataFrame:
    """Read a project CSV source and label its origin and ingestion time."""
    data = pd.read_csv(RAW_DATA_DIR / file_name)
    return _add_ingestion_metadata(data, source_name)


def _records_from_api_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict) and isinstance(payload.get("sales"), list):
        records = payload["sales"]
    else:
        raise ValueError("Sales API response must be a list or contain a 'sales' list.")

    if not all(isinstance(record, dict) for record in records):
        raise ValueError("Each sales API record must be a JSON object.")
    return records


def read_api_sales(
    api_url: str | None = SALES_API_URL,
    fixture_path: Path = RAW_DATA_DIR / "api_sales.json",
) -> pd.DataFrame:
    """Fetch API sales or read the bundled JSON fixture when no URL is configured."""
    if api_url:
        response = requests.get(api_url, timeout=SALES_API_TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.json()
        source = "rest_api"
    else:
        with fixture_path.open(encoding="utf-8") as fixture:
            payload = json.load(fixture)
        source = "api_json_fixture"

    records = _records_from_api_payload(payload)
    return _add_ingestion_metadata(pd.DataFrame.from_records(records), source)


def read_postgres_source(
    database_url: str,
    query: str = POSTGRES_SOURCE_QUERY,
) -> pd.DataFrame:
    """Run the configured source query and return rows with ingestion metadata."""
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            data = pd.read_sql_query(text(query), connection)
    finally:
        engine.dispose()
    return _add_ingestion_metadata(data, "postgresql")


def run_ingestion() -> dict[str, int]:
    """Extract configured sources and write the raw ingested CSV snapshots."""
    customers = read_csv_source("customers.csv", "csv:customers")
    products = read_csv_source("products.csv", "csv:products")
    order_sources = [
        read_csv_source("orders.csv", "csv:orders"),
        read_api_sales(),
    ]

    if POSTGRES_SOURCE_URL:
        order_sources.append(
            read_postgres_source(POSTGRES_SOURCE_URL, POSTGRES_SOURCE_QUERY)
        )

    orders = pd.concat(order_sources, ignore_index=True, sort=False)
    INGESTED_DATA_DIR.mkdir(parents=True, exist_ok=True)

    outputs = {
        "customers": customers,
        "products": products,
        "orders": orders,
    }
    counts: dict[str, int] = {}
    for name, data in outputs.items():
        data.to_csv(INGESTED_DATA_DIR / f"{name}.csv", index=False)
        counts[name] = len(data)

    return counts
