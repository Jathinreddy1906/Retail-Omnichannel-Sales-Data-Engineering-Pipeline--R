# PostgreSQL warehouse scripts

Run these scripts in order against the target PostgreSQL database:

1. `01_warehouse_schema.sql` creates the `retail_dw` star schema.
2. `02_customer_scd2.sql` creates customer staging and the SCD Type 2 procedure.
3. `03_incremental_watermarks.sql` creates the incremental load state table.
4. `04_analytics_queries.sql` contains example business and reconciliation reports.

Run the statements in `04_analytics_queries.sql` after loading warehouse data.
The examples cover daily/category aggregation, monthly trend comparisons, top
products by month, customer lifetime sales, cumulative revenue, and source/status
reconciliation. Revenue examples use completed orders; the reconciliation query
includes every status.

Set `WAREHOUSE_DATABASE_URL` in the project `.env` to enable the PostgreSQL
target load. Apply the three scripts above before the first run. `python main.py`
then loads the curated customer, product, and sales snapshots. Each entity's
watermark tracks its maximum source `updated_at`; the boundary timestamp is
replayed to handle tied timestamps, while database upserts prevent duplicates.
The loader applies dimension changes, date rows, facts, and watermark advances
in a single transaction. If no target URL is configured, the pipeline logs that
the warehouse load was skipped.

The `fact_sales` grain is one source record per `order_id`, matching the current
orders input, which contains one product per order record. Customer versions
have a surrogate key and half-open effective periods: the old version's
`effective_end` equals the next version's `effective_start`; the current version
has a null end date and `is_current = TRUE`.

To apply a staged customer snapshot, load one row per customer into
`retail_dw.stg_customer`. Set `effective_start` to the source `updated_at`
timestamp, then execute:

```sql
CALL retail_dw.apply_customer_scd2();
```

The procedure inserts new customers, leaves unchanged current versions alone,
and expires/replaces changed current versions. Duplicate staged customer IDs or
changed records that are not newer than the current version raise an error.
Staging rows are retained after the procedure call; clear or replace them only
after a successful load. Execute the stage load and procedure call in one
transaction so failures can be rolled back.
