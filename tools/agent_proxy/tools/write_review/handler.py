"""WriteReviewTool Lambda — writes a merge candidate to ReviewQueue for human review.

Generates a UUID for reviewId, sets status="pending" and ISO 8601 timestamps,
then performs a PutItem to the ReviewQueue DynamoDB table.

Environment variables:
    REVIEW_QUEUE_TABLE_NAME: DynamoDB table name for review queue.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TABLE_NAME = os.environ.get("REVIEW_QUEUE_TABLE_NAME", "ReviewQueue")

# Fields that contain PII — logged only as masked placeholders
_PII_FIELDS = {"email", "phone", "dateOfBirth", "address"}


def _get_table():
    """Return a DynamoDB Table resource."""
    return boto3.resource("dynamodb").Table(TABLE_NAME)


def _mask_pii(record: dict) -> dict:
    """Return a copy of *record* with PII fields replaced by '***'."""
    masked = {}
    for key, value in record.items():
        masked[key] = "***" if key in _PII_FIELDS else value
    return masked


def _convert_floats(obj):
    """Recursively convert float values to Decimal for DynamoDB compatibility."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _convert_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_convert_floats(i) for i in obj]
    return obj


def handler(event, context):
    """Lambda entry point.

    Args:
        event: dict with incomingRecord, matchedRecord, confidenceScore,
               confidenceClassification, matchingMethod, contributingFields,
               sourceAgent.
        context: Lambda context (unused).

    Returns:
        dict with reviewId and status.
    """
    # Parse input — support both direct dict and JSON-string body
    if isinstance(event, str):
        event = json.loads(event)
    body = event.get("body", event)
    if isinstance(body, str):
        body = json.loads(body)

    review_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    item = {
        "reviewId": review_id,
        "incomingRecord": _convert_floats(body["incomingRecord"]),
        "matchedRecord": _convert_floats(body["matchedRecord"]),
        "confidenceScore": Decimal(str(body["confidenceScore"])),
        "confidenceClassification": body["confidenceClassification"],
        "matchingMethod": body["matchingMethod"],
        "contributingFields": body["contributingFields"],
        "sourceAgent": body["sourceAgent"],
        "status": "pending",
        "createdAt": now,
    }

    table = _get_table()
    table.put_item(Item=item)

    # Log only non-PII fields
    logger.info(
        "WriteReviewTool reviewId=%s confidenceScore=%s classification=%s "
        "method=%s sourceAgent=%s status=pending",
        review_id,
        body["confidenceScore"],
        body["confidenceClassification"],
        body["matchingMethod"],
        body["sourceAgent"],
    )

    return {
        "reviewId": review_id,
        "status": "pending",
    }
