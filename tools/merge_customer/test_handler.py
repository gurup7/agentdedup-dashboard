"""Unit tests for MergeCustomerTool Lambda handler.

Uses unittest.mock to patch boto3 DynamoDB interactions.
"""

import json
import os
import unittest
from unittest.mock import MagicMock, patch, call

# Set env vars before importing handler
os.environ["CUSTOMER_TABLE_NAME"] = "TestCustomerTable"
os.environ["REVIEW_QUEUE_TABLE_NAME"] = "TestReviewQueue"

from tools.merge_customer.handler import handler, _consolidate, _mask_pii


SOURCE_RECORD = {
    "customerId": "src-001",
    "firstName": "Chris",
    "lastName": "James",
    "email": "chris@old.com",
    "phone": "+15551111111",
    "sourceSystem": "OneCRM",
    "status": "active",
    "createdAt": "2024-01-01T00:00:00+00:00",
    "updatedAt": "2024-06-01T00:00:00+00:00",
}

MASTER_RECORD = {
    "customerId": "mst-001",
    "firstName": "Chris",
    "lastName": "James",
    "email": "chris@new.com",
    "sourceSystem": "NES",
    "status": "active",
    "createdAt": "2024-01-01T00:00:00+00:00",
    "updatedAt": "2024-07-01T00:00:00+00:00",
}


def _make_mock_tables(source=None, master=None):
    """Return (mock_customer_table, mock_review_table) with get_item configured."""
    mock_customer = MagicMock()
    mock_review = MagicMock()

    def get_item_side_effect(**kwargs):
        cid = kwargs["Key"]["customerId"]
        if cid == "src-001":
            return {"Item": source} if source else {}
        if cid == "mst-001":
            return {"Item": master} if master else {}
        return {}

    mock_customer.get_item = MagicMock(side_effect=get_item_side_effect)
    return mock_customer, mock_review


class TestMaskPii(unittest.TestCase):
    """Tests for the _mask_pii helper."""

    def test_masks_pii_fields(self):
        record = {"customerId": "c1", "email": "a@b.com", "phone": "+1555", "firstName": "X"}
        masked = _mask_pii(record)
        self.assertEqual(masked["customerId"], "c1")
        self.assertEqual(masked["firstName"], "X")
        self.assertEqual(masked["email"], "***")
        self.assertEqual(masked["phone"], "***")

    def test_empty_record(self):
        self.assertEqual(_mask_pii({}), {})


class TestConsolidate(unittest.TestCase):
    """Tests for the _consolidate helper."""

    def test_fills_missing_master_fields(self):
        source = {"phone": "+1555", "updatedAt": "2024-01-01T00:00:00+00:00"}
        master = {"updatedAt": "2024-06-01T00:00:00+00:00"}
        updates, fields = _consolidate(source, master)
        self.assertIn("phone", updates)
        self.assertIn("phone", fields)

    def test_prefers_newer_source(self):
        source = {"email": "new@x.com", "updatedAt": "2024-08-01T00:00:00+00:00"}
        master = {"email": "old@x.com", "updatedAt": "2024-01-01T00:00:00+00:00"}
        updates, fields = _consolidate(source, master)
        self.assertEqual(updates["email"], "new@x.com")
        self.assertIn("email", fields)

    def test_keeps_master_when_newer(self):
        source = {"email": "old@x.com", "updatedAt": "2024-01-01T00:00:00+00:00"}
        master = {"email": "new@x.com", "updatedAt": "2024-08-01T00:00:00+00:00"}
        updates, fields = _consolidate(source, master)
        self.assertEqual(updates, {})
        self.assertEqual(fields, [])

    def test_no_updates_when_source_empty(self):
        source = {"updatedAt": "2024-01-01T00:00:00+00:00"}
        master = {"email": "a@b.com", "updatedAt": "2024-01-01T00:00:00+00:00"}
        updates, fields = _consolidate(source, master)
        self.assertEqual(updates, {})
        self.assertEqual(fields, [])


