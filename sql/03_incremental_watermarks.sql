CREATE TABLE IF NOT EXISTS retail_dw.pipeline_watermark (
    entity_name TEXT PRIMARY KEY,
    last_updated_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
