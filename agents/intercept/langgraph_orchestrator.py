"""Intercept Agent — LangGraph-based agentic orchestrator.

Uses LangGraph StateGraph with Bedrock Claude to dynamically decide which
tools to call and in what order.  The LLM follows the dedup pipeline via a
detailed system prompt and tool docstrings.

The existing orchestrator.py is preserved as a backup / fallback.
"""

import json
import logging
import os
import time
from decimal import Decimal
from typing import Annotated, Any, Optional, Sequence

from langchain_aws import ChatBedrock
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import tool
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

# Direct tool imports — same handlers the current orchestrator uses
from tools.query_customer.handler import handler as _query_customer_handler
from tools.create_customer.handler import handler as _create_customer_handler
from tools.rule_based_match.handler import handler as _rule_based_match_handler
from tools.llm_match.handler import handler as _llm_match_handler
from tools.write_review.handler import handler as _write_review_handler
from tools.write_audit_log.handler import handler as _write_audit_log_handler
from tools.merge_customer.handler import handler as _merge_customer_handler

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bedrock LLM
# ---------------------------------------------------------------------------

_model: ChatBedrock | None = None


def _get_model() -> ChatBedrock:
    """Lazy-initialise the ChatBedrock model (singleton)."""
    global _model
    if _model is None:
        _model = ChatBedrock(
            model_id=os.environ.get(
                "BEDROCK_MODEL_ID",
                "anthropic.claude-3-sonnet-20240229-v1:0",
            ),
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )
    return _model


# ---------------------------------------------------------------------------
# Helper: safe JSON serialisation (handles Decimal, etc.)
# ---------------------------------------------------------------------------

class _DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)


def _safe_json(obj: Any) -> str:
    return json.dumps(obj, cls=_DecimalEncoder, default=str)


# ---------------------------------------------------------------------------
# LangChain @tool wrappers — call existing Lambda handlers directly
# ---------------------------------------------------------------------------

@tool
def query_customer_tool(
    firstName: str,
    lastName: str,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    postalCode: Optional[str] = None,
) -> str:
    """Search the CustomerTable for potential duplicate matches using blocking strategies.

    Uses GSI lookups (email exact, phone exact, postalCode+lastName) to find
    candidate records.  Returns up to 10 deduplicated candidates.

    Call this FIRST for every new customer record to check for existing matches.

    Args:
        firstName: Customer first name.
        lastName: Customer last name.
        email: Customer email address (optional).
        phone: Customer phone number (optional).
        postalCode: Customer postal code for blocking strategy (optional).
    """
    payload = {
        "firstName": firstName,
        "lastName": lastName,
    }
    if email:
        payload["email"] = email
    if phone:
        payload["phone"] = phone
    if postalCode:
        payload["postalCode"] = postalCode
    result = _query_customer_handler(payload, None)
    return _safe_json(result)


@tool
def rule_based_match_tool(incoming_record: str, candidates: str) -> str:
    """Run deterministic rule-based matching (Stage 1) between an incoming record and candidates.

    Computes scores using exact email/phone match, Jaro-Winkler on names,
    Soundex, and date-of-birth comparison.  Each candidate gets a ruleBasedScore
    between 0.0 and 1.0.

    Call this AFTER query_customer_tool returns candidates.

    Args:
        incoming_record: JSON string of the incoming customer record.
        candidates: JSON string array of candidate records from query_customer_tool.
    """
    payload = {
        "incomingRecord": json.loads(incoming_record),
        "candidates": json.loads(candidates),
    }
    result = _rule_based_match_handler(payload, None)
    return _safe_json(result)


@tool
def llm_match_tool(
    incoming_record: str,
    candidate_record: str,
    rule_based_score: float,
) -> str:
    """Run LLM-based fuzzy matching (Stage 2) for ambiguous cases.

    Only call this when the rule-based score is between 0.4 and 0.9.
    Combines the rule-based score (60 %) with an LLM confidence score (40 %)
    to produce a finalScore.

    Args:
        incoming_record: JSON string of the incoming customer record.
        candidate_record: JSON string of the candidate record to compare.
        rule_based_score: The rule-based score (0.0–1.0) from rule_based_match_tool.
    """
    payload = {
        "incomingRecord": json.loads(incoming_record),
        "candidateRecord": json.loads(candidate_record),
        "ruleBasedScore": rule_based_score,
    }
    result = _llm_match_handler(payload, None)
    return _safe_json(result)


