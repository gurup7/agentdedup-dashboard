"""Clean Agent — FastAPI application for AgentCore Runtime (Reactive Layer).

Endpoints:
    POST /invocations  — Process a single customer record (called per-record by
                         Step Functions batch workflow).
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
logger = logging.getLogger("clean-agent")

app = FastAPI(title="Clean Agent", version="1.0.0")


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
    """AgentCore Runtime invocation payload.

    The Clean Agent supports a single action: ``process_record``.
    Step Functions Standard Workflow calls this once per record in the batch.
    """
    action: str = Field(
        ..., description="Action type: 'process_record'"
    )
    record: Optional[CustomerRecord] = Field(
        None, description="Customer record to process"
    )
    batchId: Optional[str] = Field(
        None, description="Batch identifier for progress tracking"
    )
    recordIndex: Optional[int] = Field(
        None, description="1-based index of this record within the batch"
    )
    totalRecords: Optional[int] = Field(
        None, description="Total records in the batch"
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
    processingTimeMs: Optional[int] = None
    batchId: Optional[str] = None
    recordIndex: Optional[int] = None
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
    """Process a single record invocation from Step Functions batch workflow."""
    from langgraph_orchestrator import process_record

    logger.info(
        "Invocation received: action=%s batchId=%s record=%s/%s",
        request.action,
        request.batchId,
        request.recordIndex,
        request.totalRecords,
    )
    start = time.time()

    try:
        if request.action == "process_record":
            if not request.record:
                raise HTTPException(
                    status_code=400,
                    detail="'record' is required for 'process_record' action",
                )
            result = process_record(
                record=request.record.model_dump(exclude_none=True),
                batch_id=request.batchId,
                record_index=request.recordIndex,
                total_records=request.totalRecords,
            )
        else:
            raise HTTPException(
                status_code=400, detail=f"Unknown action: {request.action}"
            )

        elapsed = int((time.time() - start) * 1000)
        logger.info(
            "Invocation completed: action=%s status=%s elapsed=%dms batch=%s record=%s/%s",
            request.action,
            result.get("status"),
            elapsed,
            request.batchId,
            request.recordIndex,
            request.totalRecords,
        )
        return InvocationResponse(**result)

    except HTTPException:
        raise
    except ValueError as exc:
        logger.error("Validation error: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Invocation failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
