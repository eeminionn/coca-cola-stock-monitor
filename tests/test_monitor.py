import json
import unittest
from unittest.mock import patch

from scripts.coke_monitor import collect_products, detect_changes


class ProductCollectionTests(unittest.TestCase):
    @patch("scripts.coke_monitor.fetch_text")
    def test_collects_matching_products_and_prefers_available_offer(self, fetch_text):
        fetch_text.return_value = json.dumps(
            [
                {
                    "productId": "42",
                    "productName": "Pack láminas Mundial",
                    "link": "https://example.test/pack",
                    "items": [
                        {
                            "itemId": "sku-1",
                            "nameComplete": "Pack de 10 láminas",
                            "sellers": [
                                {
                                    "commertialOffer": {
                                        "IsAvailable": False,
                                        "AvailableQuantity": 0,
                                        "Price": 1000,
                                    }
                                },
                                {
                                    "commertialOffer": {
                                        "IsAvailable": True,
                                        "AvailableQuantity": "7",
                                        "Price": "1290",
                                    }
                                },
                            ],
                        }
                    ],
                }
            ]
        )

        products, errors = collect_products(["laminas"], ["láminas"])

        self.assertEqual(errors, [])
        self.assertEqual(list(products), ["42:sku-1"])
        product = products["42:sku-1"]
        self.assertTrue(product.available)
        self.assertEqual(product.quantity, 7)
        self.assertEqual(product.price, 1290.0)
        self.assertEqual(product.source_terms, ["laminas"])

    @patch("scripts.coke_monitor.fetch_text")
    def test_ignores_products_that_do_not_match_keywords(self, fetch_text):
        fetch_text.return_value = json.dumps(
            [{"productId": "7", "productName": "Bebida", "items": []}]
        )

        products, errors = collect_products(["bebida"], ["mundial"])

        self.assertEqual(products, {})
        self.assertEqual(errors, [])


class ChangeDetectionTests(unittest.TestCase):
    def test_detects_new_availability_and_page_changes(self):
        previous_products = {
            "old": {"name": "Sobre", "available": False},
        }
        current_products = {
            "old": {"name": "Sobre", "available": True},
            "new": {"name": "Album", "available": False},
        }
        previous_pages = {"https://example.test": {"digest": "before"}}
        current_pages = {"https://example.test": {"digest": "after"}}

        new_products, availability_changes, page_changes = detect_changes(
            previous_products,
            previous_pages,
            current_products,
            current_pages,
        )

        self.assertEqual(new_products, [current_products["new"]])
        self.assertEqual(
            availability_changes,
            [(previous_products["old"], current_products["old"])],
        )
        self.assertEqual(
            page_changes,
            [("https://example.test", current_pages["https://example.test"])],
        )


if __name__ == "__main__":
    unittest.main()
