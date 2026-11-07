import csv
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.reporting.reports import write_pipeline_reports


class PipelineReportTests(unittest.TestCase):
    def test_writes_quality_reconciliation_mapping_and_execution_reports(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ingested = root / "raw"
            clean = root / "clean"
            curated = root / "curated"
            quarantine = root / "quarantine"
            reports = root / "reports"
            for path in (ingested, clean, curated, quarantine):
                path.mkdir()

            for folder, count in (
                (ingested, 3),
                (clean, 2),
                (curated, 2),
            ):
                pd.DataFrame({"id": range(count)}).to_csv(
                    folder / "orders.csv", index=False
                )
            pd.DataFrame(
                {"reason": ["invalid"], "order_id": ["O3"]}
            ).to_csv(quarantine / "invalid_records.csv", index=False)

            validation = {
                "orders": {
                    "input": 3,
                    "valid": 2,
                    "quarantined": 1,
                    "duplicates_removed": 0,
                    "duplicate_records_removed": 0,
                    "clean": 2,
                    "late_arriving": 0,
                }
            }
            with (
                patch("src.reporting.reports.INGESTED_DATA_DIR", ingested),
                patch("src.reporting.reports.CLEAN_DATA_DIR", clean),
                patch("src.reporting.reports.CURATED_DATA_DIR", curated),
                patch("src.reporting.reports.QUARANTINE_DATA_DIR", quarantine),
            ):
                paths = write_pipeline_reports(
                    run_id="run-test",
                    started_at=datetime(2026, 11, 7, tzinfo=timezone.utc),
                    status="success",
                    stage_metrics={
                        "validation": {
                            "duration_seconds": 0.1,
                            "datasets": validation,
                        }
                    },
                    report_dir=reports,
                )

            self.assertEqual(set(paths), {"execution", "quality", "reconciliation", "mapping"})
            execution = json.loads(paths["execution"].read_text(encoding="utf-8"))
            quality = json.loads(paths["quality"].read_text(encoding="utf-8"))
            self.assertEqual(execution["status"], "success")
            self.assertEqual(quality["total_quarantined_rows"], 1)

            with paths["reconciliation"].open(
                newline="", encoding="utf-8"
            ) as report:
                orders = next(
                    row for row in csv.DictReader(report)
                    if row["dataset"] == "orders"
                )
            self.assertEqual(orders["ingested_count"], "3")
            self.assertEqual(orders["clean_count"], "2")
            self.assertEqual(orders["ingested_to_clean_balanced"], "True")

            with paths["mapping"].open(
                newline="", encoding="utf-8"
            ) as report:
                self.assertGreaterEqual(len(list(csv.DictReader(report))), 6)

    def test_records_failed_run_and_error_message(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            empty = root / "empty"
            empty.mkdir()
            with (
                patch("src.reporting.reports.INGESTED_DATA_DIR", empty),
                patch("src.reporting.reports.CLEAN_DATA_DIR", empty),
                patch("src.reporting.reports.CURATED_DATA_DIR", empty),
                patch("src.reporting.reports.QUARANTINE_DATA_DIR", empty),
            ):
                paths = write_pipeline_reports(
                    run_id="failed-run",
                    started_at=datetime(2026, 11, 7, tzinfo=timezone.utc),
                    status="failed",
                    stage_metrics={"ingestion": {"error": "source unavailable"}},
                    error="ConnectionError: source unavailable",
                    report_dir=root / "reports",
                )

            execution = json.loads(paths["execution"].read_text(encoding="utf-8"))
            self.assertEqual(execution["status"], "failed")
            self.assertEqual(execution["error"], "ConnectionError: source unavailable")


if __name__ == "__main__":
    unittest.main()
