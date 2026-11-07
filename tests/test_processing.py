import unittest
from datetime import datetime, timezone

import pandas as pd

from src.transformation.clean import clean_batch
from src.validation.validate import validate_batch


def valid_order(order_id: str = "O1") -> dict[str, object]:
    return {
        "order_id": order_id,
        "customer_id": "C1",
        "product_id": "P1",
        "order_date": "2026-11-06T10:00:00Z",
        "quantity": "2",
        "unit_price": "10.00",
        "discount": "1.00",
        "order_status": "completed",
        "updated_at": "2026-11-06T10:00:00Z",
        "source": "test",
        "ingestion_timestamp": "2026-11-07T10:00:00Z",
    }


class ValidationTests(unittest.TestCase):
    def test_quarantines_missing_and_invalid_records_with_reasons(self) -> None:
        valid = valid_order()
        invalid = valid_order("O2")
        invalid["quantity"] = "1.5"
        invalid["discount"] = "99"
        missing_id = valid_order("")
        datasets = {
            "orders": pd.DataFrame([valid, invalid, missing_id]),
        }

        accepted, quarantine, summary = validate_batch(datasets)

        self.assertEqual(len(accepted["orders"]), 1)
        self.assertEqual(summary["orders"]["quarantined"], 2)
        reasons = quarantine.set_index("order_id")["quarantine_reason"]
        self.assertIn("quantity must be a positive whole number", reasons["O2"])
        self.assertIn("discount must be between zero and the line total", reasons["O2"])
        self.assertIn("order_id is required", reasons[""])

    def test_rejects_missing_required_schema_columns(self) -> None:
        with self.assertRaisesRegex(ValueError, "schema is missing required columns"):
            validate_batch({"orders": pd.DataFrame([{"order_id": "O1"}])})


class CleaningTests(unittest.TestCase):
    def test_deduplicates_by_latest_update_and_flags_late_orders(self) -> None:
        older = valid_order()
        newer = valid_order()
        newer["quantity"] = "3"
        newer["updated_at"] = "2026-11-06T11:00:00Z"
        validated, _, _ = validate_batch(
            {"orders": pd.DataFrame([older, newer])}
        )

        cleaned, summary = clean_batch(
            validated,
            as_of=datetime(2026, 11, 10, tzinfo=timezone.utc),
            late_after_days=1,
        )

        self.assertEqual(len(cleaned["orders"]), 1)
        self.assertEqual(cleaned["orders"].loc[0, "quantity"], 3)
        self.assertTrue(cleaned["orders"].loc[0, "late_arriving"])
        self.assertEqual(summary["orders"]["duplicates_removed"], 1)
        self.assertEqual(summary["orders"]["late_arriving"], 1)

    def test_rejects_negative_lateness_window(self) -> None:
        with self.assertRaisesRegex(ValueError, "late_after_days"):
            clean_batch({}, late_after_days=-1)


if __name__ == "__main__":
    unittest.main()
