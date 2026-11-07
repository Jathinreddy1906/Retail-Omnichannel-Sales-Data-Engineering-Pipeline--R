import pandas as pd


def build_curated_datasets(
    customers: pd.DataFrame,
    products: pd.DataFrame,
    orders: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Enrich sales lines and calculate order-line gross and net sales."""
    for name, data, key in (
        ("customers", customers, "customer_id"),
        ("products", products, "product_id"),
        ("orders", orders, "order_id"),
    ):
        if key not in data.columns:
            raise ValueError(f"{name} data is missing key column '{key}'")
        if data[key].isna().any() or data[key].duplicated().any():
            raise ValueError(f"{name} data must have unique, non-null {key} values")

    customer_attributes = [
        column
        for column in ("customer_id", "first_name", "last_name", "email", "city", "state")
        if column in customers.columns
    ]
    product_attributes = [
        column
        for column in ("product_id", "sku", "product_name", "category")
        if column in products.columns
    ]

    curated_sales = orders.merge(
        customers[customer_attributes],
        on="customer_id",
        how="left",
        validate="many_to_one",
    ).merge(
        products[product_attributes],
        on="product_id",
        how="left",
        validate="many_to_one",
    )

    missing_customers = curated_sales["first_name"].isna()
    if missing_customers.any():
        ids = sorted(curated_sales.loc[missing_customers, "customer_id"].unique())
        raise ValueError(f"Orders reference unknown customer IDs: {', '.join(ids)}")

    missing_products = curated_sales["product_name"].isna()
    if missing_products.any():
        ids = sorted(curated_sales.loc[missing_products, "product_id"].unique())
        raise ValueError(f"Orders reference unknown product IDs: {', '.join(ids)}")

    curated_sales["gross_sales"] = curated_sales["quantity"] * curated_sales["unit_price"]
    curated_sales["net_sales"] = curated_sales["gross_sales"] - curated_sales["discount"]
    curated_sales["sales_date"] = pd.to_datetime(
        curated_sales["order_date"], utc=True
    ).dt.date

    return {
        "sales": curated_sales,
        "customers": customers.copy(),
        "products": products.copy(),
    }
