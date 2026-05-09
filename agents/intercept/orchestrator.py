"""Intercept Agent orchestration logic.

Implements the full dedup pipeline for real-time record processing,
merge approval, and merge rejection. Tools are called as direct Python
function imports (prototype — AgentCore Gateway integration in Phase 5).

Retry logic: 3 attempts with exponential backoff (0s, 1s, 3s).
PII is masked in all log output.
"""

import logging
import time
from decimal import Decimal
from typing import Any

# Direct tool imports (prototype; replaced by AgentCore Gateway calls in Phase 5)
from tools.query_customer.handler import handler as query_customer
from tools.create_customer.handler import handler as create_customer
from tools.rule_based_match.handler import handler as rule_based_match
from tools.llm_match.handler import handler as llm_match
from tools.write_review.handler import handler as write_review
from tools.write_audit_log.handler import handler as write_audit_log
from tools.merge_customer.handler import handler as merge_customer

logger = logging.getLogger(__name__)

_PII_FIELDS = {"email", "phone", "dateOfBirth", "address"}
_RETRY_DELAYS = [0, 1, 3]  # seconds


def _mask_pii(data: dict) -> dict:
    """Return a shallow copy with PII fields replaced by '***'."""
    return {k: "***" if k in _PII_FIELDS else v for k, v in data.items()}


def _call_tool(tool_fn, payload: dict, tool_name: str) -> dict:
    """Invoke a tool function with retry logic (3x, exponential backoff)."""
    last_exc: Exception | None = None
    for attempt, delay in enumerate(_RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            result = tool_fn(payload, None)
            return result
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "Tool %s attempt %d failed: %s", tool_name, attempt + 1, exc
            )
    raise RuntimeError(
        f"Tool {tool_name} failed after {len(_RETRY_DELAYS)} attempts: {last_exc}"
    )


