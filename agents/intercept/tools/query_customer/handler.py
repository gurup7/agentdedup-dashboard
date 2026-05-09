"""QueryCustomerTool Lambda — searches CustomerTable for potential duplicate matches.

Supports both PERSON and ORGANIZATION party types.

PERSON: Uses blocking strategy across GSIs (EmailIndex, PhoneIndex, PostalCodeLastNameIndex)
to reduce comparison space, then deduplicates and returns up to 10 candidates.

ORGANIZATION: Uses a scan with filter on partyType=ORGANIZATION, matching by
taxRegistrationNum, taxpayerId, or partyName (for the prototype's small dataset).
In production, this would use dedicated GSIs or Oracle EBS queries.

Environment variables:
    CUSTOMER_TABLE_NAME: DynamoDB table name for customer records.
"""

import json
import logging
import os

import boto3
from boto3.dynamodb.conditions import Attr, Key

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TABLE_NAME = os.environ.get("CUSTOMER_TABLE_NAME", "CustomerTable")


def _get_table():
    """Return a DynamoDB Table resource."""
    dynamodb = boto3.resource("dynamodb")
    return dynamodb.Table(TABLE_NAME)


def _mask_record(record: dict) -> str:
    """Return only the customerId for safe CloudWatch logging."""
    return record.get("customerId", "unknown")


def _query_email_index(table, email: str) -> list[dict]:
    """Query EmailIndex GSI for exact email match."""
    resp = table.query(
        IndexName="EmailIndex",
        KeyConditionExpression=Key("email").eq(email),
    )
    return resp.get("Items", [])


def _query_phone_index(table, phone: str) -> list[dict]:
    """Query PhoneIndex GSI for exact phone match."""
    resp = table.query(
        IndexName="PhoneIndex",
        KeyConditionExpression=Key("phone").eq(phone),
    )
    return resp.get("Items", [])


def _query_postal_code_lastname_index(table, postal_code: str, last_name: str) -> list[dict]:
    """Query PostalCodeLastNameIndex GSI for postalCode + lastName match."""
    resp = table.query(
        IndexName="PostalCodeLastNameIndex",
        KeyConditionExpression=Key("postalCode").eq(postal_code) & Key("lastName").eq(last_name),
    )
    return resp.get("Items", [])


def _scan_organizations(table, body: dict) -> tuple[list[dict], list[str]]:
    """Scan for ORGANIZATION candidates using filter expressions.

    For the prototype's small dataset, a scan with filter is acceptable.
    In production, this would use dedicated GSIs or Oracle EBS REST API queries.
    """
    candidates = []
    strategies = []

    # Build a filter for ORGANIZATION records only
    filter_expr = Attr("partyType").eq("ORGANIZATION") & Attr("status").eq("active")

    # Add narrowing filters based on available fields
    tax_reg = body.get("taxRegistrationNum")
    taxpayer_id = body.get("taxpayerId")
    party_name = body.get("partyName")
    mdr_pid = body.get("mdrPidId")
    match_market = body.get("matchMarket")

    # Strategy 1: taxRegistrationNum match
    if tax_reg:
        tax_filter = filter_expr & Attr("taxRegistrationNum").eq(tax_reg)
        resp = table.scan(FilterExpression=tax_filter)
        items = resp.get("Items", [])
        while "LastEvaluatedKey" in resp:
            resp = table.scan(FilterExpression=tax_filter, ExclusiveStartKey=resp["LastEvaluatedKey"])
            items.extend(resp.get("Items", []))
        candidates.extend(items)
        strategies.append("org_tax_registration")
        logger.info("org_tax_registration returned %d candidates", len(items))

    # Strategy 2: taxpayerId match
    if taxpayer_id:
        tp_filter = filter_expr & Attr("taxpayerId").eq(taxpayer_id)
        resp = table.scan(FilterExpression=tp_filter)
        items = resp.get("Items", [])
        while "LastEvaluatedKey" in resp:
            resp = table.scan(FilterExpression=tp_filter, ExclusiveStartKey=resp["LastEvaluatedKey"])
            items.extend(resp.get("Items", []))
        candidates.extend(items)
        strategies.append("org_taxpayer_id")
        logger.info("org_taxpayer_id returned %d candidates", len(items))

    # Strategy 3: matchMarket scan (broad — returns all orgs in same market)
    if match_market:
        mm_filter = filter_expr & Attr("matchMarket").eq(match_market)
        resp = table.scan(FilterExpression=mm_filter)
        items = resp.get("Items", [])
        while "LastEvaluatedKey" in resp:
            resp = table.scan(FilterExpression=mm_filter, ExclusiveStartKey=resp["LastEvaluatedKey"])
            items.extend(resp.get("Items", []))
        candidates.extend(items)
        strategies.append("org_match_market")
        logger.info("org_match_market returned %d candidates", len(items))

    # Fallback: if no specific filters matched, scan all orgs
    if not strategies:
        resp = table.scan(FilterExpression=filter_expr)
        items = resp.get("Items", [])
        while "LastEvaluatedKey" in resp:
            resp = table.scan(FilterExpression=filter_expr, ExclusiveStartKey=resp["LastEvaluatedKey"])
            items.extend(resp.get("Items", []))
        candidates.extend(items)
        strategies.append("org_full_scan")
        logger.info("org_full_scan returned %d candidates", len(items))

    return candidates, strategies