@tool
def create_customer_tool(
    firstName: str,
    lastName: str,
    sourceSystem: str,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    dateOfBirth: Optional[str] = None,
    address: Optional[str] = None,
) -> str:
    """Create a new customer record in the CustomerTable.

    Call this when the final confidence score is below 0.6 (no duplicate found)
    or when no candidates were returned by query_customer_tool.

    Args:
        firstName: Customer first name.
        lastName: Customer last name.
        sourceSystem: Origin system (e.g. OneCRM, NES).
        email: Customer email (optional).
        phone: Customer phone (optional).
        dateOfBirth: Date of birth YYYY-MM-DD (optional).
        address: JSON string of address object (optional).
    """
    payload: dict[str, Any] = {
        "firstName": firstName,
        "lastName": lastName,
        "sourceSystem": sourceSystem,
    }
    if email:
        payload["email"] = email
    if phone:
        payload["phone"] = phone
    if dateOfBirth:
        payload["dateOfBirth"] = dateOfBirth
    if address:
        payload["address"] = json.loads(address) if isinstance(address, str) else address
    result = _create_customer_handler(payload, None)
    return _safe_json(result)


@tool
def write_review_tool(
    incoming_record: str,
    matched_record: str,
    confidence_score: float,
    confidence_classification: str,
    matching_method: str,
    contributing_fields: str,
    source_agent: str = "intercept",
) -> str:
    """Write a merge candidate to the ReviewQueue for human review.

    Call this when the final confidence score is >= 0.6.
    Classification: 'high_confidence' (>= 0.9) or 'potential_duplicate' (0.6–0.9).

    Args:
        incoming_record: JSON string of the incoming customer record.
        matched_record: JSON string of the best-matching candidate record.
        confidence_score: Final confidence score (0.0–1.0).
        confidence_classification: 'high_confidence' or 'potential_duplicate'.
        matching_method: 'rule_based' or 'rule+llm'.
        contributing_fields: JSON string array of field names that contributed to the score.
        source_agent: 'intercept' or 'clean'.
    """
    payload = {
        "incomingRecord": json.loads(incoming_record),
        "matchedRecord": json.loads(matched_record),
        "confidenceScore": confidence_score,
        "confidenceClassification": confidence_classification,
        "matchingMethod": matching_method,
        "contributingFields": json.loads(contributing_fields),
        "sourceAgent": source_agent,
    }
    result = _write_review_handler(payload, None)
    return _safe_json(result)


@tool
def write_audit_log_tool(
    event_type: str,
    source_agent: str,
    source_system: str,
    confidence_score: float,
    decision: str,
    rationale: str,
    incoming_record_id: Optional[str] = None,
    matched_record_id: Optional[str] = None,
    review_id: Optional[str] = None,
    reviewed_by: Optional[str] = None,
    fields_consolidated: Optional[str] = None,
) -> str:
    """Write an audit log entry to S3.

    ALWAYS call this as the LAST step of every pipeline execution.
    Every decision (new_record, review_routed, merge_approved, merge_rejected)
    must be audited.

    Args:
        event_type: One of 'new_record', 'review_routed', 'match_recommendation',
                    'merge_approved', 'merge_rejected'.
        source_agent: 'intercept' or 'clean'.
        source_system: Origin system (e.g. OneCRM, NES, unknown).
        confidence_score: Final confidence score.
        decision: Short description of the decision taken.
        rationale: Explanation of why this decision was made.
        incoming_record_id: Customer ID of the incoming record (optional).
        matched_record_id: Customer ID of the matched record (optional).
        review_id: Review ID if a review was created (optional).
        reviewed_by: Reviewer identifier if human action (optional).
        fields_consolidated: JSON string array of consolidated field names (optional).
    """
    payload: dict[str, Any] = {
        "eventType": event_type,
        "sourceAgent": source_agent,
        "sourceSystem": source_system,
        "confidenceScore": confidence_score,
        "decision": decision,
        "rationale": rationale,
    }
    if incoming_record_id:
        payload["incomingRecordId"] = incoming_record_id
    if matched_record_id:
        payload["matchedRecordId"] = matched_record_id
    if review_id:
        payload["reviewId"] = review_id
    if reviewed_by:
        payload["reviewedBy"] = reviewed_by
    if fields_consolidated:
        payload["fieldsConsolidated"] = json.loads(fields_consolidated)
    result = _write_audit_log_handler(payload, None)
    return _safe_json(result)


@tool
def merge_customer_tool(
    source_record_id: str,
    target_master_record_id: str,
    review_id: str,
) -> str:
    """Merge a duplicate source record into the master record after human approval.

    This consolidates fields from the source into the master, marks the source
    as 'merged', and updates the ReviewQueue status to 'approved'.
    NO records are deleted.

    Only call this during an 'approve' action after a Data Steward approves a review.

    Args:
        source_record_id: Customer ID of the source (duplicate) record.
        target_master_record_id: Customer ID of the master record to merge into.
        review_id: The review ID being approved.
    """
    payload = {
        "sourceRecordId": source_record_id,
        "targetMasterRecordId": target_master_record_id,
        "reviewId": review_id,
    }
    result = _merge_customer_handler(payload, None)
    return _safe_json(result)


