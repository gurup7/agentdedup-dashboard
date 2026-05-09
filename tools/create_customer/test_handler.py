"""Unit tests for CreateCustomerTool Lambda handler.

Uses unittest.mock to patch boto3 DynamoDB interactions.
"""

import json
import os
import unittest
from unittest.mock import MagicMock, patch

# Set env var before importing handler
os.environ["CUSTOMER_TABLE_NAME"] = "TestCustomerTable"

from tools.create_customer.handler import handler


class TestHandler(unittest.TestCase):
    """Tests for the Lambda handler function."""

    @patch("tools.create_customer.handler._get_table")
    @patch("tools.create_customer.handler.uuid.uuid4", return_value="test-uuid-1234")
    def test_creates_customer_with_required_fields(self, _mock_uuid, mock_get_table):
        mock_table = MagicMock()
        mock_get_table.return_value = mock_table

        result = handler({
            "firstName": "Chris",
            "lastName": "James",
            "sourceSystem": "OneCRM",
        }, None)

        self.assertEqual(result["customerId"], "test-uuid-1234")
        self.assertEqual(result["status"], "created")
        mock_table.put_item.assert_called_once()
        item = mock_table.put_item.call_args[1]["Item"]
        self.assertEqual(item["firstName"], "Chris")
        self.assertEqual(item["lastName"], "James")
        self.assertEqual(item["sourceSystem"], "OneCRM")
        self.assertEqual(item["status"], "active")
        self.assertIn("createdAt", item)
        self.assertIn("updatedAt", item)

    @patch("tools.create_customer.handler._get_table")
    def test_includes_optional_fields(self, mock_get_table):
        mock_table = MagicMock()
        mock_get_table.return_value = mock_table

        result = handler({
            "firstName": "Maria",
            "lastName": "Garcia",
            "email": "maria@test.com",
            "phone": "+15551234567",
            "dateOfBirth": "1990-05-15",
            "sourceSystem": "NES",
            "address": {
                "street": "123 Main St",
                "city": "Springfield",
                "state": "IL",
                "postalCode": "62701",
                "country": "US",
            },
        }, None)

        self.assertEqual(result["status"], "created")
        item = mock_table.put_item.call_args[1]["Item"]
        self.assertEqual(item["email"], "maria@test.com")
        self.assertEqual(item["phone"], "+15551234567")
        self.assertEqual(item["dateOfBirth"], "1990-05-15")
        self.assertEqual(item["address"]["city"], "Springfield")
        # postalCode promoted to top level for GSI
        self.assertEqual(item["postalCode"], "62701")

    @patch("tools.create_customer.handler._get_table")
    def test_omits_empty_optional_fields(self, mock_get_table):
        mock_table = MagicMock()
        mock_get_table.return_value = mock_table

        handler({"firstName": "A", "lastName": "B", "sourceSystem": "OneCRM"}, None)

        item = mock_table.put_item.call_args[1]["Item"]
        self.assertNotIn("email", item)
        self.assertNotIn("phone", item)
        self.assertNotIn("dateOfBirth", item)
        self.assertNotIn("address", item)
        self.assertNotIn("postalCode", item)

    @patch("tools.create_customer.handler._get_table")
    def test_json_string_body(self, mock_get_table):
        mock_table = MagicMock()
        mock_get_table.return_value = mock_table

        event = {"body": json.dumps({
            "firstName": "Test",
            "lastName": "User",
            "sourceSystem": "OneCRM",
        })}
        result = handler(event, None)

        self.assertEqual(result["status"], "created")
        mock_table.put_item.assert_called_once()

    @patch("tools.create_customer.handler._get_table")
    @patch("tools.create_customer.handler.uuid.uuid4", return_value="uuid-abc")
    def test_timestamps_are_iso8601(self, _mock_uuid, mock_get_table):
        mock_table = MagicMock()
        mock_get_table.return_value = mock_table

        handler({"firstName": "A", "lastName": "B", "sourceSystem": "X"}, None)

        item = mock_table.put_item.call_args[1]["Item"]
        # ISO 8601 timestamps contain 'T' separator and '+' timezone
        self.assertIn("T", item["createdAt"])
        self.assertIn("T", item["updatedAt"])
        self.assertEqual(item["createdAt"], item["updatedAt"])


if __name__ == "__main__":
    unittest.main()