class TestHandler(unittest.TestCase):
    """Tests for the Lambda handler function."""

    @patch("tools.merge_customer.handler._get_review_table")
    @patch("tools.merge_customer.handler._get_customer_table")
    def test_successful_merge(self, mock_get_cust, mock_get_rev):
        mock_cust, mock_rev = _make_mock_tables(SOURCE_RECORD, MASTER_RECORD)
        mock_get_cust.return_value = mock_cust
        mock_get_rev.return_value = mock_rev

        result = handler({
            "sourceRecordId": "src-001",
            "targetMasterRecordId": "mst-001",
            "reviewId": "rev-001",
        }, None)

        self.assertEqual(result["mergedRecordId"], "mst-001")
        self.assertEqual(result["sourceRecordId"], "src-001")
        self.assertIsInstance(result["fieldsConsolidated"], list)

        # Source record updated to merged status
        source_update = mock_cust.update_item.call_args_list[0]
        self.assertEqual(source_update[1]["Key"], {"customerId": "src-001"})
        self.assertIn("merged", str(source_update))

        # Review queue updated to approved
        mock_rev.update_item.assert_called_once()
        rev_update = mock_rev.update_item.call_args
        self.assertEqual(rev_update[1]["Key"], {"reviewId": "rev-001"})
        self.assertIn("approved", str(rev_update))

    @patch("tools.merge_customer.handler._get_review_table")
    @patch("tools.merge_customer.handler._get_customer_table")
    def test_consolidates_missing_phone_from_source(self, mock_get_cust, mock_get_rev):
        """Source has phone, master doesn't — phone should be consolidated."""
        mock_cust, mock_rev = _make_mock_tables(SOURCE_RECORD, MASTER_RECORD)
        mock_get_cust.return_value = mock_cust
        mock_get_rev.return_value = mock_rev

        result = handler({
            "sourceRecordId": "src-001",
            "targetMasterRecordId": "mst-001",
            "reviewId": "rev-001",
        }, None)

        self.assertIn("phone", result["fieldsConsolidated"])

    @patch("tools.merge_customer.handler._get_review_table")
    @patch("tools.merge_customer.handler._get_customer_table")
    def test_raises_on_missing_source(self, mock_get_cust, mock_get_rev):
        mock_cust, mock_rev = _make_mock_tables(source=None, master=MASTER_RECORD)
        mock_get_cust.return_value = mock_cust
        mock_get_rev.return_value = mock_rev

        with self.assertRaises(ValueError) as ctx:
            handler({
                "sourceRecordId": "src-001",
                "targetMasterRecordId": "mst-001",
                "reviewId": "rev-001",
            }, None)
        self.assertIn("Source record not found", str(ctx.exception))

    @patch("tools.merge_customer.handler._get_review_table")
    @patch("tools.merge_customer.handler._get_customer_table")
    def test_raises_on_missing_master(self, mock_get_cust, mock_get_rev):
        mock_cust, mock_rev = _make_mock_tables(source=SOURCE_RECORD, master=None)
        mock_get_cust.return_value = mock_cust
        mock_get_rev.return_value = mock_rev

        with self.assertRaises(ValueError) as ctx:
            handler({
                "sourceRecordId": "src-001",
                "targetMasterRecordId": "mst-001",
                "reviewId": "rev-001",
            }, None)
        self.assertIn("Master record not found", str(ctx.exception))

    @patch("tools.merge_customer.handler._get_review_table")
    @patch("tools.merge_customer.handler._get_customer_table")
    def test_no_delete_operations(self, mock_get_cust, mock_get_rev):
        """Verify NO delete operations are called — Req 7."""
        mock_cust, mock_rev = _make_mock_tables(SOURCE_RECORD, MASTER_RECORD)
        mock_get_cust.return_value = mock_cust
        mock_get_rev.return_value = mock_rev

        handler({
            "sourceRecordId": "src-001",
            "targetMasterRecordId": "mst-001",
            "reviewId": "rev-001",
        }, None)

        mock_cust.delete_item.assert_not_called()
        mock_rev.delete_item.assert_not_called()

    @patch("tools.merge_customer.handler._get_review_table")
    @patch("tools.merge_customer.handler._get_customer_table")
    def test_json_string_body(self, mock_get_cust, mock_get_rev):
        mock_cust, mock_rev = _make_mock_tables(SOURCE_RECORD, MASTER_RECORD)
        mock_get_cust.return_value = mock_cust
        mock_get_rev.return_value = mock_rev

        event = {"body": json.dumps({
            "sourceRecordId": "src-001",
            "targetMasterRecordId": "mst-001",
            "reviewId": "rev-001",
        })}
        result = handler(event, None)

        self.assertEqual(result["mergedRecordId"], "mst-001")


if __name__ == "__main__":
    unittest.main()
