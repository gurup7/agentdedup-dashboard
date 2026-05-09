"""Unit tests for WriteAuditLogTool Lambda handler.

Uses unittest.mock to patch boto3 S3 interactions.
"""

import json
import os
import unittest
from unittest.mock import MagicMock, patch

# Set env var before importing handler
os.environ["AUDIT_LOGS_BUCKET"] = "test-audit-bucket"

from tools.write_audit_log.handler import handler


SAMPLE_EVENT = {
    "eventType": "match_recommendation",
    "sourceAgent": "intercept",
    "sourceSystem": "OneCRM",
    "confidenceScore": 0.87,
    "incomingRecordId": "incoming-001",
    "matchedRecordId": "existing-001",
    "reviewId": "review-001",
    "decision": "routed_to_review",
    "rationale": "Potential duplicate detected with 0.87 confidence",
}


class TestHandler(unittest.TestCase):
    """Tests for the Lambda handler function."""

    @patch("tools.write_audit_log.handler._get_s3_client")
    def test_writes_audit_log_to_s3(self, mock_get_s3):
        mock_s3 = MagicMock()
        mock_get_s3.return_value = mock_s3

        result = handler(SAMPLE_EVENT.copy(), None)

        self.assertIn("auditLogKey", result)
        self.assertIn("timestamp", result)
        self.assertIn("audit-logs/", result["auditLogKey"])
        self.assertTrue(result["auditLogKey"].endswith("-match_recommendation.json"))
        mock_s3.put_object.assert_called_once()

    @patch("tools.write_audit_log.handler._get_s3_client")
    def test_s3_key_date_partitioned(self, mock_get_s3):
        mock_s3 = MagicMock()
        mock_get_s3.return_value = mock_s3

        result = handler(SAMPLE_EVENT.copy(), None)

        key = result["auditLogKey"]
        # Key format: audit-logs/{YYYY}/{MM}/{DD}/{timestamp}-{eventType}.json
        parts = key.split("/")
        self.assertEqual(parts[0], "audit-logs")
        self.assertEqual(len(parts[1]), 4)  # YYYY
        self.assertEqual(len(parts[2]), 2)  # MM
        self.assertEqual(len(parts[3]), 2)  # DD

    @patch("tools.write_audit_log.handler._get_s3_client")
    def test_s3_body_contains_required_fields(self, mock_get_s3):
        mock_s3 = MagicMock()
        mock_get_s3.return_value = mock_s3

        handler(SAMPLE_EVENT.copy(), None)

        call_kwargs = mock_s3.put_object.call_args[1]
        self.assertEqual(call_kwargs["Bucket"], "test-audit-bucket")
        self.assertEqual(call_kwargs["ContentType"], "application/json")
        body = json.loads(call_kwargs["Body"])
        self.assertIn("auditId", body)
        self.assertEqual(body["eventType"], "match_recommendation")
        self.assertEqual(body["sourceAgent"], "intercept")
        self.assertEqual(body["confidenceScore"], 0.87)
        self.assertEqual(body["matchedRecordId"], "existing-001")
        self.assertEqual(body["reviewId"], "review-001")

    @patch("tools.write_audit_log.handler._get_s3_client")
    def test_optional_fields_omitted_when_absent(self, mock_get_s3):
        mock_s3 = MagicMock()
        mock_get_s3.return_value = mock_s3

        event = {
            "eventType": "new_record",
            "sourceAgent": "intercept",
            "sourceSystem": "NES",
            "confidenceScore": 0.3,
            "incomingRecordId": "incoming-002",
            "decision": "created_new_record",
            "rationale": "No duplicates found",
        }
        handler(event, None)

        body = json.loads(mock_s3.put_object.call_args[1]["Body"])
        self.assertNotIn("matchedRecordId", body)
        self.assertNotIn("reviewId", body)
        self.assertNotIn("reviewedBy", body)
        self.assertNotIn("fieldsConsolidated", body)

    @patch("tools.write_audit_log.handler._get_s3_client")
    def test_json_string_body(self, mock_get_s3):
        mock_s3 = MagicMock()
        mock_get_s3.return_value = mock_s3

        event = {"body": json.dumps(SAMPLE_EVENT)}
        result = handler(event, None)

        self.assertIn("auditLogKey", result)
        mock_s3.put_object.assert_called_once()

    @patch("tools.write_audit_log.handler._get_s3_client")
    def test_timestamp_is_iso8601(self, mock_get_s3):
        mock_s3 = MagicMock()
        mock_get_s3.return_value = mock_s3

        result = handler(SAMPLE_EVENT.copy(), None)

        self.assertIn("T", result["timestamp"])


if __name__ == "__main__":
    unittest.main()