def _to_float(value: Any) -> float:
    """Safely convert Decimal or other numeric types to float."""
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def process_register(record: dict) -> dict:
    """Full dedup pipeline for a new customer record.

    Steps:
        1. QueryCustomerTool (blocking strategy)
        2. No candidates → CreateCustomerTool → audit → return "new_record"
        3. Candidates → RuleBasedMatchTool
        4. Ambiguous scores (0.4–0.9) → LLMMatchTool
        5. Decision routing based on final score
    """
    start = time.time()
    logger.info("process_register started for record: %s", _mask_pii(record))

    # Step 1: Query for candidates
    query_result = _call_tool(query_customer, record, "QueryCustomerTool")
    candidates = query_result.get("candidates", [])

    # Step 2: No candidates → new record
    if not candidates:
        create_result = _call_tool(create_customer, record, "CreateCustomerTool")
        _call_tool(
            write_audit_log,
            {
                "eventType": "new_record",
                "sourceAgent": "intercept",
                "sourceSystem": record.get("sourceSystem", "unknown"),
                "confidenceScore": 0.0,
                "incomingRecordId": create_result["customerId"],
                "decision": "new_record_created",
                "rationale": "No matching candidates found in blocking query",
            },
            "WriteAuditLogTool",
        )
        elapsed = int((time.time() - start) * 1000)
        return {
            "status": "new_record",
            "customerId": create_result["customerId"],
            "confidenceScore": 0.0,
            "confidenceClassification": None,
            "matchingMethod": "none",
            "sourceAgent": "intercept",
            "processingTimeMs": elapsed,
        }

    # Step 3: Rule-based matching
    match_result = _call_tool(
        rule_based_match,
        {"incomingRecord": record, "candidates": candidates},
        "RuleBasedMatchTool",
    )
    scored = match_result.get("results", [])

    # Step 4: LLM matching for ambiguous scores
    for item in scored:
        rb_score = _to_float(item.get("ruleBasedScore", 0.0))
        if 0.4 <= rb_score < 0.9:
            # Find the full candidate record for LLM comparison
            cand_record = next(
                (c for c in candidates if c.get("customerId") == item["candidateId"]),
                None,
            )
            if cand_record:
                llm_result = _call_tool(
                    llm_match,
                    {
                        "incomingRecord": record,
                        "candidateRecord": cand_record,
                        "ruleBasedScore": rb_score,
                    },
                    "LLMMatchTool",
                )
                item["finalScore"] = _to_float(llm_result.get("finalScore", rb_score))
                item["matchingMethod"] = llm_result.get("matchingMethod", "rule+llm")
                item["reasoning"] = llm_result.get("reasoning", "")
            else:
                item["finalScore"] = rb_score
                item["matchingMethod"] = "rule_based"
        else:
            item["finalScore"] = rb_score
            item["matchingMethod"] = "rule_based"

    # Pick the highest-scoring candidate
    # For ORGANIZATION records, use cumulative score for ranking
    party_type = record.get("partyType", "PERSON").upper()
    if party_type == "ORGANIZATION":
        best = max(scored, key=lambda x: _to_float(x.get("cumulativeScore", x.get("finalScore", 0.0))))
    else:
        best = max(scored, key=lambda x: _to_float(x.get("finalScore", 0.0)))
    final_score = _to_float(best.get("finalScore", 0.0))
    cumulative_score = _to_float(best.get("cumulativeScore", 0.0))
    matching_method = best.get("matchingMethod", "rule_based")
    candidate_id = best.get("candidateId", "")
    contributing_fields = best.get("contributingFields", [])

    # Find the full matched record for review
    matched_record = next(
        (c for c in candidates if c.get("customerId") == candidate_id), {}
    )

    # Step 5: Decision routing
    # ORGANIZATION uses cumulative thresholds (>=200 high, >=144 potential)
    # PERSON uses normalized thresholds (>=0.9 high, >=0.6 potential)
    if party_type == "ORGANIZATION":
        is_high_confidence = cumulative_score >= 200
        is_potential_duplicate = cumulative_score >= 144
        display_score = final_score  # normalized for display
    else:
        is_high_confidence = final_score >= 0.9
        is_potential_duplicate = final_score >= 0.6
        display_score = final_score

    if is_high_confidence:
        classification = "high_confidence"
        review_payload = {
            "incomingRecord": record,
            "matchedRecord": matched_record,
            "confidenceScore": display_score,
            "confidenceClassification": classification,
            "matchingMethod": matching_method,
            "contributingFields": contributing_fields,
            "sourceAgent": "intercept",
        }
        if party_type == "ORGANIZATION":
            review_payload["cumulativeScore"] = cumulative_score
        review_result = _call_tool(write_review, review_payload, "WriteReviewTool")
        _call_tool(
            write_audit_log,
            {
                "eventType": "review_routed",
                "sourceAgent": "intercept",
                "sourceSystem": record.get("sourceSystem", "unknown"),
                "confidenceScore": display_score,
                "incomingRecordId": record.get("customerId", "incoming"),
                "matchedRecordId": candidate_id,
                "reviewId": review_result["reviewId"],
                "decision": "high_confidence_duplicate",
                "rationale": f"Score {display_score:.4f} (cumulative={cumulative_score}) meets high_confidence threshold"
                if party_type == "ORGANIZATION"
                else f"Score {final_score:.4f} >= 0.9 threshold",
            },
            "WriteAuditLogTool",
        )
        elapsed = int((time.time() - start) * 1000)
        result = {
            "status": "review_pending",
            "reviewId": review_result["reviewId"],
            "confidenceScore": display_score,
            "confidenceClassification": classification,
            "matchingMethod": matching_method,
            "matchedRecord": matched_record,
            "sourceAgent": "intercept",
            "processingTimeMs": elapsed,
        }
        if party_type == "ORGANIZATION":
            result["cumulativeScore"] = cumulative_score
        return result

    elif is_potential_duplicate:
        classification = "potential_duplicate"
        review_payload = {
            "incomingRecord": record,
            "matchedRecord": matched_record,
            "confidenceScore": display_score,
            "confidenceClassification": classification,
            "matchingMethod": matching_method,
            "contributingFields": contributing_fields,
            "sourceAgent": "intercept",
        }
        if party_type == "ORGANIZATION":
            review_payload["cumulativeScore"] = cumulative_score
        review_result = _call_tool(write_review, review_payload, "WriteReviewTool")
        _call_tool(
            write_audit_log,
            {
                "eventType": "review_routed",
                "sourceAgent": "intercept",
                "sourceSystem": record.get("sourceSystem", "unknown"),
                "confidenceScore": display_score,
                "incomingRecordId": record.get("customerId", "incoming"),
                "matchedRecordId": candidate_id,
                "reviewId": review_result["reviewId"],
                "decision": "potential_duplicate",
                "rationale": f"Score {display_score:.4f} (cumulative={cumulative_score}) meets potential_duplicate threshold"
                if party_type == "ORGANIZATION"
                else f"Score {final_score:.4f} in 0.6-0.9 range",
            },
            "WriteAuditLogTool",
        )
        elapsed = int((time.time() - start) * 1000)
        result = {
            "status": "review_pending",
            "reviewId": review_result["reviewId"],
            "confidenceScore": display_score,
            "confidenceClassification": classification,
            "matchingMethod": matching_method,
            "matchedRecord": matched_record,
            "sourceAgent": "intercept",
            "processingTimeMs": elapsed,
        }
        if party_type == "ORGANIZATION":
            result["cumulativeScore"] = cumulative_score
        return result

    else:
        # Score below threshold → new record
        create_result = _call_tool(create_customer, record, "CreateCustomerTool")
        _call_tool(
            write_audit_log,
            {
                "eventType": "new_record",
                "sourceAgent": "intercept",
                "sourceSystem": record.get("sourceSystem", "unknown"),
                "confidenceScore": display_score,
                "incomingRecordId": create_result["customerId"],
                "matchedRecordId": candidate_id,
                "decision": "new_record_created",
                "rationale": f"Best score {display_score:.4f} (cumulative={cumulative_score}) below threshold"
                if party_type == "ORGANIZATION"
                else f"Best score {final_score:.4f} < 0.6 threshold",
            },
            "WriteAuditLogTool",
        )
        elapsed = int((time.time() - start) * 1000)
        return {
            "status": "new_record",
            "customerId": create_result["customerId"],
            "confidenceScore": display_score,
            "confidenceClassification": None,
            "matchingMethod": matching_method,
            "sourceAgent": "intercept",
            "processingTimeMs": elapsed,
        }


