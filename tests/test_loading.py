import unittest
from unittest.mock import patch

import pandas as pd

from src.loading.warehouse_loader import load_warehouse, rows_after_watermark


class WatermarkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = pd.DataFrame(
            {
                "order_id": ["O1", "O2", "O3"],
                "updated_at": [
                    "2026-11-06T09:00:00Z",
                    "2026-11-06T10:00:00Z",
                    "2026-11-06T11:00:00Z",
                ],
            }
        )

    def test_includes_boundary_timestamp_for_safe_replay(self) -> None:
        result = rows_after_watermark(
            self.data,
            "2026-11-06T10:00:00Z",
        )

        self.assertEqual(result["order_id"].tolist(), ["O2", "O3"])

    def test_initial_load_returns_all_rows(self) -> None:
        self.assertEqual(len(rows_after_watermark(self.data, None)), 3)

    def test_rejects_missing_or_invalid_source_timestamps(self) -> None:
        invalid = self.data.copy()
        invalid.loc[1, "updated_at"] = "not-a-timestamp"

        with self.assertRaisesRegex(ValueError, "missing or invalid timestamps"):
            rows_after_watermark(invalid, None)

    def test_rejects_missing_timestamp_column(self) -> None:
        with self.assertRaisesRegex(ValueError, "Missing incremental timestamp"):
            rows_after_watermark(pd.DataFrame({"order_id": ["O1"]}), None)

    @patch("src.loading.warehouse_loader.WAREHOUSE_DATABASE_URL", None)
    def test_pipeline_skips_warehouse_without_target_configuration(self) -> None:
        self.assertIsNone(load_warehouse())


if __name__ == "__main__":
    unittest.main()
