"""Unit tests for GetReviews Lambda handler.

Uses unittest.mock to patch boto3 DynamoDB interactions.
"""

import json
import os
import unittest
from unittest.mock import MagicMock, patch

# Set env var before importing handler
os.environ["REVIEW_QUEUE_TABLE_NAME"] = "TestReviewQueue"

from tools.get_reviews.handler import handler


SAMPLE_REVIEW = {
    "reviewId": "rev-001",
    "incomingRecord": {"firstName": "Chris", "lastName": "James"},
    "matchedRecord": {"customerId": "c-001", "firstName": "Chrish"},
    "confidenceScore": 0.87,
    "confidenceClassification": "potential_duplicate",
    "matchingMethod": "rule+llm",
    "status": "pending",
    "createdAt": "2024-07-01T00:00:00+00:00",
}


class TestHandler(unittest.TestCase):
    """Tests for the Lambda handler function."""

    @patch("tools.get_reviews.handler._get_table")
    def test_queries_pending_reviews_by_default(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": [SAMPLE_REVIEW]}
        mock_get_table.return_value = mock_table

        result = handler({}, None)

        self.assertEqual(len(result["reviews"]), 1)
        self.assertEqual(result["reviews"][0]["reviewId"], "rev-001")
        mock_table.query.assert_called_once()
        call_kwargs = mock_table.query.call_args[1]
        self.assertEqual(call_kwargs["IndexName"], "StatusIndex")

    @patch("tools.get_reviews.handler._get_table")
    def test_queries_by_custom_status(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": []}
        mock_get_table.return_value = mock_table

        result = handler({"status": "approved"}, None)

        self.assertEqual(result["reviews"], [])
        mock_table.query.assert_called_once()

    @patch("tools.get_reviews.handler._get_table")
    def test_single_review_lookup_by_id(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": SAMPLE_REVIEW}
        mock_get_table.return_value = mock_table

        result = handler({"reviewId": "rev-001"}, None)

        self.assertEqual(len(result["reviews"]), 1)
        self.assertEqual(result["reviews"][0]["reviewId"], "rev-001")
        mock_table.get_item.assert_called_once_with(Key={"reviewId": "rev-001"})
        mock_table.query.assert_not_called()

    @patch("tools.get_reviews.handler._get_table")
    def test_single_review_not_found(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_get_table.return_value = mock_table

        result = handler({"reviewId": "nonexistent"}, None)

        self.assertEqual(result["reviews"], [])

    @patch("tools.get_reviews.handler._get_table")
    def test_query_string_parameters(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": SAMPLE_REVIEW}
        mock_get_table.return_value = mock_table

        event = {
            "queryStringParameters": {"reviewId": "rev-001"},
        }
        result = handler(event, None)

        self.assertEqual(len(result["reviews"]), 1)
        mock_table.get_item.assert_called_once_with(Key={"reviewId": "rev-001"})

    @patch("tools.get_reviews.handler._get_table")
    def test_json_string_body(self, mock_get_table):
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": [SAMPLE_REVIEW]}
        mock_get_table.return_value = mock_table

        event = {"body": json.dumps({"status": "pending"})}
        result = handler(event, None)

        self.assertEqual(len(result["reviews"]), 1)


if __name__ == "__main__":
    unittest.main()
