CREATE SCHEMA IF NOT EXISTS retail_dw;

CREATE TABLE IF NOT EXISTS retail_dw.dim_customer (
    customer_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id TEXT NOT NULL,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    effective_start TIMESTAMPTZ NOT NULL,
    effective_end TIMESTAMPTZ,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT ck_dim_customer_effective_period
        CHECK (effective_end IS NULL OR effective_end > effective_start),
    CONSTRAINT ck_dim_customer_current_period
        CHECK (is_current = (effective_end IS NULL))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_dim_customer_current
    ON retail_dw.dim_customer (customer_id)
    WHERE is_current;

CREATE INDEX IF NOT EXISTS ix_dim_customer_business_key
    ON retail_dw.dim_customer (customer_id);

CREATE TABLE IF NOT EXISTS retail_dw.dim_product (
    product_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id TEXT NOT NULL UNIQUE,
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    category TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS retail_dw.dim_date (
    date_key INTEGER PRIMARY KEY,
    full_date DATE NOT NULL UNIQUE,
    calendar_year SMALLINT NOT NULL,
    quarter SMALLINT NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    month_number SMALLINT NOT NULL CHECK (month_number BETWEEN 1 AND 12),
    month_name TEXT NOT NULL,
    day_of_month SMALLINT NOT NULL CHECK (day_of_month BETWEEN 1 AND 31),
    day_of_week SMALLINT NOT NULL CHECK (day_of_week BETWEEN 1 AND 7),
    day_name TEXT NOT NULL,
    is_weekend BOOLEAN NOT NULL,
    CONSTRAINT ck_dim_date_key
        CHECK (
            date_key = EXTRACT(YEAR FROM full_date)::INTEGER * 10000
                + EXTRACT(MONTH FROM full_date)::INTEGER * 100
                + EXTRACT(DAY FROM full_date)::INTEGER
        )
);

CREATE TABLE IF NOT EXISTS retail_dw.fact_sales (
    sales_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id TEXT NOT NULL UNIQUE,
    customer_key BIGINT NOT NULL
        REFERENCES retail_dw.dim_customer (customer_key),
    product_key BIGINT NOT NULL
        REFERENCES retail_dw.dim_product (product_key),
    date_key INTEGER NOT NULL
        REFERENCES retail_dw.dim_date (date_key),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price > 0),
    discount NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (discount >= 0),
    gross_sales NUMERIC(14, 2) NOT NULL CHECK (gross_sales >= 0),
    net_sales NUMERIC(14, 2) NOT NULL CHECK (net_sales >= 0),
    order_status TEXT NOT NULL,
    late_arriving BOOLEAN NOT NULL DEFAULT FALSE,
    source TEXT NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_fact_sales_amounts
        CHECK (discount <= gross_sales AND net_sales = gross_sales - discount)
);

CREATE INDEX IF NOT EXISTS ix_fact_sales_date_key
    ON retail_dw.fact_sales (date_key);

CREATE INDEX IF NOT EXISTS ix_fact_sales_customer_key
    ON retail_dw.fact_sales (customer_key);

CREATE INDEX IF NOT EXISTS ix_fact_sales_product_key
    ON retail_dw.fact_sales (product_key);
