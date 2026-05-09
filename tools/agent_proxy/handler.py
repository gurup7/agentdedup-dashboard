"""Agent Proxy Lambda — bridges Step Functions to the orchestrator logic.

For the prototype, this Lambda directly imports and calls the Intercept/Clean
orchestrator (since AgentCore Runtime deployment is separate). In production,
this would be replaced by an InvokeAgent call to AgentCore Runtime.

Accepts {action, payload, reviewId} from Step Functions.
Routes to the appropriate orchestrator function based on AGENT_TYPE env var.

Environment variables:
    AGENT_TYPE: "intercept" or "clean"
    CUSTOMER_TABLE_NAME, REVIEW_QUEUE_TABLE_NAME, AUDIT_LOGS_BUCKET,
    BEDROCK_MODEL_ID — passed through to tool handlers via os.environ.
"""

import json
import logging
import os
import sys

# Add project root to sys.path so we can import from tools/ and agents/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    """Lambda entry point.

    Args:
        event: dict with keys:
            action: "register" | "approve" | "reject"
            payload: customer record dict (for register)
            reviewId: str (for approve/reject)
        context: Lambda context (unused).

    Returns:
        dict — result from the orchestrator.
    """
    if isinstance(event, str):
        event = json.loads(event)

    action = event.get("action", "")
    agent_type = os.environ.get("AGENT_TYPE", "intercept")

    logger.info("Agent proxy invoked: agent_type=%s action=%s", agent_type, action)

    try:
        if agent_type == "intercept":
            from agents.intercept.orchestrator import (
                process_register,
                process_approve,
                process_reject,
            )

            if action == "register":
                payload = event.get("payload", {})
                if isinstance(payload, str):
                    payload = json.loads(payload)
                return process_register(payload)

            elif action == "approve":
                review_id = event.get("reviewId", "")
                return process_approve(review_id)

            elif action == "reject":
                review_id = event.get("reviewId", "")
                return process_reject(review_id)

            elif action == "register-site":
                from agents.intercept.orchestrator import process_register_site
                payload = event.get("payload", {})
                if isinstance(payload, str):
                    payload = json.loads(payload)
                return process_register_site(payload)

            else:
                return {"error": f"Unknown action: {action}"}

        elif agent_type == "clean":
            from agents.clean.orchestrator import process_record

            if action == "register":
                payload = event.get("payload", {})
                if isinstance(payload, str):
                    payload = json.loads(payload)
                return process_record(payload)

            else:
                return {"error": f"Clean agent only supports 'register' action, got: {action}"}

        else:
            return {"error": f"Unknown AGENT_TYPE: {agent_type}"}

    except Exception as exc:
        logger.error("Agent proxy error: %s", exc, exc_info=True)
        return {
            "error": str(exc),
            "action": action,
            "agentType": agent_type,
        }
