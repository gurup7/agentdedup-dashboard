#!/usr/bin/env bash
# =============================================================================
# Deploy Clean Agent to AgentCore Runtime
# Creates or updates an AgentCore Runtime with the ECR image, waits for READY.
#
# Usage:
#   ./scripts/deploy-clean-agent.sh [AWS_ACCOUNT_ID] [AWS_REGION]
#
# Environment variables:
#   AWS_ACCOUNT_ID  - 12-digit AWS account ID
#   AWS_REGION      - AWS region (default: us-east-1)
# =============================================================================
set -euo pipefail

AWS_ACCOUNT_ID="${1:-${AWS_ACCOUNT_ID:?'AWS_ACCOUNT_ID required as arg or env var'}}"
AWS_REGION="${2:-${AWS_REGION:-us-east-1}}"

ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE_URI="${ECR_REGISTRY}/clean-agent:latest"
RUNTIME_NAME="clean-agent-runtime"
MAX_WAIT_SECONDS=300
POLL_INTERVAL=10

echo "=== Deploy Clean Agent ==="
echo "Image: ${IMAGE_URI}"
echo "Runtime: ${RUNTIME_NAME}"
echo ""

# --- Step 1: Create or update AgentCore Runtime ---
# NOTE: Commands below use placeholder CLI syntax. Replace with actual
# AgentCore CLI/API calls once the service reaches GA.
echo "Creating/updating AgentCore Runtime..."
RUNTIME_ARN=$(aws bedrock-agentcore create-runtime \
  --runtime-name "${RUNTIME_NAME}" \
  --image-uri "${IMAGE_URI}" \
  --port 8080 \
  --region "${AWS_REGION}" \
  --output text --query 'runtimeArn' 2>/dev/null) || \
RUNTIME_ARN=$(aws bedrock-agentcore update-runtime \
  --runtime-name "${RUNTIME_NAME}" \
  --image-uri "${IMAGE_URI}" \
  --region "${AWS_REGION}" \
  --output text --query 'runtimeArn')

echo "Runtime ARN: ${RUNTIME_ARN}"

# --- Step 2: Wait for status=READY ---
echo "Waiting for runtime to become READY (timeout: ${MAX_WAIT_SECONDS}s)..."
elapsed=0
while [ $elapsed -lt $MAX_WAIT_SECONDS ]; do
  STATUS=$(aws bedrock-agentcore get-runtime \
    --runtime-name "${RUNTIME_NAME}" \
    --region "${AWS_REGION}" \
    --output text --query 'status' 2>/dev/null || echo "UNKNOWN")

  echo "  Status: ${STATUS} (${elapsed}s elapsed)"
  if [ "${STATUS}" = "READY" ]; then
    echo "Runtime is READY."
    break
  fi
  sleep $POLL_INTERVAL
  elapsed=$((elapsed + POLL_INTERVAL))
done

if [ "${STATUS}" != "READY" ]; then
  echo "ERROR: Runtime did not reach READY within ${MAX_WAIT_SECONDS}s"
  exit 1
fi

# --- Step 3: Test /ping endpoint ---
echo ""
echo "Testing /ping endpoint..."
PING_RESPONSE=$(aws bedrock-agentcore invoke-runtime \
  --runtime-name "${RUNTIME_NAME}" \
  --path "/ping" \
  --method GET \
  --region "${AWS_REGION}" \
  --output text 2>/dev/null || echo "PING_FAILED")

echo "Ping response: ${PING_RESPONSE}"

# --- Step 4: Print summary ---
echo ""
echo "=== Clean Agent Deployed ==="
echo "  Runtime ARN: ${RUNTIME_ARN}"
echo "  Image URI:   ${IMAGE_URI}"
echo "  Status:      ${STATUS}"