# ---------------------------------------------------------------------------
# All tools list
# ---------------------------------------------------------------------------

ALL_TOOLS = [
    query_customer_tool,
    rule_based_match_tool,
    llm_match_tool,
    create_customer_tool,
    write_review_tool,
    write_audit_log_tool,
    merge_customer_tool,
]

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are the Intercept Agent — a real-time customer data deduplication agent.
Your sourceAgent identifier is "intercept".

You have access to the following tools and MUST follow this pipeline precisely:

## REGISTER Pipeline (new customer record)

1. **Always start** by calling `query_customer_tool` with the customer's fields
   (firstName, lastName, and any available email, phone, postalCode).

2. If `query_customer_tool` returns 0 candidates:
   - Call `create_customer_tool` to create a new record.
   - Call `write_audit_log_tool` with event_type="new_record", confidence_score=0.0.
   - Return the result.

3. If candidates are found:
   - Call `rule_based_match_tool` with the incoming record and candidates.
   - Examine each candidate's ruleBasedScore.

4. For any candidate with a ruleBasedScore between 0.4 and 0.9 (ambiguous):
   - Call `llm_match_tool` with that candidate to get a refined finalScore.
   - For scores outside 0.4–0.9, use the ruleBasedScore as the finalScore.

5. Pick the candidate with the highest finalScore and apply decision routing:
   - **finalScore >= 0.9** → high_confidence duplicate.
     Call `write_review_tool` with confidence_classification="high_confidence".
   - **finalScore >= 0.6 but < 0.9** → potential_duplicate.
     Call `write_review_tool` with confidence_classification="potential_duplicate".
   - **finalScore < 0.6** → not a duplicate.
     Call `create_customer_tool` to create a new record.

6. **Always** call `write_audit_log_tool` as the LAST step with the appropriate
   event_type and all relevant IDs.

## APPROVE Pipeline (merge approval)

1. Call `merge_customer_tool` with the source_record_id, target_master_record_id,
   and review_id provided.
2. Call `write_audit_log_tool` with event_type="merge_approved".

## REJECT Pipeline (merge rejection)

1. The rejection has already been written to the ReviewQueue by the caller.
2. Call `write_audit_log_tool` with event_type="merge_rejected".

## Confidence Thresholds
- >= 0.9  → high_confidence
- 0.6–0.9 → potential_duplicate
- < 0.6   → new_record

