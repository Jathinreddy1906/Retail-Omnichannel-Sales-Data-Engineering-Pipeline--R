CREATE TABLE IF NOT EXISTS retail_dw.stg_customer (
    customer_id TEXT NOT NULL,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    effective_start TIMESTAMPTZ NOT NULL
);

CREATE OR REPLACE PROCEDURE retail_dw.apply_customer_scd2()
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM retail_dw.stg_customer
        GROUP BY customer_id
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION 'Customer staging contains duplicate customer_id values';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM retail_dw.stg_customer AS stage
        JOIN retail_dw.dim_customer AS current_customer
          ON current_customer.customer_id = stage.customer_id
         AND current_customer.is_current
        WHERE (
            current_customer.first_name IS DISTINCT FROM stage.first_name
            OR current_customer.last_name IS DISTINCT FROM stage.last_name
            OR current_customer.email IS DISTINCT FROM stage.email
            OR current_customer.phone IS DISTINCT FROM stage.phone
            OR current_customer.city IS DISTINCT FROM stage.city
            OR current_customer.state IS DISTINCT FROM stage.state
        )
          AND stage.effective_start <= current_customer.effective_start
    ) THEN
        RAISE EXCEPTION
            'Customer staging contains a changed record that is not newer than its current version';
    END IF;

    UPDATE retail_dw.dim_customer AS current_customer
       SET effective_end = stage.effective_start,
           is_current = FALSE
      FROM retail_dw.stg_customer AS stage
     WHERE current_customer.customer_id = stage.customer_id
       AND current_customer.is_current
       AND (
            current_customer.first_name IS DISTINCT FROM stage.first_name
            OR current_customer.last_name IS DISTINCT FROM stage.last_name
            OR current_customer.email IS DISTINCT FROM stage.email
            OR current_customer.phone IS DISTINCT FROM stage.phone
            OR current_customer.city IS DISTINCT FROM stage.city
            OR current_customer.state IS DISTINCT FROM stage.state
       );

    INSERT INTO retail_dw.dim_customer (
        customer_id,
        first_name,
        last_name,
        email,
        phone,
        city,
        state,
        effective_start,
        effective_end,
        is_current
    )
    SELECT
        stage.customer_id,
        stage.first_name,
        stage.last_name,
        stage.email,
        stage.phone,
        stage.city,
        stage.state,
        stage.effective_start,
        NULL,
        TRUE
    FROM retail_dw.stg_customer AS stage
    WHERE NOT EXISTS (
        SELECT 1
        FROM retail_dw.dim_customer AS current_customer
        WHERE current_customer.customer_id = stage.customer_id
          AND current_customer.is_current
    );
END;
$$;
