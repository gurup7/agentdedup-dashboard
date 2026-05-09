# AgentDedup — DynamoDB to Oracle EBS Migration Guide

## Overview

The prototype uses DynamoDB to simulate Oracle EBS TCA (HZ_PARTIES). 
To switch to Oracle EBS via Mulesoft API, only **3 Lambda tool handlers** change.
The agents, API Gateway, matching pipeline, and ReviewQueue remain unchanged.

## What Changes

| Component | Prototype | Production | Change |
|---|---|---|---|
| QueryCustomerTool | DynamoDB Query/Scan | Mulesoft API → Oracle EBS | Lambda code |
| CreateCustomerTool | DynamoDB PutItem | Mulesoft API → Oracle EBS | Lambda code |
| MergeCustomerTool | DynamoDB UpdateItem | Mulesoft API → Oracle EBS | Lambda code |
| Intercept Agent | No change | No change | None |
| Clean Agent | No change | No change | None |
| API Gateway | No change | No change | None |
| RuleBasedMatchTool | No change | No change | None |
| LLMMatchTool | No change | No change | None |
| ReviewQueue | DynamoDB (stays) | DynamoDB (stays) | None |

## Information Needed from Client

### Mulesoft API Details

1. **Base URL**: e.g., `https://api.client.com/oracle-ebs/v1`
2. **Authentication**: OAuth2 / API Key / mTLS?
3. **Credentials**: Client ID + Secret (store in AWS Secrets Manager)

### API Endpoints Required

| Operation | HTTP Method | Endpoint | Purpose |
|---|---|---|---|
| Search parties | GET | `/parties?search=...` | QueryCustomerTool |
| Get party by ID | GET | `/parties/{partyId}` | QueryCustomerTool |
| Create party | POST | `/parties` | CreateCustomerTool |
| Update party | PUT | `/parties/{partyId}` | MergeCustomerTool |
| Merge parties | POST | `/parties/{partyId}/merge` | MergeCustomerTool |

### Sample Request/Response

We need sample payloads for each endpoint to map our data model.

**Current DynamoDB schema (Person):**
```json
{
  "customerId": "uuid",
  "firstName": "Chris",
  "lastName": "James",
  "email": "chris@example.com",
  "phone": "+15551234001",
  "dateOfBirth": "1985-03-15",
  "address": {"street": "100 Maple Ave", "city": "Springfield", "state": "IL", "postalCode": "62701"},
  "sourceSystem": "OneCRM",
  "status": "active"
}
```

**Current DynamoDB schema (Organization):**
```json
{
  "customerId": "uuid",
  "partyType": "ORGANIZATION",
  "partyName": "Pearson Education Inc.",
  "taxRegistrationNum": "TAX-PE-2024-001",
  "taxpayerId": "TP-84-1234567",
  "mdrPidId": "MDR-PE-0001",
  "matchMarket": "US-EDUCATION",
  "address": {"street": "221 River St", "city": "Hoboken", "state": "NJ", "postalCode": "07030"},
  "sourceSystem": "OneCRM",
  "status": "active"
}
```

**Question:** What does the equivalent Oracle EBS TCA HZ_PARTIES record look like via Mulesoft?

## Migration Steps

### Step 1: Store Mulesoft Credentials in Secrets Manager

```bash
aws secretsmanager create-secret \
  --name agentdedup/mulesoft-api \
  --secret-string '{"base_url":"https://api.client.com/oracle-ebs/v1","client_id":"xxx","client_secret":"xxx"}' \
  --region us-east-1
```

### Step 2: Update Lambda Tool Code

Each Lambda tool handler gets a new implementation that calls Mulesoft instead of DynamoDB.
The function signature (input/output) stays the same — only the internal implementation changes.

### Step 3: Update Lambda Environment Variables

```bash
aws lambda update-function-configuration \
  --function-name dedup-app-query-customer-tool \
  --environment Variables={MULESOFT_SECRET_ARN=arn:aws:secretsmanager:...} \
  --region us-east-1
```

### Step 4: Update IAM Roles

Lambda tools need permission to:
- Read from Secrets Manager (for Mulesoft credentials)
- Make outbound HTTPS calls to Mulesoft API

### Step 5: Test

Run the same demo scenarios — the behavior should be identical, just backed by Oracle EBS instead of DynamoDB.
