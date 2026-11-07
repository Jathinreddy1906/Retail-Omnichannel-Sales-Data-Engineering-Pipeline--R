import logging
import uuid
from datetime import datetime, timezone
from time import perf_counter

from config.settings import LOG_DIR, REPORT_DIR
from src.ingestion import run_ingestion
from src.loading.warehouse_loader import load_warehouse
from src.reporting import write_pipeline_reports
from src.transformation.curate_pipeline import build_curated_layer
from src.transformation.pipeline import process_ingested_data


def main() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_DIR / "pipeline.log", encoding="utf-8"),
        ],
        force=True,
    )

    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)
    stage_metrics: dict[str, dict[str, object]] = {}
    logger = logging.getLogger(__name__)
    logger.info("Starting pipeline run_id=%s", run_id)
    try:
        stage_started = perf_counter()
        ingestion_counts = run_ingestion()
        stage_metrics["ingestion"] = {
            "duration_seconds": round(perf_counter() - stage_started, 3),
            "records": ingestion_counts,
        }
        logger.info(
            "Ingestion complete: customers=%d products=%d orders=%d",
            ingestion_counts["customers"],
            ingestion_counts["products"],
            ingestion_counts["orders"],
        )

        stage_started = perf_counter()
        validation_counts = process_ingested_data()
        stage_metrics["validation"] = {
            "duration_seconds": round(perf_counter() - stage_started, 3),
            "datasets": validation_counts,
        }

        stage_started = perf_counter()
        curated_counts = build_curated_layer()
        stage_metrics["curation"] = {
            "duration_seconds": round(perf_counter() - stage_started, 3),
            "records": curated_counts,
        }

        stage_started = perf_counter()
        warehouse_counts = load_warehouse()
        stage_metrics["warehouse"] = {
            "duration_seconds": round(perf_counter() - stage_started, 3),
            "status": "skipped" if warehouse_counts is None else "loaded",
            "records": warehouse_counts or {},
        }
        if warehouse_counts is not None:
            logger.info(
                "Warehouse load complete: customers=%d products=%d sales=%d",
                warehouse_counts["customers"],
                warehouse_counts["products"],
                warehouse_counts["sales"],
            )

        paths = write_pipeline_reports(
            run_id=run_id,
            started_at=started_at,
            status="success",
            stage_metrics=stage_metrics,
        )
        logging.info(
            "Pipeline reports written: %s",
            ", ".join(str(path) for path in paths.values()),
        )
    except Exception as error:
        logger.exception("Pipeline failed run_id=%s", run_id)
        try:
            write_pipeline_reports(
                run_id=run_id,
                started_at=started_at,
                status="failed",
                stage_metrics=stage_metrics,
                error=f"{type(error).__name__}: {error}",
            )
        except Exception:
            logger.exception("Failed to write pipeline failure reports.")
        raise


if __name__ == "__main__":
    main()
