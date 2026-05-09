"""Register Lambda tools as AgentCore Gateway targets using the starter toolkit's internal API."""
import json
import sys

# The starter toolkit uses httpx to call the AgentCore API directly
from bedrock_agentcore_starter_toolkit.gateway.gateway_manager import GatewayManager

REGION = "us-east-1"
GATEWAY_ID = "dedup-tools-gateway-kij10ejguh"
LAMBDA_PREFIX = "arn:aws:lambda:us-east-1:553556337417:function:dedup-app-"

TOOLS = [
    {
        "name": "QueryCustomerTool",
        "lambda_suffix": "query-customer-tool",
        "description": "Search CustomerTable for potential duplicate matches using blocking strategy.",
        "schema": [
            {
                "name": "QueryCustomerTool",
                "description": "Search CustomerTable for potential duplicate matches using blocking strategy (email, phone, postalCode+lastName). Returns up to 10 candidate records.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "firstName": {"type": "string"},
                            "lastName": {"type": "string"},
                            "email": {"type": "string"},
                            "phone": {"type": "string"},
                            "postalCode": {"type": "string"},
                        },
                        "required": ["lastName"],
                    }
                },
            }
        ],
    },
    {
        "name": "CreateCustomerTool",
        "lambda_suffix": "create-customer-tool",
        "description": "Insert a new customer record into CustomerTable.",
        "schema": [
            {
                "name": "CreateCustomerTool",
                "description": "Insert a new customer record into CustomerTable with status=active.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "firstName": {"type": "string"},
                            "lastName": {"type": "string"},
                            "sourceSystem": {"type": "string"},
                        },
                        "required": ["firstName", "lastName", "sourceSystem"],
                    }
                },
            }
        ],
    },
]

try:
    gm = GatewayManager(region=REGION)
    print(f"GatewayManager created for region: {REGION}")
    
    for tool in TOOLS:
        lambda_arn = f"{LAMBDA_PREFIX}{tool['lambda_suffix']}"
        print(f"\nRegistering: {tool['name']} -> {lambda_arn}")
        
        result = gm.create_gateway_target(
            gateway_id=GATEWAY_ID,
            name=tool["name"],
            target_type="lambda",
            lambda_arn=lambda_arn,
            tool_schema=tool["schema"],
        )
        print(f"  Result: {result}")
        
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
    
    # Fallback: try to find the correct API
    import inspect
    try:
        gm = GatewayManager(region=REGION)
        methods = [m for m in dir(gm) if not m.startswith("_") and "target" in m.lower()]
        print(f"\nAvailable target methods: {methods}")
        
        # Check create_gateway_target signature
        for m in methods:
            sig = inspect.signature(getattr(gm, m))
            print(f"  {m}{sig}")
    except Exception as e2:
        print(f"Fallback error: {e2}")
