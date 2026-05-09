#!/usr/bin/env bash
# =============================================================================
# Build and Push Docker Images to ECR
# Builds ARM64 images for Intercept Agent and Clean Agent, pushes to ECR.
#
# Usage:
#   ./scripts/build-and-push.sh [AWS_ACCOUNT_ID] [AWS_REGION]
#
# Environment variables (override with args):
#   AWS_ACCOUNT_ID  - 12-digit AWS account ID
#   AWS_REGION      - AWS region (default: us-east-1)
# =============================================================================
set -euo pipefail

AWS_ACCOUNT_ID="${1:-${AWS_ACCOUNT_ID:?'AWS_ACCOUNT_ID required as arg or env var'}}"
AWS_REGION="${2:-${AWS_REGION:-us-east-1}}"

ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
AGENTS=("intercept-agent" "clean-agent")
DOCKERFILES=("agents/intercept/Dockerfile" "agents/clean/Dockerfile")

echo "=== ECR Build & Push ==="
echo "Account: ${AWS_ACCOUNT_ID}"
echo "Region:  ${AWS_REGION}"
echo "Registry: ${ECR_REGISTRY}"
echo ""

# --- Step 1: Create ECR repositories if they don't exist ---
for repo in "${AGENTS[@]}"; do
  echo "Ensuring ECR repository: ${repo}"
  aws ecr describe-repositories --repository-names "${repo}" --region "${AWS_REGION}" 2>/dev/null || \
    aws ecr create-repository \
      --repository-name "${repo}" \
      --region "${AWS_REGION}" \
      --image-scanning-configuration scanOnPush=true \
      --encryption-configuration encryptionType=KMS
done

# --- Step 2: Login to ECR ---
echo ""
echo "Logging in to ECR..."
aws ecr get-login-password --region "${AWS_REGION}" | \
  docker login --username AWS --password-stdin "${ECR_REGISTRY}"

# --- Step 3: Build ARM64 images (build context = project root) ---
# Ensure buildx builder exists for multi-platform builds
docker buildx inspect dedup-builder 2>/dev/null || \
  docker buildx create --name dedup-builder --use

for i in "${!AGENTS[@]}"; do
  agent="${AGENTS[$i]}"
  dockerfile="${DOCKERFILES[$i]}"
  image_uri="${ECR_REGISTRY}/${agent}:latest"

  echo ""
  echo "Building ${agent} (ARM64)..."
  docker buildx build \
    --platform linux/arm64 \
    --file "${dockerfile}" \
    --tag "${image_uri}" \
    --push \
    .
done

# --- Step 4: Print image URIs ---
echo ""
echo "=== Build Complete ==="
for agent in "${AGENTS[@]}"; do
  echo "  ${agent}: ${ECR_REGISTRY}/${agent}:latest"
done
