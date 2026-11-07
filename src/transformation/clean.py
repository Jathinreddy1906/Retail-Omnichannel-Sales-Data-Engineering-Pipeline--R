from datetime import datetime, timedelta, timezone

import pandas as pd

PRIMARY_KEYS = {
    "customers": ("customer_id", "updated_at", "ingestion_timestamp"),
    "products": ("product_id", "updated_at", "ingestion_timestamp"),
    "orders": ("order_id", "updated_at", "ingestion_timestamp"),
}


def clean_batch(
    datasets: dict[str, pd.DataFrame],
    as_of: datetime | None = None,
    late_after_days: int = 1,
) -> tuple[dict[str, pd.DataFrame], dict[str, dict[str, int]]]:
    """Deduplicate by business key and flag sales older than the lateness window."""
    if late_after_days < 0:
        raise ValueError("late_after_days must be zero or greater")

    as_of = as_of or datetime.now(timezone.utc)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    cutoff = pd.Timestamp(as_of - timedelta(days=late_after_days))

    cleaned: dict[str, pd.DataFrame] = {}
    summary: dict[str, dict[str, int]] = {}
    for name, data in datasets.items():
        if name not in PRIMARY_KEYS:
            raise ValueError(f"Unknown dataset: {name}")

        key, *sort_columns = PRIMARY_KEYS[name]
        ordered = data.sort_values(sort_columns, kind="mergesort")
        deduplicated = ordered.drop_duplicates(subset=key, keep="last").copy()
        summary[name] = {
            "duplicates_removed": len(data) - len(deduplicated),
            "clean": len(deduplicated),
            "late_arriving": 0,
        }

        if name == "orders":
            deduplicated["late_arriving"] = deduplicated["order_date"] < cutoff
            summary[name]["late_arriving"] = int(
                deduplicated["late_arriving"].sum()
            )

        cleaned[name] = deduplicated.reset_index(drop=True)

    return cleaned, summary