def _deduplicate(records: list[dict]) -> list[dict]:
    """Deduplicate records by customerId, preserving first occurrence."""
    seen = set()
    unique = []
    for record in records:
        cid = record.get("customerId")
        if cid and cid not in seen:
            seen.add(cid)
            unique.append(record)
    return unique


def handler(event, context):
    """Lambda entry point.

    Args:
        event: dict with customer fields. Checks partyType to determine strategy.
               PERSON: uses firstName, lastName, email, phone, postalCode.
               ORGANIZATION: uses partyName, taxRegistrationNum, taxpayerId, etc.
        context: Lambda context (unused).

    Returns:
        dict with candidates list, candidateCount, and blockingStrategiesUsed.
    """
    # Parse input — support both direct dict and JSON-string body
    if isinstance(event, str):
        event = json.loads(event)
    body = event.get("body", event)
    if isinstance(body, str):
        body = json.loads(body)

    # Determine party type — default to PERSON for backward compatibility
    party_type = body.get("partyType", "PERSON").upper()

    table = _get_table()
    all_candidates: list[dict] = []
    strategies_used: list[str] = []

    if party_type == "ORGANIZATION":
        logger.info(
            "QueryCustomerTool invoked for ORGANIZATION lookup (partyName=%s, taxReg=%s, taxpayerId=%s)",
            bool(body.get("partyName")),
            bool(body.get("taxRegistrationNum")),
            bool(body.get("taxpayerId")),
        )
        org_candidates, org_strategies = _scan_organizations(table, body)
        all_candidates.extend(org_candidates)
        strategies_used.extend(org_strategies)
    else:
        first_name = body.get("firstName", "")
        last_name = body.get("lastName", "")
        email = body.get("email")
        phone = body.get("phone")
        postal_code = body.get("postalCode")

        logger.info(
            "QueryCustomerTool invoked for PERSON blocking lookup (email=%s, phone=%s, postalCode=%s)",
            bool(email), bool(phone), bool(postal_code),
        )

        # Strategy 1: email exact match
        if email:
            results = _query_email_index(table, email)
            all_candidates.extend(results)
            strategies_used.append("email_exact")
            logger.info("email_exact returned %d candidate IDs: %s",
                         len(results), [_mask_record(r) for r in results])

        # Strategy 2: phone exact match
        if phone:
            results = _query_phone_index(table, phone)
            all_candidates.extend(results)
            strategies_used.append("phone_exact")
            logger.info("phone_exact returned %d candidate IDs: %s",
                         len(results), [_mask_record(r) for r in results])

        # Strategy 3: postalCode + lastName
        if postal_code and last_name:
            results = _query_postal_code_lastname_index(table, postal_code, last_name)
            all_candidates.extend(results)
            strategies_used.append("postal_code_lastname")
            logger.info("postal_code_lastname returned %d candidate IDs: %s",
                         len(results), [_mask_record(r) for r in results])

    # Deduplicate and cap at 10
    candidates = _deduplicate(all_candidates)[:10]

    logger.info("Returning %d unique candidates (IDs: %s), strategies: %s, partyType: %s",
                len(candidates), [_mask_record(c) for c in candidates], strategies_used, party_type)

    return {
        "candidates": candidates,
        "candidateCount": len(candidates),
        "blockingStrategiesUsed": strategies_used,
        "partyType": party_type,
    }
