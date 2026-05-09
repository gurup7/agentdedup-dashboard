"""CreateCustomerTool Lambda — inserts a new customer record into CustomerTable.

Generates a UUID for customerId, sets status="active" and ISO 8601 timestamps,
then performs a PutItem to DynamoDB.

Environment variables:
    CUSTOMER_TABLE_NAME: DynamoDB table name for customer records.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TABLE_NAME = os.environ.get("CUSTOMER_TABLE_NAME", "CustomerTable")


def _get_table():
    """Return a DynamoDB Table resource."""
    dynamodb = boto3.resource("dynamodb")
    return dynamodb.Table(TABLE_NAME)


def handler(event, context):
    """Lambda entry point.

    Args:
        event: dict with customer fields (firstName, lastName, email, phone,
               dateOfBirth, address, sourceSystem).
        context: Lambda context (unused).

    Returns:
        dict with customerId and status.
    """
    # Parse input — support both direct dict and JSON-string body
    if isinstance(event, str):
        event = json.loads(event)
    body = event.get("body", event)
    if isinstance(body, str):
        body = json.loads(body)

    customer_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    item = {
        "customerId": customer_id,
        "sourceSystem": body.get("sourceSystem", ""),
        "status": "active",
        "createdAt": now,
        "updatedAt": now,
    }

    # Determine party type
    party_type = body.get("partyType", "PERSON").upper()
    if party_type == "ORGANIZATION":
        item["partyType"] = "ORGANIZATION"
        if body.get("partyName"):
            item["partyName"] = body["partyName"]
    else:
        item["firstName"] = body.get("firstName", "")
        item["lastName"] = body.get("lastName", "")

    # Optional fields — only include if provided
    for field in ("email", "phone", "dateOfBirth"):
        if body.get(field):
            item[field] = body[field]

    # Organization-specific optional fields
    for field in ("taxRegistrationNum", "taxpayerId", "mdrPidId", "matchMarket", "province"):
        if body.get(field):
            item[field] = body[field]

    if body.get("address"):
        item["address"] = body["address"]

    # Extract postalCode to top level for GSI (PostalCodeLastNameIndex)
    if isinstance(body.get("address"), dict) and body["address"].get("postalCode"):
        item["postalCode"] = body["address"]["postalCode"]

    table = _get_table()
    table.put_item(Item=item)

    # Log only non-PII fields
    logger.info(
        "Created customer customerId=%s sourceSystem=%s status=active",
        customer_id,
        body.get("sourceSystem", ""),
    )

    return {
        "customerId": customer_id,
        "status": "created",
    }
