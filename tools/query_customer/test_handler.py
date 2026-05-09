"""Unit tests for QueryCustomerTool Lambda handler.

Uses unittest.mock to patch boto3 DynamoDB interactions.
"""

import json
import os
import unittest
from unittest.mock import MagicMock, patch

# Set env var before importing handler
os.environ["CUSTOMER_TABLE_NAME"] = "TestCustomerTable"

from tools.query_customer.handler import handler, _deduplicate


class TestDeduplicate(unittest.TestCase):
    """Tests for the _deduplicate helper."""

    def test_removes_duplicate_customer_ids(self):
        records = [
            {"customerId": "c1", "firstName": "A"},
            {"customerId": "c1", "firstName": "A"},
            {"customerId": "c2", "firstName": "B"},
        ]
        result = _deduplicate(records)
        self.assertEqual(len(result), 2)
        self.assertEqual([r["customerId"] for r in result], ["c1", "c2"])

    def test_empty_list(self):
        self.assertEqual(_deduplicate([]), [])

    def test_preserves_order(self):
        records = [
            {"customerId": "c3"},
            {"customerId": "c1"},
            {"customerId": "c2"},
        ]
        result = _deduplicate(records)
        self.assertEqual([r["customerId"] for r in result], ["c3", "c1", "c2"])


def _make_mock_table(email_items=None, phone_items=None, postal_items=None):
    """Create a mock DynamoDB Table that returns configured items per GSI."""
    mock_table = MagicMock()

    def query_side_effect(**kwargs):
        index = kwargs.get("IndexName", "")
        if index == "EmailIndex":
            return {"Items": email_items or []}
        if index == "PhoneIndex":
            return {"Items": phone_items or []}
        if index == "PostalCodeLastNameIndex":
            return {"Items": postal_items or []}
        return {"Items": []}

    mock_table.query = MagicMock(side_effect=query_side_effect)
    return mock_table


SAMPLE_RECORD_A = {
    "customerId": "c001",
    "firstName": "Chris",
    "lastName": "James",
    "email": "chris.james@fakecorp.com",
    "phone": "+15551234001",
    "postalCode": "62701",
}

SAMPLE_RECORD_B = {
    "customerId": "c002",
    "firstName": "Maria",
    "lastName": "Garcia",
    "email": "maria.garcia@testmail.net",
    "phone": "+15559876001",
    "postalCode": "73301",
}


class TestHandler(unittest.TestCase):
    """Tests for the Lambda handler function."""

    @patch("tools.query_customer.handler._get_table")
    def test_email_strategy(self, mock_get_table):
        mock_get_table.return_value = _make_mock_table(email_items=[SAMPLE_RECORD_A])

        result = handler({"firstName": "Chris", "lastName": "James", "email": "chris.james@fakecorp.com"}, None)

        self.assertEqual(result["candidateCount"], 1)
        self.assertIn("email_exact", result["blockingStrategiesUsed"])
        self.assertEqual(result["candidates"][0]["customerId"], "c001")

    @patch("tools.query_customer.handler._get_table")
    def test_phone_strategy(self, mock_get_table):
        mock_get_table.return_value = _make_mock_table(phone_items=[SAMPLE_RECORD_B])

        result = handler({"firstName": "Maria", "lastName": "Garcia", "phone": "+15559876001"}, None)

        self.assertEqual(result["candidateCount"], 1)
        self.assertIn("phone_exact", result["blockingStrategiesUsed"])
        self.assertEqual(result["candidates"][0]["customerId"], "c002")

    @patch("tools.query_customer.handler._get_table")
    def test_postal_code_lastname_strategy(self, mock_get_table):
        mock_get_table.return_value = _make_mock_table(postal_items=[SAMPLE_RECORD_A])

        result = handler({"firstName": "Chris", "lastName": "James", "postalCode": "62701"}, None)

        self.assertEqual(result["candidateCount"], 1)
        self.assertIn("postal_code_lastname", result["blockingStrategiesUsed"])

    @patch("tools.query_customer.handler._get_table")
    def test_multiple_strategies_deduplicates(self, mock_get_table):
        """Same record returned by email and phone should appear once."""
        mock_get_table.return_value = _make_mock_table(
            email_items=[SAMPLE_RECORD_A],
            phone_items=[SAMPLE_RECORD_A],
        )

        result = handler({
            "firstName": "Chris", "lastName": "James",
            "email": "chris.james@fakecorp.com", "phone": "+15551234001",
        }, None)

        self.assertEqual(result["candidateCount"], 1)
        self.assertIn("email_exact", result["blockingStrategiesUsed"])
        self.assertIn("phone_exact", result["blockingStrategiesUsed"])

    @patch("tools.query_customer.handler._get_table")
    def test_multiple_strategies_different_records(self, mock_get_table):
        mock_get_table.return_value = _make_mock_table(
            email_items=[SAMPLE_RECORD_A],
            phone_items=[SAMPLE_RECORD_B],
        )

        result = handler({
            "firstName": "Chris", "lastName": "James",
            "email": "chris.james@fakecorp.com", "phone": "+15559876001",
        }, None)

        self.assertEqual(result["candidateCount"], 2)

    @patch("tools.query_customer.handler._get_table")
    def test_no_strategies_applied(self, mock_get_table):
        """When no optional fields provided, no strategies run, empty result."""
        mock_get_table.return_value = _make_mock_table()

        result = handler({"firstName": "Chris", "lastName": "James"}, None)

        self.assertEqual(result["candidateCount"], 0)
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["blockingStrategiesUsed"], [])

    @patch("tools.query_customer.handler._get_table")
    def test_max_10_candidates(self, mock_get_table):
        """Results are capped at 10 candidates."""
        many_records = [{"customerId": f"c{i:03d}", "firstName": "X", "lastName": "Y"} for i in range(15)]
        mock_get_table.return_value = _make_mock_table(email_items=many_records)

        result = handler({"firstName": "X", "lastName": "Y", "email": "x@y.com"}, None)

        self.assertEqual(result["candidateCount"], 10)
        self.assertEqual(len(result["candidates"]), 10)

    @patch("tools.query_customer.handler._get_table")
    def test_json_string_body(self, mock_get_table):
        """Handler supports event with JSON string body (API Gateway proxy)."""
        mock_get_table.return_value = _make_mock_table(email_items=[SAMPLE_RECORD_A])

        event = {"body": json.dumps({"firstName": "Chris", "lastName": "James", "email": "chris.james@fakecorp.com"})}
        result = handler(event, None)

        self.assertEqual(result["candidateCount"], 1)


if __name__ == "__main__":
    unittest.main()
