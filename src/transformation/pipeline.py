import logging

import pandas as pd

from config.settings import CLEAN_DATA_DIR, INGESTED_DATA_DIR, QUARANTINE_DATA_DIR
from src.transformation.clean import clean_batch
from src.validation.validate import validate_batch

logger = logging.getLogger(__name__)


def process_ingested_data() -> dict[str, dict[str, int]]:
    """Validate raw snapshots, quarantine invalid rows, and write clean snapshots."""
    datasets = {
        name: pd.read_csv(INGESTED_DATA_DIR / f"{name}.csv")
        for name in ("customers", "products", "orders")
    }
    valid, quarantine, validation_summary = validate_batch(datasets)
    cleaned, cleaning_summary = clean_batch(valid)

    CLEAN_DATA_DIR.mkdir(parents=True, exist_ok=True)
    QUARANTINE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name, data in cleaned.items():
        data.to_csv(CLEAN_DATA_DIR / f"{name}.csv", index=False)
    quarantine.to_csv(QUARANTINE_DATA_DIR / "invalid_records.csv", index=False)

    for name in datasets:
        logger.info(
            "%s processing: input=%d valid=%d quarantined=%d duplicates_removed=%d "
            "clean=%d late_arriving=%d",
            name,
            validation_summary[name]["input"],
            validation_summary[name]["valid"],
            validation_summary[name]["quarantined"],
            cleaning_summary[name]["duplicates_removed"],
            cleaning_summary[name]["clean"],
            cleaning_summary[name]["late_arriving"],
        )

    return {
        name: {
            **validation_summary[name],
            **cleaning_summary[name],
            "duplicate_records_removed": cleaning_summary[name]["duplicates_removed"],
        }
        for name in datasets
    }