def process_approve(review_id: str, reviewed_by: str = "data_steward") -> dict:
    """Execute a merge approval for a given review.

    Calls MergeCustomerTool then WriteAuditLogTool.
    """
    logger.info("process_approve reviewId=%s reviewedBy=%s", review_id, reviewed_by)

    # Look up the review to get source/target record IDs
    import boto3, os
    table_name = os.environ.get("REVIEW_QUEUE_TABLE_NAME", "ReviewQueue")
    table = boto3.resource("dynamodb").Table(table_name)
    resp = table.get_item(Key={"reviewId": review_id})
    review = resp.get("Item")
    if not review:
        raise ValueError(f"Review not found: {review_id}")

    incoming = review.get("incomingRecord", {})
    matched = review.get("matchedRecord", {})
    source_id = incoming.get("customerId", "")
    master_id = matched.get("customerId", "")

    if not source_id or not master_id:
        raise ValueError(
            f"Review {review_id} missing record IDs: source={source_id}, master={master_id}"
        )

    merge_result = _call_tool(
        merge_customer,
        {
            "sourceRecordId": source_id,
            "targetMasterRecordId": master_id,
            "reviewId": review_id,
        },
        "MergeCustomerTool",
    )

    _call_tool(
        write_audit_log,
        {
            "eventType": "merge_approved",
            "sourceAgent": "intercept",
            "sourceSystem": incoming.get("sourceSystem", "unknown"),
            "confidenceScore": _to_float(review.get("confidenceScore", 0.0)),
            "incomingRecordId": source_id,
            "matchedRecordId": master_id,
            "reviewId": review_id,
            "reviewedBy": reviewed_by,
            "decision": "merge_approved",
            "rationale": "Data steward approved merge",
            "fieldsConsolidated": merge_result.get("fieldsConsolidated", []),
        },
        "WriteAuditLogTool",
    )

    return {
        "status": "approved",
        "reviewId": review_id,
        "mergedRecordId": merge_result["mergedRecordId"],
        "sourceRecordId": merge_result["sourceRecordId"],
        "fieldsConsolidated": merge_result.get("fieldsConsolidated", []),
        "sourceAgent": "intercept",
    }