## Rules
- NEVER auto-merge records. All merges require human approval via the review queue.
- Always set source_agent="intercept" in write_review_tool and write_audit_log_tool.
- Always write an audit log — no pipeline execution should end without one.
- Return your final answer as a JSON object with the pipeline result.
"""

# ---------------------------------------------------------------------------
# LangGraph State
# ---------------------------------------------------------------------------

class DedupState(TypedDict):
    """State for the dedup LangGraph agent."""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    customer_record: dict
    candidates: list
    match_results: list
    final_decision: str
    source_agent: str


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------

def llm_call(state: DedupState) -> dict:
    """Invoke the LLM with the current messages and bound tools."""
    model = _get_model()
    model_with_tools = model.bind_tools(ALL_TOOLS)
    response = model_with_tools.invoke(state["messages"])
    return {"messages": [response]}


def should_continue(state: DedupState) -> str:
    """Route to tool_node if the last message has tool calls, else END."""
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tool_node"
    return END


# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------

def _build_graph() -> StateGraph:
    """Construct and compile the LangGraph agent."""
    tool_node = ToolNode(ALL_TOOLS)

    graph = StateGraph(DedupState)
    graph.add_node("llm_call", llm_call)
    graph.add_node("tool_node", tool_node)

    graph.set_entry_point("llm_call")
    graph.add_conditional_edges("llm_call", should_continue, {
        "tool_node": "tool_node",
        END: END,
    })
    graph.add_edge("tool_node", "llm_call")

    return graph.compile()


# Compile once at module level
_agent = _build_graph()


# ---------------------------------------------------------------------------
# Helper: extract final result from agent messages
# ---------------------------------------------------------------------------

def _extract_result(messages: Sequence[BaseMessage]) -> dict:
    """Walk messages in reverse to find the final JSON result from the LLM."""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            # Try to parse JSON from the content
            try:
                # Look for JSON block in the response
                if "```json" in content:
                    json_str = content.split("```json")[1].split("```")[0].strip()
                    return json.loads(json_str)
                if "```" in content:
                    json_str = content.split("```")[1].split("```")[0].strip()
                    return json.loads(json_str)
                # Try direct parse
                return json.loads(content)
            except (json.JSONDecodeError, IndexError):
                # Try to find a JSON object in the text
                start = content.find("{")
                end = content.rfind("}") + 1
                if start >= 0 and end > start:
                    try:
                        return json.loads(content[start:end])
                    except json.JSONDecodeError:
                        pass
    return {"status": "error", "error": "Could not extract result from agent response"}


# ---------------------------------------------------------------------------
# Public API — drop-in replacements for orchestrator.py functions
# ---------------------------------------------------------------------------

def process_register(record: dict) -> dict:
    """Full dedup pipeline for a new customer record via LangGraph agent.

    Compatible with the response format of the original orchestrator.
    """
    start = time.time()
    logger.info("langgraph process_register started")

    human_msg = HumanMessage(
        content=(
            "Process this new customer record through the REGISTER pipeline. "
            "Follow the pipeline steps exactly.\n\n"
            f"Customer record:\n```json\n{_safe_json(record)}\n```"
        )
    )

    initial_state: DedupState = {
        "messages": [SystemMessage(content=SYSTEM_PROMPT), human_msg],
        "customer_record": record,
        "candidates": [],
        "match_results": [],
        "final_decision": "",
        "source_agent": "intercept",
    }

    final_state = _agent.invoke(initial_state)
    result = _extract_result(final_state["messages"])

    elapsed = int((time.time() - start) * 1000)
    result.setdefault("processingTimeMs", elapsed)
    result.setdefault("sourceAgent", "intercept")
    logger.info(
        "langgraph process_register completed status=%s elapsed=%dms",
        result.get("status"), elapsed,
    )
    return result


def process_approve(review_id: str, reviewed_by: str = "data_steward") -> dict:
    """Execute a merge approval via LangGraph agent."""
    logger.info("langgraph process_approve reviewId=%s", review_id)

    # Look up review to provide context to the LLM
    import boto3
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

    human_msg = HumanMessage(
        content=(
            "Process this APPROVE pipeline. A Data Steward has approved the merge.\n\n"
            f"review_id: {review_id}\n"
            f"source_record_id: {source_id}\n"
            f"target_master_record_id: {master_id}\n"
            f"reviewed_by: {reviewed_by}\n"
            f"source_system: {incoming.get('sourceSystem', 'unknown')}\n"
            f"confidence_score: {float(review.get('confidenceScore', 0.0))}\n"
        )
    )

    initial_state: DedupState = {
        "messages": [SystemMessage(content=SYSTEM_PROMPT), human_msg],
        "customer_record": incoming,
        "candidates": [],
        "match_results": [],
        "final_decision": "approve",
        "source_agent": "intercept",
    }

    final_state = _agent.invoke(initial_state)
    result = _extract_result(final_state["messages"])

    result.setdefault("status", "approved")
    result.setdefault("reviewId", review_id)
    result.setdefault("sourceAgent", "intercept")
    return result


def process_reject(review_id: str, reviewed_by: str = "data_steward") -> dict:
    """Reject a merge via LangGraph agent."""
    logger.info("langgraph process_reject reviewId=%s", review_id)

    import boto3
    from datetime import datetime, timezone

    table_name = os.environ.get("REVIEW_QUEUE_TABLE_NAME", "ReviewQueue")
    table = boto3.resource("dynamodb").Table(table_name)

    resp = table.get_item(Key={"reviewId": review_id})
    review = resp.get("Item")
    if not review:
        raise ValueError(f"Review not found: {review_id}")

    now = datetime.now(timezone.utc).isoformat()

    # Update ReviewQueue status to rejected (same as original orchestrator)
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

    human_msg = HumanMessage(
        content=(
            "Process this REJECT pipeline. A Data Steward has rejected the merge.\n\n"
            f"review_id: {review_id}\n"
            f"incoming_record_id: {incoming.get('customerId', '')}\n"
            f"matched_record_id: {matched.get('customerId', '')}\n"
            f"reviewed_by: {reviewed_by}\n"
            f"source_system: {incoming.get('sourceSystem', 'unknown')}\n"
            f"confidence_score: {float(review.get('confidenceScore', 0.0))}\n"
        )
    )

    initial_state: DedupState = {
        "messages": [SystemMessage(content=SYSTEM_PROMPT), human_msg],
        "customer_record": incoming,
        "candidates": [],
        "match_results": [],
        "final_decision": "reject",
        "source_agent": "intercept",
    }

    final_state = _agent.invoke(initial_state)
    result = _extract_result(final_state["messages"])

    result.setdefault("status", "rejected")
    result.setdefault("reviewId", review_id)
    result.setdefault("sourceAgent", "intercept")
    return result
