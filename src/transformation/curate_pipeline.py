import logging

import pandas as pd

from config.settings import CLEAN_DATA_DIR, CURATED_DATA_DIR
from src.transformation.curate import build_curated_datasets

logger = logging.getLogger(__name__)


def build_curated_layer() -> dict[str, int]:
    """Build and persist enriched sales and curated customer/product snapshots."""
    clean = {
        name: pd.read_csv(CLEAN_DATA_DIR / f"{name}.csv")
        for name in ("customers", "products", "orders")
    }
    curated = build_curated_datasets(
        clean["customers"],
        clean["products"],
        clean["orders"],
    )

    CURATED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for name, data in curated.items():
        data.to_csv(CURATED_DATA_DIR / f"{name}.csv", index=False)
        counts[name] = len(data)
        logger.info("Curated %s rows=%d", name, len(data))

    return counts
