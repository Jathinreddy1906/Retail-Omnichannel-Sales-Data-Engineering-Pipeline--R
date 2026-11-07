import re

import pandas as pd

REQUIRED_COLUMNS = {
    "customers": {
        "customer_id",
        "first_name",
        "last_name",
        "email",
        "city",
        "state",
        "updated_at",
        "source",
        "ingestion_timestamp",
    },
    "products": {
        "product_id",
        "sku",
        "product_name",
        "category",
        "unit_price",
        "updated_at",
        "source",
        "ingestion_timestamp",
    },
    "orders": {
        "order_id",
        "customer_id",
        "product_id",
        "order_date",
        "quantity",
        "unit_price",
        "discount",
        "order_status",
        "updated_at",
        "source",
        "ingestion_timestamp",
    },
}

STRING_COLUMNS = {
    "customers": (
        "customer_id",
        "first_name",
        "last_name",
        "email",
        "phone",
        "city",
        "state",
        "source",
    ),
    "products": (
        "product_id",
        "sku",
        "product_name",
        "category",
        "source",
    ),
    "orders": (
        "order_id",
        "customer_id",
        "product_id",
        "order_status",
        "source",
    ),
}

DATETIME_COLUMNS = {
    "customers": ("updated_at", "ingestion_timestamp"),
    "products": ("updated_at", "ingestion_timestamp"),
    "orders": ("order_date", "updated_at", "ingestion_timestamp"),
}

NUMERIC_COLUMNS = {
    "customers": (),
    "products": ("unit_price",),
    "orders": ("quantity", "unit_price", "discount"),
}

NON_EMPTY_COLUMNS = {
    "customers": (
        "customer_id",
        "first_name",
        "last_name",
        "email",
        "city",
        "state",
        "source",
    ),
    "products": ("product_id", "sku", "product_name", "category", "source"),
    "orders": (
        "order_id",
        "customer_id",
        "product_id",
        "order_status",
        "source",
    ),
}

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_batch(
    datasets: dict[str, pd.DataFrame],
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, dict[str, dict[str, int]]]:
    """Validate source datasets; quarantine row-level issues with clear reasons."""
    unknown_datasets = set(datasets) - set(REQUIRED_COLUMNS)
    if unknown_datasets:
        raise ValueError(f"Unknown datasets: {', '.join(sorted(unknown_datasets))}")

    valid_datasets: dict[str, pd.DataFrame] = {}
    quarantined_rows: list[pd.DataFrame] = []
    summary: dict[str, dict[str, int]] = {}

    for name, source_data in datasets.items():
        missing_columns = REQUIRED_COLUMNS[name] - set(source_data.columns)
        if missing_columns:
            raise ValueError(
                f"{name} schema is missing required columns: "
                f"{', '.join(sorted(missing_columns))}"
            )

        data = source_data.copy()
        reasons: list[list[str]] = [[] for _ in range(len(data))]

        for column in STRING_COLUMNS[name]:
            data[column] = data[column].astype("string").str.strip()

        for column in NON_EMPTY_COLUMNS[name]:
            invalid = data[column].isna() | data[column].eq("")
            for position in invalid.to_numpy().nonzero()[0]:
                reasons[position].append(f"{column} is required")

        if name == "customers":
            invalid_email = ~data["email"].str.fullmatch(EMAIL_PATTERN, na=False)
            for position in invalid_email.to_numpy().nonzero()[0]:
                reasons[position].append("email is invalid")
            data["email"] = data["email"].str.lower()

        for column in DATETIME_COLUMNS[name]:
            original = data[column]
            parsed = pd.to_datetime(original, errors="coerce", utc=True)
            invalid = parsed.isna()
            for position in invalid.to_numpy().nonzero()[0]:
                reasons[position].append(f"{column} is missing or invalid")
            data[column] = parsed

        for column in NUMERIC_COLUMNS[name]:
            original = data[column]
            parsed = pd.to_numeric(original, errors="coerce")
            invalid = parsed.isna()
            for position in invalid.to_numpy().nonzero()[0]:
                reasons[position].append(f"{column} is missing or not numeric")
            data[column] = parsed

        if name == "products":
            invalid = data["unit_price"].lt(0).fillna(False)
            for position in invalid.to_numpy().nonzero()[0]:
                reasons[position].append("unit_price must not be negative")

        if name == "orders":
            invalid_quantity = (
                data["quantity"].le(0)
                | data["quantity"].mod(1).ne(0)
            ).fillna(False)
            for position in invalid_quantity.to_numpy().nonzero()[0]:
                reasons[position].append("quantity must be a positive whole number")

            invalid_price = data["unit_price"].le(0).fillna(False)
            for position in invalid_price.to_numpy().nonzero()[0]:
                reasons[position].append("unit_price must be greater than zero")

            invalid_discount = (
                data["discount"].lt(0)
                | data["discount"].gt(data["quantity"] * data["unit_price"])
            ).fillna(False)
            for position in invalid_discount.to_numpy().nonzero()[0]:
                reasons[position].append(
                    "discount must be between zero and the line total"
                )

        invalid_rows = [bool(row_reasons) for row_reasons in reasons]
        quarantine = data.loc[invalid_rows].copy()
        quarantine.insert(0, "dataset", name)
        quarantine["quarantine_reason"] = [
            "; ".join(reasons[position])
            for position, invalid in enumerate(invalid_rows)
            if invalid
        ]
        quarantined_rows.append(quarantine)

        valid_datasets[name] = data.loc[[not invalid for invalid in invalid_rows]].copy()
        summary[name] = {
            "input": len(data),
            "valid": int((~pd.Series(invalid_rows, dtype=bool)).sum()),
            "quarantined": int(sum(invalid_rows)),
        }

    quarantine_data = (
        pd.concat(quarantined_rows, ignore_index=True, sort=False)
        if quarantined_rows
        else pd.DataFrame(columns=["dataset", "quarantine_reason"])
    )
    return valid_datasets, quarantine_data, summary
