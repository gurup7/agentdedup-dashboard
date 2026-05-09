"""CreateCustomerTool Lambda — inserts a new customer record into CustomerTable,
or a new site record into SiteTable when partyType is "SITE".

Generates a UUID for customerId/siteId, sets status="active" and ISO 8601
timestamps, then performs a PutItem to DynamoDB.

Environment variables:
    CUSTOMER_TABLE_NAME: DynamoDB table name for customer records.
    SITE_TABLE_NAME: DynamoDB table name for site records.
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
SITE_TABLE_NAME = os.environ.get("SITE_TABLE_NAME", "SiteTable")

# Required fields for site record creation
_SITE_REQUIRED_FIELDS = ("accountNumber", "siteNumber", "addressLine1", "city", "postalCode", "country")


def _get_table():
    """Return a DynamoDB Table resource for CustomerTable."""
    dynamodb = boto3.resource("dynamodb")
    return dynamodb.Table(TABLE_NAME)


def _get_site_table():
    """Return a DynamoDB Table resource for SiteTable."""
    dynamodb = boto3.resource("dynamodb")
    return dynamodb.Table(SITE_TABLE_NAME)


def _create_site(body: dict) -> dict:
    """Create a new site record in SiteTable.

    Validates required fields, generates a UUID siteId, and writes to SiteTable.

    Args:
        body: dict with site fields.

    Returns:
        dict with siteId and status.

    Raises:
        ValueError: If required fields are missing.
    """
    # Validate required fields
    missing = [f for f in _SITE_REQUIRED_FIELDS if not body.get(f)]
    if missing:
        raise ValueError(f"Missing required site fields: {', '.join(missing)}")

    site_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    item = {
        "siteId": site_id,
        "partyType": "SITE",
        "accountNumber": body["accountNumber"],
        "accountDescription": body.get("accountDescription", ""),
        "siteNumber": body["siteNumber"],
        "operatingUnit": body.get("operatingUnit", ""),
        "purpose": body.get("purpose", ""),
        "profileClass": body.get("profileClass", ""),
        "status": "active",
        "country": body["country"],
        "addressLine1": body["addressLine1"],
        "addressLine2": body.get("addressLine2", ""),
        "city": body["city"],
        "postalCode": body["postalCode"],
        "county": body.get("county", ""),
        "sourceSystem": body.get("sourceSystem", ""),
        "createdAt": now,
        "updatedAt": now,
    }

    table = _get_site_table()
    table.put_item(Item=item)

    logger.info(
        "Created site siteId=%s accountNumber=%s siteNumber=%s status=active",
        site_id,
        body["accountNumber"],
        body["siteNumber"],
    )

    return {
        "siteId": site_id,
        "status": "created",
    }


def handler(event, context):
    """Lambda entry point.

    Args:
        event: dict with customer/site fields.
        context: Lambda context (unused).

    Returns:
        dict with customerId/siteId and status.
    """
    # Parse input — support both direct dict and JSON-string body
    if isinstance(event, str):
        event = json.loads(event)
    body = event.get("body", event)
    if isinstance(body, str):
        body = json.loads(body)

    # Determine party type and route accordingly
    party_type = body.get("partyType", "PERSON").upper()

    # --- SITE branch: write to SiteTable ---
    if party_type == "SITE":
        return _create_site(body)

    # --- PERSON / ORGANIZATION branch: write to CustomerTable ---
    customer_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    item = {
        "customerId": customer_id,
        "sourceSystem": body.get("sourceSystem", ""),
        "status": "active",
        "createdAt": now,
        "updatedAt": now,
    }

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
