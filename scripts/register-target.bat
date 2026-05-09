@echo off
set AGENTCORE=C:\Users\GuruprakashSubbarao\AppData\Roaming\Python\Python314\Scripts\agentcore.exe
set GATEWAY_ARN=arn:aws:bedrock-agentcore:us-east-1:553556337417:gateway/dedup-tools-gateway-kij10ejguh
set GATEWAY_URL=https://dedup-tools-gateway-kij10ejguh.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp
set ROLE_ARN=arn:aws:iam::553556337417:role/AgentCoreGatewayExecutionRole
set PAYLOAD={"lambdaArn":"arn:aws:lambda:us-east-1:553556337417:function:dedup-app-query-customer-tool","toolSchema":{"inlinePayload":[{"name":"QueryCustomerTool","description":"Search for matches","inputSchema":{"json":{"type":"object","properties":{"lastName":{"type":"string"}},"required":["lastName"]}}}]}}

%AGENTCORE% gateway create-mcp-gateway-target --gateway-arn %GATEWAY_ARN% --gateway-url %GATEWAY_URL% --role-arn %ROLE_ARN% --region us-east-1 --name QueryCustomerTool --target-type lambda --target-payload "%PAYLOAD%"
