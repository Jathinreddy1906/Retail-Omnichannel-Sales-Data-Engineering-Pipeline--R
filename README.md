# Retail Omnichannel Sales Data Engineering Pipeline

An end-to-end Python and PostgreSQL example pipeline for retail customers,
products, and order-line sales. It ingests CSV, JSON/REST API, and optional
PostgreSQL source data, validates and quarantines bad records, builds clean and
curated data layers, and can incrementally load a PostgreSQL star schema.

## Features

- CSV ingestion with Pandas and REST JSON ingestion with `requests`.
- Bundled API JSON fixture for offline runs.
- Optional PostgreSQL source extraction through SQLAlchemy and psycopg2.
- Source labels and UTC ingestion timestamps on ingested records.
- Schema, field, type, and basic sales-rule validation.
- Invalid-record quarantine with per-row validation reasons.
- Deduplication by business key and late-arriving order flags.
- Curated sales enriched with customer/product attributes and gross/net sales.
- PostgreSQL star schema with customer SCD Type 2 history.
- Transactional incremental loading with watermarks and idempotent upserts.
- SQL analytics, pipeline logs, quality reports, source-to-target mapping, and
  reconciliation counts.

## Requirements

- Windows 10/11 and PowerShell (or another supported Python environment).
- Python 3.10 or newer.
- PostgreSQL 12 or newer for warehouse loading.
- `psql` or pgAdmin to apply the SQL scripts when enabling the warehouse.

The pipeline can run end-to-end against the included sample files without a
PostgreSQL server. The warehouse load is skipped unless
`WAREHOUSE_DATABASE_URL` is configured.

## Setup on Windows

Open PowerShell in the project directory:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

In VS Code, select the project's `.venv` interpreter using **Python: Select
Interpreter**. Edit `.env` only for the sources you want to enable. The sample
CSV and API fixture run without any `.env` changes.

## Configuration

| Variable | Required | Purpose |
| --- | --- | --- |
| `SALES_API_URL` | No | REST endpoint returning a JSON array of sales or an object with a `sales` array. If blank, the bundled `data/raw/api_sales.json` fixture is used. |
| `SALES_API_TIMEOUT_SECONDS` | No | HTTP request timeout in seconds; defaults to `30`. |
| `POSTGRES_SOURCE_URL` | No | SQLAlchemy URL for an optional source PostgreSQL database. |
| `POSTGRES_SOURCE_QUERY` | No | Source query; defaults to `SELECT * FROM orders`. Its output must match the order schema expected by validation. |
| `WAREHOUSE_DATABASE_URL` | No | SQLAlchemy URL for the target PostgreSQL warehouse. Enables warehouse loading when set. |

Example URL formats (replace placeholders; do not commit real credentials):

```text
postgresql+psycopg2://USER:PASSWORD@HOST:5432/DATABASE
```

Use URL-encoded special characters in database credentials. Keep `.env`
private; it is excluded from Git.

## Run the pipeline

From the project directory, with the virtual environment active:

```powershell
python main.py
```

The run performs these stages in order:

1. Ingest `customers.csv`, `products.csv`, and `orders.csv`; read API sales from
   the configured endpoint or bundled fixture; optionally query source
   PostgreSQL.
2. Validate columns and values, quarantine invalid rows, deduplicate records,
   and flag late-arriving orders.
3. Join order lines to customer and product attributes and calculate
   `gross_sales`, `net_sales`, and `sales_date`.
4. If a target URL is configured, apply incremental customer/product/sales
   changes to PostgreSQL and update watermarks in the same transaction.
5. Write run, quality, reconciliation, and source-to-target mapping reports.

Errors are logged and re-raised so failed executions return a non-zero process
exit code. Failure details are recorded in the execution report when reporting
is available.

## PostgreSQL warehouse setup

Create or select a target database, then execute these scripts in order:

1. `sql/01_warehouse_schema.sql`
2. `sql/02_customer_scd2.sql`
3. `sql/03_incremental_watermarks.sql`

For example, with PostgreSQL's `psql` command-line client:

```powershell
psql -v ON_ERROR_STOP=1 -d "postgresql://USER:PASSWORD@HOST:5432/DATABASE" -f sql/01_warehouse_schema.sql
psql -v ON_ERROR_STOP=1 -d "postgresql://USER:PASSWORD@HOST:5432/DATABASE" -f sql/02_customer_scd2.sql
psql -v ON_ERROR_STOP=1 -d "postgresql://USER:PASSWORD@HOST:5432/DATABASE" -f sql/03_incremental_watermarks.sql
```

Set `WAREHOUSE_DATABASE_URL` in `.env`, then run `python main.py`. The loader
expects the scripts to have been applied and writes the `retail_dw` schema. The
customer staging table is managed by the loader. To run business analytics
after data has loaded, execute `sql/04_analytics_queries.sql`.

The fact table grain is one row per `order_id` (one product per input order
record). Customer dimensions retain historical versions with half-open
effective periods. The loader replays the watermark boundary timestamp to avoid
missing tied updates; primary-key upserts make replays safe.

More details on manual staging and the SCD procedure are in
[`sql/README.md`](sql/README.md).

## Data layers and outputs

| Layer / output | Location | Contents |
| --- | --- | --- |
| Original samples | `data/raw/` | Starter customer, product, order CSVs and API JSON fixture. |
| Ingested snapshots | `data/raw/ingested/` | Source records with `source` and `ingestion_timestamp`. |
| Quarantine | `data/quarantine/invalid_records.csv` | Rejected rows with dataset and validation reasons. |
| Clean | `data/clean/` | Validated, deduplicated records; orders include `late_arriving`. |
| Curated | `data/curated/` | Enriched sales, customers, and products. |
| Warehouse | PostgreSQL `retail_dw` schema | `fact_sales`, `dim_customer`, `dim_product`, `dim_date`, watermark table, and customer staging. |
| Logs | `logs/pipeline.log` | Timestamped execution and error logs. |
| Reports | `reports/` | Execution JSON, data-quality JSON, reconciliation CSV, and mapping CSV. |

Generated snapshots, logs, local `.env`, Python caches, and the virtual
environment are excluded by `.gitignore`.

## Tests

Run the test suite from the project directory:

```powershell
python -m unittest discover -s tests -v
```

The tests cover API parsing, validation and quarantine, deduplication and late
records, curated joins and sales calculations, watermark filtering, and
monitoring report output. PostgreSQL DDL and database loading require a
configured PostgreSQL server and are not exercised by the offline unit tests.

## Project structure

```text
config/                 Environment-backed settings
data/raw/               Sample source files and ingested snapshots
data/clean/             Validated, deduplicated snapshots
data/curated/           Enriched business-ready snapshots
data/quarantine/        Invalid records and validation reasons
logs/                   Pipeline execution logs
reports/                Generated monitoring and reconciliation reports
src/ingestion/          CSV, REST JSON, and PostgreSQL extraction
src/validation/         Schema and value validation
src/transformation/     Clean and curated data processing
src/warehouse/          Reserved for warehouse utilities
src/loading/            Incremental PostgreSQL warehouse loader
src/reporting/          Pipeline monitoring and reports
sql/                    PostgreSQL DDL, SCD2, watermarks, and analytics
tests/                  Unit tests
main.py                 End-to-end pipeline entry point
requirements.txt        Python dependencies
```
