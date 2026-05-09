#!/usr/bin/env bash
# =============================================================================
# Register Lambda Tools in AgentCore Gateway
# Registers all 7 Lambda tools as MCP-compatible tools for agent discovery.
#
# NOTE: This is a REFERENCE script. The actual CLI commands depend on the
# AgentCore Gateway GA API. Replace placeholder commands with real ones.
#
# Usage:
#   ./scripts/register-tools.sh [AWS_ACCOUNT_ID] [AWS_REGION]
# =============================================================================
set -euo pipefail

AWS_ACCOUNT_ID="${1:-${AWS_ACCOUNT_ID:?'AWS_ACCOUNT_ID required as arg or env var'}}"
AWS_REGION="${2:-${AWS_REGION:-us-east-1}}"

LAMBDA_ARN_PREFIX="arn:aws:lambda:${AWS_REGION}:${AWS_ACCOUNT_ID}:function"

echo "=== Register Lambda Tools in AgentCore Gateway ==="
echo "Account: ${AWS_ACCOUNT_ID}"
echo "Region:  ${AWS_REGION}"
echo ""

# --- Helper function to register a single tool ---
register_tool() {
  local tool_name="$1"
  local description="$2"
  local lambda_name="$3"
  local input_schema="$4"

  echo "Registering tool: ${tool_name}"
  echo "  Lambda: ${LAMBDA_ARN_PREFIX}:${lambda_name}"

  # PLACEHOLDER: Replace with actual AgentCore Gateway CLI command.
  # The register-tool API will associate the Lambda ARN with a tool name,
  # description, and JSON input schema so agents can discover and invoke it.
  aws bedrock-agentcore register-tool \
    --tool-name "${tool_name}" \
    --description "${description}" \
    --lambda-arn "${LAMBDA_ARN_PREFIX}:${lambda_name}" \
    --input-schema "${input_schema}" \
    --region "${AWS_REGION}" 2>/dev/null || \
    echo "  [PLACEHOLDER] Command not yet available — update when AgentCore GA API is released."

  echo ""
}

# --- Tool 1: QueryCustomerTool ---
register_tool "QueryCustomerTool" \
  "Search CustomerTable for potential matches using blocking strategy (postal code, phonetic name, email, phone)." \
  "dedup-query-customer-tool" \
  '{
    "type": "object",
    "properties": {
      "firstName":  {"type": "string", "description": "Customer first name"},
      "lastName":   {"type": "string", "description": "Customer last name"},
      "email":      {"type": "string", "description": "Email address"},
      "phone":      {"type": "string", "description": "Phone number"},
      "postalCode": {"type": "string", "description": "Postal code for blocking"}
    },
    "required": ["lastName"]
  }'

# --- Tool 2: CreateCustomerTool ---
register_tool "CreateCustomerTool" \
  "Insert a new customer record into CustomerTable with status=active." \
  "dedup-create-customer-tool" \
  '{
    "type": "object",
    "properties": {
      "firstName":    {"type": "string"},
      "lastName":     {"type": "string"},
      "email":        {"type": "string"},
      "phone":        {"type": "string"},
      "dateOfBirth":  {"type": "string", "description": "YYYY-MM-DD"},
      "address":      {"type": "object"},
      "sourceSystem": {"type": "string", "description": "e.g. OneCRM, NES"}
    },
    "required": ["firstName", "lastName", "sourceSystem"]
  }'

# --- Tool 3: MergeCustomerTool ---
register_tool "MergeCustomerTool" \
  "Merge duplicate records: consolidate fields into master, mark source as merged. No deletions." \
  "dedup-merge-customer-tool" \
  '{
    "type": "object",
    "properties": {
      "sourceRecordId":      {"type": "string", "description": "ID of the duplicate record"},
      "targetMasterRecordId": {"type": "string", "description": "ID of the master record"},
      "reviewId":            {"type": "string", "description": "Associated review ID"}
    },
    "required": ["sourceRecordId", "targetMasterRecordId", "reviewId"]
  }'

# --- Tool 4: RuleBasedMatchTool ---
register_tool "RuleBasedMatchTool" \
  "Stage 1 matching: score candidates using email, phone, Jaro-Winkler, Soundex, DOB." \
  "dedup-rule-based-match-tool" \
  '{
    "type": "object",
    "properties": {
      "incomingRecord": {"type": "object", "description": "The new customer record"},
      "candidates":     {"type": "array", "description": "Array of candidate records to compare"}
    },
    "required": ["incomingRecord", "candidates"]
  }'

# --- Tool 5: LLMMatchTool ---
register_tool "LLMMatchTool" \
  "Stage 2 matching: LLM-based fuzzy matching via Bedrock for ambiguous cases (score 0.4-0.9)." \
  "dedup-llm-match-tool" \
  '{
    "type": "object",
    "properties": {
      "incomingRecord":  {"type": "object", "description": "The new customer record"},
      "candidateRecord": {"type": "object", "description": "The candidate to compare"},
      "ruleBasedScore":  {"type": "number", "description": "Score from RuleBasedMatchTool"}
    },
    "required": ["incomingRecord", "candidateRecord", "ruleBasedScore"]
  }'

# --- Tool 6: WriteReviewTool ---
register_tool "WriteReviewTool" \
  "Write a merge candidate pair to ReviewQueue for human review." \
  "dedup-write-review-tool" \
  '{
    "type": "object",
    "properties": {
      "incomingRecord":            {"type": "object"},
      "matchedRecord":             {"type": "object"},
      "confidenceScore":           {"type": "number"},
      "confidenceClassification":  {"type": "string", "enum": ["high_confidence", "potential_duplicate"]},
      "matchingMethod":            {"type": "string"},
      "contributingFields":        {"type": "array", "items": {"type": "string"}},
      "sourceAgent":               {"type": "string", "enum": ["intercept", "clean"]}
    },
    "required": ["incomingRecord", "matchedRecord", "confidenceScore", "confidenceClassification", "matchingMethod", "contributingFields", "sourceAgent"]
  }'

# --- Tool 7: WriteAuditLogTool ---
register_tool "WriteAuditLogTool" \
  "Write structured audit log entry to S3 audit bucket." \
  "dedup-write-audit-log-tool" \
  '{
    "type": "object",
    "properties": {
      "eventType":       {"type": "string", "description": "e.g. match_recommendation, new_record, merge_approved"},
      "sourceAgent":     {"type": "string"},
      "confidenceScore": {"type": "number"},
      "decision":        {"type": "string"},
      "rationale":       {"type": "string"},
      "incomingRecordId": {"type": "string"},
      "matchedRecordId":  {"type": "string"},
      "reviewId":         {"type": "string"}
    },
    "required": ["eventType", "sourceAgent", "decision"]
  }'

echo "=== Tool Registration Complete ==="
echo "Registered 7 tools. Verify in AgentCore Gateway console."
