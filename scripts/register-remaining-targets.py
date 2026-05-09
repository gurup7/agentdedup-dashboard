"""Register remaining Lambda tools as AgentCore Gateway targets one at a time."""
import subprocess
import json
import sys

AGENTCORE = r"C:\Users\GuruprakashSubbarao\AppData\Roaming\Python\Python314\Scripts\agentcore.exe"
GATEWAY_ARN = "arn:aws:bedrock-agentcore:us-east-1:553556337417:gateway/dedup-tools-gateway-kij10ejguh"
GATEWAY_URL = "https://dedup-tools-gateway-kij10ejguh.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp"
ROLE_ARN = "arn:aws:iam::553556337417:role/AgentCoreGatewayExecutionRole"
REGION = "us-east-1"
LAMBDA_PREFIX = "arn:aws:lambda:us-east-1:553556337417:function:dedup-app-"

# Only the tools NOT yet registered (QueryCustomerTool already exists)
TOOLS = [
    {
        "name": "CreateCustomerTool",
        "lambda_suffix": "create-customer-tool",
        "description": "Insert a new customer record into CustomerTable with status active",
        "schema": {"type": "object", "properties": {"firstName": {"type": "string"}, "lastName": {"type": "string"}, "sourceSystem": {"type": "string"}}, "required": ["firstName", "lastName", "sourceSystem"]},
    },
    {
        "name": "MergeCustomerTool",
        "lambda_suffix": "merge-customer-tool",
        "description": "Merge duplicate records after human approval. Marks source as merged.",
        "schema": {"type": "object", "properties": {"sourceRecordId": {"type": "string"}, "targetMasterRecordId": {"type": "string"}, "reviewId": {"type": "string"}}, "required": ["sourceRecordId", "targetMasterRecordId", "reviewId"]},
    },
    {
        "name": "RuleBasedMatchTool",
        "lambda_suffix": "rule-based-match-tool",
        "description": "Stage 1 matching using email phone Jaro-Winkler Soundex and DOB",
        "schema": {"type": "object", "properties": {"incomingRecord": {"type": "object"}, "candidates": {"type": "array"}}, "required": ["incomingRecord", "candidates"]},
    },
    {
        "name": "LLMMatchTool",
        "lambda_suffix": "llm-match-tool",
        "description": "Stage 2 LLM-based fuzzy matching via Bedrock for ambiguous cases",
        "schema": {"type": "object", "properties": {"incomingRecord": {"type": "object"}, "candidateRecord": {"type": "object"}, "ruleBasedScore": {"type": "number"}}, "required": ["incomingRecord", "candidateRecord", "ruleBasedScore"]},
    },
    {
        "name": "WriteReviewTool",
        "lambda_suffix": "write-review-tool",
        "description": "Write a merge candidate pair to ReviewQueue for human review",
        "schema": {"type": "object", "properties": {"incomingRecord": {"type": "object"}, "matchedRecord": {"type": "object"}, "confidenceScore": {"type": "number"}, "sourceAgent": {"type": "string"}}, "required": ["incomingRecord", "matchedRecord", "confidenceScore"]},
    },
    {
        "name": "WriteAuditLogTool",
        "lambda_suffix": "write-audit-log-tool",
        "description": "Write structured audit log entry to S3 audit bucket",
        "schema": {"type": "object", "properties": {"eventType": {"type": "string"}, "sourceAgent": {"type": "string"}, "decision": {"type": "string"}}, "required": ["eventType", "sourceAgent", "decision"]},
    },
]

for tool in TOOLS:
    lambda_arn = f"{LAMBDA_PREFIX}{tool['lambda_suffix']}"
    payload = json.dumps({
        "lambdaArn": lambda_arn,
        "toolSchema": {
            "inlinePayload": [
                {
                    "name": tool["name"],
                    "description": tool["description"],
                    "inputSchema": tool["schema"],
                }
            ]
        },
    })

    cmd = [
        AGENTCORE, "gateway", "create-mcp-gateway-target",
        "--gateway-arn", GATEWAY_ARN,
        "--gateway-url", GATEWAY_URL,
        "--role-arn", ROLE_ARN,
        "--region", REGION,
        "--name", tool["name"],
        "--target-type", "lambda",
        "--target-payload", payload,
    ]

    print(f"Registering: {tool['name']}...", flush=True)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        if "Created" in stderr or "success" in stderr.lower() or result.returncode == 0:
            print(f"  OK (rc={result.returncode})")
        else:
            print(f"  rc={result.returncode}")
        if stderr:
            # Show last 2 lines of stderr for debugging
            lines = stderr.split("\n")
            for line in lines[-3:]:
                if line.strip():
                    print(f"  {line.strip()[:120]}")
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT (30s)")
    print()
