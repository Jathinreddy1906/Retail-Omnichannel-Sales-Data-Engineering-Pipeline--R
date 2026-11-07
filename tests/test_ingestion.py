import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

from src.ingestion.extract import _records_from_api_payload, read_api_sales


class ApiIngestionTests(unittest.TestCase):
    def test_reads_api_fixture_and_adds_metadata(self) -> None:
        fixture = {
            "sales": [
                {
                    "order_id": "O1",
                    "customer_id": "C1",
                    "product_id": "P1",
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            fixture_path = Path(directory) / "sales.json"
            fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

            result = read_api_sales(api_url=None, fixture_path=fixture_path)

        self.assertEqual(result.loc[0, "order_id"], "O1")
        self.assertEqual(result.loc[0, "source"], "api_json_fixture")
        self.assertTrue(pd.Timestamp(result.loc[0, "ingestion_timestamp"]).tzinfo)

    @patch("src.ingestion.extract.requests.get")
    def test_fetches_api_payload_when_url_is_configured(
        self, get: Mock
    ) -> None:
        response = Mock()
        response.json.return_value = [{"order_id": "O2"}]
        get.return_value = response

        result = read_api_sales(api_url="https://example.test/sales")

        get.assert_called_once_with(
            "https://example.test/sales", timeout=30
        )
        response.raise_for_status.assert_called_once_with()
        self.assertEqual(result.loc[0, "source"], "rest_api")

    def test_rejects_malformed_api_records(self) -> None:
        with self.assertRaisesRegex(ValueError, "JSON object"):
            _records_from_api_payload({"sales": ["not-an-object"]})


if __name__ == "__main__":
    unittest.main()
