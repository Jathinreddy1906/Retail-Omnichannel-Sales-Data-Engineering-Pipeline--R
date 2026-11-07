import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
INGESTED_DATA_DIR = RAW_DATA_DIR / "ingested"
CLEAN_DATA_DIR = PROJECT_ROOT / "data" / "clean"
CURATED_DATA_DIR = PROJECT_ROOT / "data" / "curated"
QUARANTINE_DATA_DIR = PROJECT_ROOT / "data" / "quarantine"
LOG_DIR = PROJECT_ROOT / "logs"
REPORT_DIR = PROJECT_ROOT / "reports"

load_dotenv(PROJECT_ROOT / ".env")

SALES_API_URL = os.getenv("SALES_API_URL") or None
SALES_API_TIMEOUT_SECONDS = int(os.getenv("SALES_API_TIMEOUT_SECONDS", "30"))
POSTGRES_SOURCE_URL = os.getenv("POSTGRES_SOURCE_URL") or None
POSTGRES_SOURCE_QUERY = os.getenv(
    "POSTGRES_SOURCE_QUERY", "SELECT * FROM orders"
)
WAREHOUSE_DATABASE_URL = os.getenv("WAREHOUSE_DATABASE_URL") or None
