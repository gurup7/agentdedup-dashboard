"""Clean Agent orchestration logic (Reactive Layer).

Same dedup pipeline as the Intercept Agent but with:
    - sourceAgent = "clean"
    - Batch progress tracking (batchId, recordIndex, totalRecords)
    - More tolerant of partial failures (logs and continues)

Tools are imported from the shared tools/ directory.
Retry logic: 3 attempts with exponential backoff (0s, 1s, 3s).
PII is masked in all log output.
"""

import logging
import time
from decimal import Decimal
from typing import Any, Optional

# Direct tool imports (prototype; replaced by AgentCore Gateway calls in Phase 5)
from tools.query_customer.handler import handler as query_customer
from tools.create_customer.handler import handler as create_customer
from tools.rule_based_match.handler import handler as rule_based_match
from tools.llm_match.handler import handler as llm_match
from tools.write_review.handler import handler as write_review
from tools.write_audit_log.handler import handler as write_audit_log

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


def _batch_ctx(batch_id: Optional[str], record_index: Optional[int],
               total_records: Optional[int]) -> str:
    """Format batch context string for log messages."""
    if batch_id:
        return f"[batch={batch_id} record={record_index}/{total_records}]"
    return "[no-batch]"


def process_record(
    record: dict,
    batch_id: Optional[str] = None,
    record_index: Optional[int] = None,
    total_records: Optional[int] = None,
) -> dict:
    """Full dedup pipeline for a single record within a batch.

    Same logic as Intercept Agent's process_register but with:
        - sourceAgent = "clean"
        - Batch progress logging
        - Partial-failure tolerance (tool errors are caught and logged;
          the record is skipped rather than aborting the entire batch)
    """
    ctx = _batch_ctx(batch_id, record_index, total_records)
    start = time.time()
    logger.info("%s process_record started: %s", ctx, _mask_pii(record))

    try:
        return _run_pipeline(record, batch_id, record_index, total_records, ctx, start)
    except Exception as exc:
        # Partial-failure tolerance: log and return error status so the batch
        # workflow can continue with the next record.
        elapsed = int((time.time() - start) * 1000)
        logger.error("%s process_record failed: %s", ctx, exc, exc_info=True)
        return {
            "status": "error",
            "error": str(exc),
            "sourceAgent": "clean",
            "batchId": batch_id,
            "recordIndex": record_index,
            "processingTimeMs": elapsed,
        }


def _run_pipeline(
    record: dict,
    batch_id: Optional[str],
    record_index: Optional[int],
    total_records: Optional[int],
    ctx: str,
    start: float,
) -> dict:
    """Core pipeline — separated so process_record can wrap with error handling."""

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
                "sourceAgent": "clean",
                "sourceSystem": record.get("sourceSystem", "unknown"),
                "confidenceScore": 0.0,
                "incomingRecordId": create_result["customerId"],
                "decision": "new_record_created",
                "rationale": "No matching candidates found in blocking query",
            },
            "WriteAuditLogTool",
        )
        elapsed = int((time.time() - start) * 1000)
        logger.info("%s new_record created id=%s", ctx, create_result["customerId"])
        return {
            "status": "new_record",
            "customerId": create_result["customerId"],
            "confidenceScore": 0.0,
            "confidenceClassification": None,
            "matchingMethod": "none",
            "sourceAgent": "clean",
            "batchId": batch_id,
            "recordIndex": record_index,
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

    matched_record = next(
        (c for c in candidates if c.get("customerId") == candidate_id), {}
    )

    # Step 5: Decision routing
    # ORGANIZATION uses cumulative thresholds (>=200 high, >=144 potential)
    # PERSON uses normalized thresholds (>=0.9 high, >=0.6 potential)
    if party_type == "ORGANIZATION":
        is_high_confidence = cumulative_score >= 200
        is_potential_duplicate = cumulative_score >= 144
        display_score = final_score
    else:
        is_high_confidence = final_score >= 0.9
        is_potential_duplicate = final_score >= 0.6
        display_score = final_score

    if is_high_confidence:
        classification = "high_confidence"
    elif is_potential_duplicate:
        classification = "potential_duplicate"
    else:
        classification = None

    if classification:
        review_payload = {
            "incomingRecord": record,
            "matchedRecord": matched_record,
            "confidenceScore": display_score,
            "confidenceClassification": classification,
            "matchingMethod": matching_method,
            "contributingFields": contributing_fields,
            "sourceAgent": "clean",
        }
        if party_type == "ORGANIZATION":
            review_payload["cumulativeScore"] = cumulative_score
        review_result = _call_tool(write_review, review_payload, "WriteReviewTool")
        _call_tool(
            write_audit_log,
            {
                "eventType": "review_routed",
                "sourceAgent": "clean",
                "sourceSystem": record.get("sourceSystem", "unknown"),
                "confidenceScore": display_score,
                "incomingRecordId": record.get("customerId", "incoming"),
                "matchedRecordId": candidate_id,
                "reviewId": review_result["reviewId"],
                "decision": classification,
                "rationale": f"Score {display_score:.4f} (cumulative={cumulative_score}) — routed as {classification}"
                if party_type == "ORGANIZATION"
                else f"Score {final_score:.4f} — routed as {classification}",
            },
            "WriteAuditLogTool",
        )
        elapsed = int((time.time() - start) * 1000)
        logger.info(
            "%s review_pending classification=%s score=%.4f cumulative=%.0f",
            ctx, classification, display_score, cumulative_score,
        )
        result = {
            "status": "review_pending",
            "reviewId": review_result["reviewId"],
            "confidenceScore": display_score,
            "confidenceClassification": classification,
            "matchingMethod": matching_method,
            "matchedRecord": matched_record,
            "sourceAgent": "clean",
            "batchId": batch_id,
            "recordIndex": record_index,
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
                "sourceAgent": "clean",
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
        logger.info(
            "%s new_record created id=%s score=%.4f",
            ctx, create_result["customerId"], display_score,
        )
        return {
            "status": "new_record",
            "customerId": create_result["customerId"],
            "confidenceScore": display_score,
            "confidenceClassification": None,
            "matchingMethod": matching_method,
            "sourceAgent": "clean",
            "batchId": batch_id,
            "recordIndex": record_index,
            "processingTimeMs": elapsed,
        }
