"""Register Lambda tools as AgentCore Gateway targets."""
import boto3
import json

REGION = "us-east-1"
GATEWAY_ID = "dedup-tools-gateway-kij10ejguh"

client = boto3.client("bedrock-agentcore", region_name=REGION)

# Lambda ARN prefix
LAMBDA_PREFIX = "arn:aws:lambda:us-east-1:553556337417:function:dedup-app-"

TOOLS = [
    {
        "name": "QueryCustomerTool",
        "lambda_suffix": "query-customer-tool",
        "description": "Search CustomerTable for potential duplicate matches using blocking strategy.",
        "schema": {
            "type": "object",
            "properties": {
                "firstName": {"type": "string"},
                "lastName": {"type": "string"},
                "email": {"type": "string"},
                "phone": {"type": "string"},
                "postalCode": {"type": "string"},
            },
            "required": ["lastName"],
        },
    },
    {
        "name": "CreateCustomerTool",
        "lambda_suffix": "create-customer-tool",
        "description": "Insert a new customer record into CustomerTable.",
        "schema": {
            "type": "object",
            "properties": {
                "firstName": {"type": "string"},
                "lastName": {"type": "string"},
                "email": {"type": "string"},
                "phone": {"type": "string"},
                "sourceSystem": {"type": "string"},
            },
            "required": ["firstName", "lastName", "sourceSystem"],
        },
    },
    {
        "name": "RuleBasedMatchTool",
        "lambda_suffix": "rule-based-match-tool",
        "description": "Stage 1 matching: score candidates using email, phone, Jaro-Winkler, Soundex, DOB.",
        "schema": {
            "type": "object",
            "properties": {
                "incomingRecord": {"type": "object"},
                "candidates": {"type": "array"},
            },
            "required": ["incomingRecord", "candidates"],
        },
    },
    {
        "name": "WriteReviewTool",
        "lambda_suffix": "write-review-tool",
        "description": "Write a merge candidate pair to ReviewQueue for human review.",
        "schema": {
            "type": "object",
            "properties": {
                "incomingRecord": {"type": "object"},
                "matchedRecord": {"type": "object"},
                "confidenceScore": {"type": "number"},
                "confidenceClassification": {"type": "string"},
                "matchingMethod": {"type": "string"},
                "contributingFields": {"type": "array"},
                "sourceAgent": {"type": "string"},
            },
            "required": ["incomingRecord", "matchedRecord", "confidenceScore"],
        },
    },
]

print(f"Registering {len(TOOLS)} tools in Gateway: {GATEWAY_ID}\n")

for tool in TOOLS:
    lambda_arn = f"{LAMBDA_PREFIX}{tool['lambda_suffix']}"
    print(f"  Registering: {tool['name']} -> {lambda_arn}")
    
    try:
        response = client.create_gateway_target(
            gatewayIdentifier=GATEWAY_ID,
            name=tool["name"],
            targetConfiguration={
                "lambdaTargetConfiguration": {
                    "lambdaArn": lambda_arn,
                    "toolSchema": {
                        "inlinePayload": [
                            {
                                "name": tool["name"],
                                "description": tool["description"],
                                "inputSchema": {"json": tool["schema"]},
                            }
                        ]
                    },
                }
            },
        )
        target_id = response.get("targetId", "unknown")
        print(f"    Created: {target_id}")
    except Exception as e:
        print(f"    Error: {e}")

print("\nDone.")
