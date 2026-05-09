"""GetReviews Lambda — queries ReviewQueue for pending reviews or a single review.

Queries the StatusIndex GSI for reviews by status (default "pending"), or
performs a direct GetItem lookup when a specific reviewId is provided.

Environment variables:
    REVIEW_QUEUE_TABLE_NAME: DynamoDB table name for review queue.
"""

import json
import logging
import os

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TABLE_NAME = os.environ.get("REVIEW_QUEUE_TABLE_NAME", "ReviewQueue")


def _get_table():
    """Return a DynamoDB Table resource."""
    return boto3.resource("dynamodb").Table(TABLE_NAME)


def handler(event, context):
    """Lambda entry point.

    Args:
        event: dict with optional status (default "pending") and optional
               reviewId for single lookup.
        context: Lambda context (unused).

    Returns:
        dict with reviews array.
    """
    # Parse input — support both direct dict and JSON-string body
    if isinstance(event, str):
        event = json.loads(event)
    body = event.get("body", event)
    if isinstance(body, str):
        body = json.loads(body)

    # Also support query string parameters (API Gateway integration)
    params = event.get("queryStringParameters") or {}
    review_id = body.get("reviewId") or params.get("reviewId")
    status = body.get("status") or params.get("status") or "pending"

    table = _get_table()

    if review_id:
        # Single review lookup by primary key
        resp = table.get_item(Key={"reviewId": review_id})
        item = resp.get("Item")
        reviews = [item] if item else []
        logger.info("GetReviews lookup reviewId=%s found=%s", review_id, bool(item))
    else:
        # Query StatusIndex for reviews by status
        resp = table.query(
            IndexName="StatusIndex",
            KeyConditionExpression=Key("status").eq(status),
        )
        reviews = resp.get("Items", [])
        logger.info("GetReviews query status=%s count=%d", status, len(reviews))

    return {
        "reviews": reviews,
    }
