"""Register Lambda tools as AgentCore Gateway targets using the bedrock-agentcore SDK."""
import json
from bedrock_agentcore.gateway import GatewayClient

REGION = "us-east-1"
GATEWAY_ID = "dedup-tools-gateway-kij10ejguh"
LAMBDA_PREFIX = "arn:aws:lambda:us-east-1:553556337417:function:dedup-app-"

try:
    client = GatewayClient(region=REGION)
    print(f"Gateway client created for region: {REGION}")
except Exception as e:
    print(f"Error creating client: {e}")
    # Try alternative approach
    import boto3
    session = boto3.Session(region_name=REGION)
    # List available methods
    ac = session.client("bedrock-agentcore")
    methods = [m for m in dir(ac) if "target" in m.lower() or "gateway" in m.lower()]
    print(f"Available gateway methods: {methods}")
