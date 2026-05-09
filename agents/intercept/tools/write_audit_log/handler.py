"""WriteAuditLogTool Lambda — writes structured audit log entries to S3.

Formats the audit event as JSON and writes to the audit-logs S3 bucket with a
date-partitioned key: audit-logs/{YYYY}/{MM}/{DD}/{timestamp}-{eventType}.json

Environment variables:
    AUDIT_LOGS_BUCKET: S3 bucket name for audit logs.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

BUCKET_NAME = os.environ.get("AUDIT_LOGS_BUCKET", "dedup-audit-logs")

# Fields that contain PII — logged only as masked placeholders
_PII_FIELDS = {"email", "phone", "dateOfBirth", "address"}


def _get_s3_client():
    """Return an S3 client."""
    return boto3.client("s3")


def handler(event, context):
    """Lambda entry point.

    Args:
        event: dict with eventType, sourceAgent, sourceSystem, confidenceScore,
               incomingRecordId, decision, rationale, and optional matchedRecordId,
               reviewId, reviewedBy, fieldsConsolidated.
        context: Lambda context (unused).

    Returns:
        dict with auditLogKey and timestamp.
    """
    # Parse input — support both direct dict and JSON-string body
    if isinstance(event, str):
        event = json.loads(event)
    body = event.get("body", event)
    if isinstance(body, str):
        body = json.loads(body)

    now = datetime.now(timezone.utc)
    timestamp = now.isoformat()
    audit_id = str(uuid.uuid4())

    audit_entry = {
        "auditId": audit_id,
        "timestamp": timestamp,
        "eventType": body["eventType"],
        "sourceAgent": body["sourceAgent"],
        "sourceSystem": body["sourceSystem"],
        "confidenceScore": body["confidenceScore"],
        "incomingRecordId": body["incomingRecordId"],
        "decision": body["decision"],
        "rationale": body["rationale"],
    }

    # Optional fields — only include if provided
    for field in ("matchedRecordId", "reviewId", "reviewedBy", "fieldsConsolidated"):
        if body.get(field) is not None:
            audit_entry[field] = body[field]

    # Build S3 key: audit-logs/{YYYY}/{MM}/{DD}/{timestamp}-{eventType}.json
    s3_key = (
        f"audit-logs/{now.strftime('%Y')}/{now.strftime('%m')}/"
        f"{now.strftime('%d')}/{now.strftime('%Y%m%dT%H%M%S')}-{body['eventType']}.json"
    )

    s3_client = _get_s3_client()
    s3_client.put_object(
        Bucket=BUCKET_NAME,
        Key=s3_key,
        Body=json.dumps(audit_entry, default=str),
        ContentType="application/json",
    )

    # Log only non-PII fields
    logger.info(
        "WriteAuditLogTool auditId=%s eventType=%s sourceAgent=%s "
        "confidenceScore=%s decision=%s key=%s",
        audit_id,
        body["eventType"],
        body["sourceAgent"],
        body["confidenceScore"],
        body["decision"],
        s3_key,
    )

    return {
        "auditLogKey": s3_key,
        "timestamp": timestamp,
    }
