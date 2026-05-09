"""Intercept Agent — FastAPI application for AgentCore Runtime.

Endpoints:
    POST /invocations  — Process register, approve, or reject actions.
    GET  /ping         — Health check (AgentCore Runtime requirement).
"""

import logging
import sys
import time
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# Structured logging to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("intercept-agent")

app = FastAPI(title="Intercept Agent", version="1.0.0")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class CustomerRecord(BaseModel):
    """Incoming customer record fields."""
    firstName: str
    lastName: str
    email: Optional[str] = None
    phone: Optional[str] = None
    dateOfBirth: Optional[str] = None
    address: Optional[dict[str, str]] = None
    sourceSystem: str = "unknown"


class InvocationRequest(BaseModel):
    """AgentCore Runtime invocation payload."""
    action: str = Field(
        ..., description="Action type: 'register', 'approve', or 'reject'"
    )
    record: Optional[CustomerRecord] = Field(
        None, description="Customer record (required for 'register')"
    )
    reviewId: Optional[str] = Field(
        None, description="Review ID (required for 'approve'/'reject')"
    )
    reviewedBy: Optional[str] = Field(
        "data_steward", description="Reviewer identifier"
    )


class InvocationResponse(BaseModel):
    """AgentCore Runtime invocation response."""
    status: str
    customerId: Optional[str] = None
    reviewId: Optional[str] = None
    confidenceScore: Optional[float] = None
    confidenceClassification: Optional[str] = None
    matchingMethod: Optional[str] = None
    matchedRecord: Optional[dict[str, Any]] = None
    mergedRecordId: Optional[str] = None
    sourceRecordId: Optional[str] = None
    fieldsConsolidated: Optional[list[str]] = None
    processingTimeMs: Optional[int] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/ping")
def ping():
    """Health check endpoint required by AgentCore Runtime."""
    return {"status": "healthy"}


@app.post("/invocations", response_model=InvocationResponse)
def invocations(request: InvocationRequest):
    """Process an invocation from AgentCore Runtime / Step Functions."""
    from langgraph_orchestrator import process_register, process_approve, process_reject

    logger.info("Invocation received: action=%s", request.action)
    start = time.time()

    try:
        if request.action == "register":
            if not request.record:
                raise HTTPException(status_code=400, detail="'record' is required for 'register' action")
            result = process_register(request.record.model_dump(exclude_none=True))

        elif request.action == "approve":
            if not request.reviewId:
                raise HTTPException(status_code=400, detail="'reviewId' is required for 'approve' action")
            result = process_approve(request.reviewId, request.reviewedBy or "data_steward")

        elif request.action == "reject":
            if not request.reviewId:
                raise HTTPException(status_code=400, detail="'reviewId' is required for 'reject' action")
            result = process_reject(request.reviewId, request.reviewedBy or "data_steward")

        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {request.action}")

        elapsed = int((time.time() - start) * 1000)
        logger.info("Invocation completed: action=%s status=%s elapsed=%dms",
                     request.action, result.get("status"), elapsed)
        return InvocationResponse(**result)

    except HTTPException:
        raise
    except ValueError as exc:
        logger.error("Validation error: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Invocation failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