def process_reject(review_id: str, reviewed_by: str = "data_steward") -> dict:
    """Reject a merge — update ReviewQueue status and write audit log."""
    logger.info("process_reject reviewId=%s reviewedBy=%s", review_id, reviewed_by)

    import boto3, os
    from datetime import datetime, timezone

    table_name = os.environ.get("REVIEW_QUEUE_TABLE_NAME", "ReviewQueue")
    table = boto3.resource("dynamodb").Table(table_name)

    # Read review for audit context
    resp = table.get_item(Key={"reviewId": review_id})
    review = resp.get("Item")
    if not review:
        raise ValueError(f"Review not found: {review_id}")

    now = datetime.now(timezone.utc).isoformat()

    # Update status to rejected
    table.update_item(
        Key={"reviewId": review_id},
        UpdateExpression="SET #s = :s, reviewedBy = :rb, reviewedAt = :ra",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":s": "rejected",
            ":rb": reviewed_by,
            ":ra": now,
        },
    )

    incoming = review.get("incomingRecord", {})
    matched = review.get("matchedRecord", {})

    _call_tool(
        write_audit_log,
        {
            "eventType": "merge_rejected",
            "sourceAgent": "intercept",
            "sourceSystem": incoming.get("sourceSystem", "unknown"),
            "confidenceScore": _to_float(review.get("confidenceScore", 0.0)),
            "incomingRecordId": incoming.get("customerId", ""),
            "matchedRecordId": matched.get("customerId", ""),
            "reviewId": review_id,
            "reviewedBy": reviewed_by,
            "decision": "merge_rejected",
            "rationale": "Data steward rejected merge — confirmed non-match",
        },
        "WriteAuditLogTool",
    )

    return {
        "status": "rejected",
        "reviewId": review_id,
        "sourceAgent": "intercept",
    }


# ---------------------------------------------------------------------------
# Site-Level Dedup (separate from Person/Organization)
# Sites are child records of accounts — NOT a partyType.
# ---------------------------------------------------------------------------

