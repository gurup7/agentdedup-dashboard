"""MergeCustomerTool Lambda — merges duplicate customer records after human approval.

Reads source and master records from CustomerTable, consolidates fields (preferring
the most recent data), marks the source as merged, updates the master with consolidated
data, and updates the ReviewQueue status to approved.  NO records are deleted.

Environment variables:
    CUSTOMER_TABLE_NAME: DynamoDB table name for customer records.
    REVIEW_QUEUE_TABLE_NAME: DynamoDB table name for review queue.
"""

import json
import logging
import os
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

CUSTOMER_TABLE_NAME = os.environ.get("CUSTOMER_TABLE_NAME", "CustomerTable")
REVIEW_QUEUE_TABLE_NAME = os.environ.get("REVIEW_QUEUE_TABLE_NAME", "ReviewQueue")

# Fields that contain PII — logged only as masked placeholders
_PII_FIELDS = {"email", "phone", "dateOfBirth", "address"}

# Fields eligible for consolidation from source into master
_CONSOLIDATION_FIELDS = (
    "email", "phone", "dateOfBirth", "address", "postalCode",
)


def _get_customer_table():
    """Return a DynamoDB Table resource for CustomerTable."""
    return boto3.resource("dynamodb").Table(CUSTOMER_TABLE_NAME)


def _get_review_table():
    """Return a DynamoDB Table resource for ReviewQueue."""
    return boto3.resource("dynamodb").Table(REVIEW_QUEUE_TABLE_NAME)


def _mask_pii(record: dict) -> dict:
    """Return a copy of *record* with PII fields replaced by '***'."""
    masked = {}
    for key, value in record.items():
        masked[key] = "***" if key in _PII_FIELDS else value
    return masked


def _pick_newer(source: dict, master: dict) -> dict:
    """Determine which record was updated more recently.

    Returns the record with the later ``updatedAt`` value, falling back to
    *source* when timestamps are equal or missing.
    """
    source_ts = source.get("updatedAt", "")
    master_ts = master.get("updatedAt", "")
    if master_ts >= source_ts:
        return master
    return source


def _consolidate(source: dict, master: dict) -> tuple[dict, list[str]]:
    """Merge fields from *source* into *master*, preferring the most recent.

    Returns a tuple of (consolidated updates dict, list of field names that
    were consolidated from the source record).
    """
    newer = _pick_newer(source, master)
    updates: dict = {}
    fields_consolidated: list[str] = []

    for field in _CONSOLIDATION_FIELDS:
        source_val = source.get(field)
        master_val = master.get(field)

        if source_val and not master_val:
            # Master is missing this field — take from source
            updates[field] = source_val
            fields_consolidated.append(field)
        elif source_val and master_val and newer is source:
            # Both have the field but source is newer — prefer source
            updates[field] = source_val
            fields_consolidated.append(field)

    return updates, fields_consolidated


def handler(event, context):
    """Lambda entry point.

    Args:
        event: dict with sourceRecordId, targetMasterRecordId, reviewId.
        context: Lambda context (unused).

    Returns:
        dict with mergedRecordId, sourceRecordId, fieldsConsolidated.
    """
    # Parse input — support both direct dict and JSON-string body
    if isinstance(event, str):
        event = json.loads(event)
    body = event.get("body", event)
    if isinstance(body, str):
        body = json.loads(body)

    source_id = body["sourceRecordId"]
    master_id = body["targetMasterRecordId"]
    review_id = body["reviewId"]

    logger.info(
        "MergeCustomerTool invoked sourceRecordId=%s targetMasterRecordId=%s reviewId=%s",
        source_id, master_id, review_id,
    )

    customer_table = _get_customer_table()
    now = datetime.now(timezone.utc).isoformat()

    # 1. Read both records
    source_resp = customer_table.get_item(Key={"customerId": source_id})
    master_resp = customer_table.get_item(Key={"customerId": master_id})
    source_record = source_resp.get("Item")
    master_record = master_resp.get("Item")

    if not source_record:
        raise ValueError(f"Source record not found: {source_id}")
    if not master_record:
        raise ValueError(f"Master record not found: {master_id}")

    logger.info("Source record (masked): %s", _mask_pii(source_record))
    logger.info("Master record (masked): %s", _mask_pii(master_record))

    # 2. Consolidate fields
    updates, fields_consolidated = _consolidate(source_record, master_record)

    # 3. Update source record — mark as merged
    customer_table.update_item(
        Key={"customerId": source_id},
        UpdateExpression="SET #s = :s, mergedInto = :m, updatedAt = :u",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":s": "merged",
            ":m": master_id,
            ":u": now,
        },
    )

    # 4. Update master record with consolidated fields
    if updates:
        expr_parts = ["updatedAt = :u"]
        attr_values = {":u": now}
        attr_names = {}
        for i, (field, value) in enumerate(updates.items()):
            placeholder = f":v{i}"
            name_placeholder = f"#f{i}"
            expr_parts.append(f"{name_placeholder} = {placeholder}")
            attr_values[placeholder] = value
            attr_names[name_placeholder] = field
        customer_table.update_item(
            Key={"customerId": master_id},
            UpdateExpression="SET " + ", ".join(expr_parts),
            ExpressionAttributeNames=attr_names,
            ExpressionAttributeValues=attr_values,
        )
    else:
        customer_table.update_item(
            Key={"customerId": master_id},
            UpdateExpression="SET updatedAt = :u",
            ExpressionAttributeValues={":u": now},
        )

    # 5. Update ReviewQueue — mark as approved
    review_table = _get_review_table()
    review_table.update_item(
        Key={"reviewId": review_id},
        UpdateExpression="SET #s = :s, reviewedAt = :r",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":s": "approved",
            ":r": now,
        },
    )

    logger.info(
        "Merge complete mergedRecordId=%s sourceRecordId=%s fieldsConsolidated=%s",
        master_id, source_id, fields_consolidated,
    )

    return {
        "mergedRecordId": master_id,
        "sourceRecordId": source_id,
        "fieldsConsolidated": fields_consolidated,
    }
