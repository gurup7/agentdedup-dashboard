"""Unit tests for WriteReviewTool Lambda handler.

Uses unittest.mock to patch boto3 DynamoDB interactions.
"""

import json
import os
import unittest
from unittest.mock import MagicMock, patch

# Set env var before importing handler
os.environ["REVIEW_QUEUE_TABLE_NAME"] = "TestReviewQueue"

from tools.write_review.handler import handler, _mask_pii


SAMPLE_EVENT = {
    "incomingRecord": {
        "firstName": "Chris",
        "lastName": "James",
        "email": "chris@example.com",
        "sourceSystem": "OneCRM",
    },
    "matchedRecord": {
        "customerId": "existing-001",
        "firstName": "Chrish",
        "lastName": "James",
        "email": "chris@example.com",
        "sourceSystem": "NES",
    },
    "confidenceScore": 0.87,
    "confidenceClassification": "potential_duplicate",
    "matchingMethod": "rule+llm",
    "contributingFields": ["email", "lastName"],
    "sourceAgent": "intercept",
}


class TestMaskPii(unittest.TestCase):
    """Tests for the _mask_pii helper."""

    def test_masks_pii_fields(self):
        record = {"customerId": "c1", "email": "a@b.com", "phone": "+1555"}
        masked = _mask_pii(record)
        self.assertEqual(masked["customerId"], "c1")
        self.assertEqual(masked["email"], "***")
        self.assertEqual(masked["phone"], "***")

    def test_empty_record(self):
        self.assertEqual(_mask_pii({}), {})


class TestHandler(unittest.TestCase):
    """Tests for the Lambda handler function."""

    @patch("tools.write_review.handler._get_table")
    @patch("tools.write_review.handler.uuid.uuid4", return_value="review-uuid-1234")
    def test_creates_review_with_all_fields(self, _mock_uuid, mock_get_table):
        mock_table = MagicMock()
        mock_get_table.return_value = mock_table

        result = handler(SAMPLE_EVENT.copy(), None)

        self.assertEqual(result["reviewId"], "review-uuid-1234")
        self.assertEqual(result["status"], "pending")
        mock_table.put_item.assert_called_once()
        item = mock_table.put_item.call_args[1]["Item"]
        self.assertEqual(item["reviewId"], "review-uuid-1234")
        self.assertEqual(item["status"], "pending")
        self.assertEqual(item["confidenceScore"], 0.87)
        self.assertEqual(item["confidenceClassification"], "potential_duplicate")
        self.assertEqual(item["matchingMethod"], "rule+llm")
        self.assertEqual(item["contributingFields"], ["email", "lastName"])
        self.assertEqual(item["sourceAgent"], "intercept")
        self.assertIn("createdAt", item)
        self.assertEqual(item["incomingRecord"]["firstName"], "Chris")
        self.assertEqual(item["matchedRecord"]["customerId"], "existing-001")

    @patch("tools.write_review.handler._get_table")
    def test_high_confidence_classification(self, mock_get_table):
        mock_table = MagicMock()
        mock_get_table.return_value = mock_table

        event = SAMPLE_EVENT.copy()
        event["confidenceScore"] = 0.95
        event["confidenceClassification"] = "high_confidence"
        result = handler(event, None)

        self.assertEqual(result["status"], "pending")
        item = mock_table.put_item.call_args[1]["Item"]
        self.assertEqual(item["confidenceClassification"], "high_confidence")
        self.assertEqual(item["confidenceScore"], 0.95)

    @patch("tools.write_review.handler._get_table")
    def test_json_string_body(self, mock_get_table):
        mock_table = MagicMock()
        mock_get_table.return_value = mock_table

        event = {"body": json.dumps(SAMPLE_EVENT)}
        result = handler(event, None)

        self.assertEqual(result["status"], "pending")
        mock_table.put_item.assert_called_once()

    @patch("tools.write_review.handler._get_table")
    def test_clean_agent_source(self, mock_get_table):
        mock_table = MagicMock()
        mock_get_table.return_value = mock_table

        event = SAMPLE_EVENT.copy()
        event["sourceAgent"] = "clean"
        result = handler(event, None)

        item = mock_table.put_item.call_args[1]["Item"]
        self.assertEqual(item["sourceAgent"], "clean")

    @patch("tools.write_review.handler._get_table")
    @patch("tools.write_review.handler.uuid.uuid4", return_value="uuid-abc")
    def test_timestamp_is_iso8601(self, _mock_uuid, mock_get_table):
        mock_table = MagicMock()
        mock_get_table.return_value = mock_table

        handler(SAMPLE_EVENT.copy(), None)

        item = mock_table.put_item.call_args[1]["Item"]
        self.assertIn("T", item["createdAt"])


if __name__ == "__main__":
    unittest.main()