def process_register_site(record: dict, source_agent: str = "intercept") -> dict:
    """Site-level dedup pipeline — checks for duplicate sites within an account.

    This is a SEPARATE operation from process_register (Person/Organization).
    Sites belong to accounts; this checks if the address already exists
    within the same accountNumber.

    Args:
        record: Site record dict with accountNumber, addressLine1, etc.
        source_agent: "intercept" for real-time, "clean" for batch scan.

    Steps:
        1. QueryCustomerTool with partyType=SITE (queries SiteTable by accountNumber)
        2. No candidates → CreateCustomerTool with partyType=SITE → new site
        3. Candidates → RuleBasedMatchTool with partyType=SITE (address scoring)
        4. Decision routing based on cumulative score (120/200 thresholds)
    """
    start = time.time()
    # Ensure partyType is set for tool routing
    record["partyType"] = "SITE"
    logger.info("process_register_site started for account=%s", record.get("accountNumber"))

    # Step 1: Query for candidate sites in the same account
    query_result = _call_tool(query_customer, record, "QueryCustomerTool")
    candidates = query_result.get("candidates", [])

    # Step 2: No candidates → new site
    if not candidates:
        create_result = _call_tool(create_customer, record, "CreateCustomerTool")
        _call_tool(
            write_audit_log,
            {
                "eventType": "new_record",
                "sourceAgent": "intercept",
                "sourceSystem": record.get("sourceSystem", "unknown"),
                "confidenceScore": 0.0,
                "incomingRecordId": create_result.get("siteId", ""),
                "decision": "new_site_created",
                "rationale": "No matching sites found in account " + record.get("accountNumber", ""),
            },
            "WriteAuditLogTool",
        )
        elapsed = int((time.time() - start) * 1000)
        return {
            "status": "new_record",
            "siteId": create_result.get("siteId", ""),
            "confidenceScore": 0.0,
            "confidenceClassification": None,
            "matchingMethod": "none",
            "sourceAgent": "intercept",
            "processingTimeMs": elapsed,
        }

    # Step 3: Site scoring (address-focused)
    match_result = _call_tool(
        rule_based_match,
        {"incomingRecord": record, "candidates": candidates},
        "RuleBasedMatchTool",
    )
    scored = match_result.get("results", [])

    # Pick the highest-scoring candidate by cumulative score
    best = max(scored, key=lambda x: _to_float(x.get("cumulativeScore", x.get("finalScore", 0.0))))
    final_score = _to_float(best.get("finalScore", best.get("ruleBasedScore", 0.0)))
    cumulative_score = _to_float(best.get("cumulativeScore", 0.0))
    candidate_id = best.get("candidateId", "")
    contributing_fields = best.get("contributingFields", [])

    # Find the full matched site record
    matched_record = next(
        (c for c in candidates if c.get("siteId") == candidate_id), {}
    )

    # Step 4: Decision routing using SITE thresholds (120/200 cumulative)
    is_high_confidence = cumulative_score >= 200
    is_potential_duplicate = cumulative_score >= 120

    if is_high_confidence:
        classification = "high_confidence"
    elif is_potential_duplicate:
        classification = "potential_duplicate"
    else:
        classification = None

    if classification:
        review_result = _call_tool(
            write_review,
            {
                "incomingRecord": record,
                "matchedRecord": matched_record,
                "confidenceScore": final_score,
                "confidenceClassification": classification,
                "matchingMethod": "rule_based",
                "contributingFields": contributing_fields,
                "sourceAgent": "intercept",
                "cumulativeScore": cumulative_score,
            },
            "WriteReviewTool",
        )
        _call_tool(
            write_audit_log,
            {
                "eventType": "review_routed",
                "sourceAgent": "intercept",
                "sourceSystem": record.get("sourceSystem", "unknown"),
                "confidenceScore": final_score,
                "incomingRecordId": record.get("siteNumber", "incoming"),
                "matchedRecordId": candidate_id,
                "reviewId": review_result["reviewId"],
                "decision": f"site_{classification}",
                "rationale": f"Site score {final_score:.4f} (cumulative={cumulative_score}) in account {record.get('accountNumber', '')}",
            },
            "WriteAuditLogTool",
        )
        elapsed = int((time.time() - start) * 1000)
        return {
            "status": "review_pending",
            "reviewId": review_result["reviewId"],
            "confidenceScore": final_score,
            "cumulativeScore": cumulative_score,
            "confidenceClassification": classification,
            "matchingMethod": "rule_based",
            "matchedRecord": matched_record,
            "sourceAgent": "intercept",
            "processingTimeMs": elapsed,
        }
    else:
        # Score below threshold → new site
        create_result = _call_tool(create_customer, record, "CreateCustomerTool")
        _call_tool(
            write_audit_log,
            {
                "eventType": "new_record",
                "sourceAgent": "intercept",
                "sourceSystem": record.get("sourceSystem", "unknown"),
                "confidenceScore": final_score,
                "incomingRecordId": create_result.get("siteId", ""),
                "matchedRecordId": candidate_id,
                "decision": "new_site_created",
                "rationale": f"Best site score {final_score:.4f} (cumulative={cumulative_score}) below 120 threshold",
            },
            "WriteAuditLogTool",
        )
        elapsed = int((time.time() - start) * 1000)
        return {
            "status": "new_record",
            "siteId": create_result.get("siteId", ""),
            "confidenceScore": final_score,
            "cumulativeScore": cumulative_score,
            "confidenceClassification": None,
            "matchingMethod": "rule_based",
            "sourceAgent": "intercept",
            "processingTimeMs": elapsed,
        }
