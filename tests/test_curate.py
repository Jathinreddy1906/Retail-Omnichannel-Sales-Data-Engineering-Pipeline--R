import unittest

import pandas as pd

from src.transformation.curate import build_curated_datasets


class CuratedLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.customers = pd.DataFrame(
            [
                {
                    "customer_id": "C1",
                    "first_name": "Ava",
                    "last_name": "Patel",
                    "email": "ava@example.com",
                    "city": "Austin",
                    "state": "TX",
                }
            ]
        )
        self.products = pd.DataFrame(
            [
                {
                    "product_id": "P1",
                    "sku": "APP-1",
                    "product_name": "T-Shirt",
                    "category": "Apparel",
                }
            ]
        )
        self.orders = pd.DataFrame(
            [
                {
                    "order_id": "O1",
                    "customer_id": "C1",
                    "product_id": "P1",
                    "order_date": "2026-11-06T10:00:00Z",
                    "quantity": 2,
                    "unit_price": 24.99,
                    "discount": 5.00,
                    "order_status": "completed",
                    "source": "test",
                }
            ]
        )

    def test_enriches_sales_and_calculates_line_amounts(self) -> None:
        curated = build_curated_datasets(
            self.customers, self.products, self.orders
        )

        sale = curated["sales"].iloc[0]
        self.assertEqual(len(curated["sales"]), len(self.orders))
        self.assertEqual(sale["first_name"], "Ava")
        self.assertEqual(sale["product_name"], "T-Shirt")
        self.assertAlmostEqual(sale["gross_sales"], 49.98)
        self.assertAlmostEqual(sale["net_sales"], 44.98)
        self.assertEqual(str(sale["sales_date"]), "2026-11-06")

    def test_fails_explicitly_for_unknown_customer(self) -> None:
        self.orders.loc[0, "customer_id"] = "UNKNOWN"

        with self.assertRaisesRegex(ValueError, "unknown customer IDs"):
            build_curated_datasets(self.customers, self.products, self.orders)

    def test_rejects_duplicate_dimension_keys(self) -> None:
        duplicated = pd.concat([self.products, self.products], ignore_index=True)

        with self.assertRaisesRegex(ValueError, "unique, non-null product_id"):
            build_curated_datasets(self.customers, duplicated, self.orders)


if __name__ == "__main__":
    unittest.main()
