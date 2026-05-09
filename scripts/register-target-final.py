"""Register Lambda tools as AgentCore Gateway targets by calling the CLI via subprocess."""
import subprocess
import json
import sys

AGENTCORE = r"C:\Users\GuruprakashSubbarao\AppData\Roaming\Python\Python314\Scripts\agentcore.exe"
GATEWAY_ARN = "arn:aws:bedrock-agentcore:us-east-1:553556337417:gateway/dedup-tools-gateway-kij10ejguh"
GATEWAY_URL = "https://dedup-tools-gateway-kij10ejguh.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp"
ROLE_ARN = "arn:aws:iam::553556337417:role/AgentCoreGatewayExecutionRole"
REGION = "us-east-1"

TOOLS = [
    {
        "name": "QueryCustomerTool",
        "lambda_arn": "arn:aws:lambda:us-east-1:553556337417:function:dedup-app-query-customer-tool",
        "description": "Search CustomerTable for potential duplicate matches",
        "schema": {"type": "object", "properties": {"lastName": {"type": "string"}}, "required": ["lastName"]},
    },
    {
        "name": "CreateCustomerTool",
        "lambda_arn": "arn:aws:lambda:us-east-1:553556337417:function:dedup-app-create-customer-tool",
        "description": "Insert a new customer record into CustomerTable",
        "schema": {"type": "object", "properties": {"firstName": {"type": "string"}, "lastName": {"type": "string"}, "sourceSystem": {"type": "string"}}, "required": ["firstName", "lastName", "sourceSystem"]},
    },
    {
        "name": "WriteReviewTool",
        "lambda_arn": "arn:aws:lambda:us-east-1:553556337417:function:dedup-app-write-review-tool",
        "description": "Write a merge candidate pair to ReviewQueue for human review",
        "schema": {"type": "object", "properties": {"incomingRecord": {"type": "object"}, "matchedRecord": {"type": "object"}, "confidenceScore": {"type": "number"}}, "required": ["incomingRecord", "matchedRecord", "confidenceScore"]},
    },
]

for tool in TOOLS:
    payload = json.dumps({
        "lambdaArn": tool["lambda_arn"],
        "toolSchema": {
            "inlinePayload": [
                {
                    "name": tool["name"],
                    "description": tool["description"],
                    "inputSchema": {"json": tool["schema"]},
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

    print(f"Registering: {tool['name']}...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode == 0:
        print(f"  Success: {result.stdout[:200]}")
    else:
        print(f"  Error: {result.stderr[:300]}")
    print()
