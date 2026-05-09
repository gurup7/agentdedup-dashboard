# Design Document: Customer Data Deduplication Prototype

## Overview

This design defines the technical architecture for a two-agent customer data deduplication system on AWS Bedrock AgentCore. The system intercepts and cleans duplicate customer records flowing from Sales Systems (OneCRM, NES) into TEP Oracle EBS, using AI-powered matching and human-in-the-loop review.

The prototype is designed to be demonstrable to the client via Postman/curl — no web UI required. All interactions (record submission, duplicate detection, human review, merge approval) happen through REST API endpoints.

**Key Design Decisions:**
- Two independent agents (Intercept + Clean) on AgentCore Runtime, sharing Lambda tools
- DynamoDB simulates Oracle EBS TCA (HZ_PARTIES) — swappable via Lambda tool code only
- Two-stage matching: rule-based (Lambda) → LLM-based (Bedrock) for ambiguous cases
- All merges require human approval — no auto-merge
- No deletions — merge operations preserve source records
- Unified Person + Organization support: same pipeline, different scoring rules per partyType
- PERSON uses normalized scoring (0.0–1.0); ORGANIZATION uses cumulative scoring (Oracle TCA style, threshold 144)
- Scoring configuration externalized in `tools/scoring_config.json` for easy tuning

## Architecture

### System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     PROACTIVE LAYER (Real-Time)                     │
│                                                                     │
│  Sales Systems          API Gateway         Step Functions (Express)│
│  (OneCRM, NES)   ──►  POST /register  ──►  Invoke Intercept Agent  │
│  via Postman/curl      GET /reviews         via AgentCore Runtime   │
│                        POST /reviews/       ──► Intercept_Agent     │
│                          {id}/approve                               │
│                          {id}/reject                                │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                     REACTIVE LAYER (Batch)                          │
│                                                                     │
│  S3 Bucket              S3 Event /          Step Functions (Std)    │
│  (CSV/JSON)      ──►   Manual Trigger  ──►  Orchestrate Clean Agent│
│                                             via AgentCore Runtime   │
│                                             ──► Clean_Agent         │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                     SHARED TOOL LAYER                               │
│                                                                     │
│  AgentCore Gateway (MCP-compatible tool registry)                   │
│  ├── QueryCustomerTool    (Lambda → DynamoDB CustomerTable)         │
│  │   └── PERSON: GSI blocking | ORGANIZATION: scan + filter        │
│  ├── CreateCustomerTool   (Lambda → DynamoDB CustomerTable)         │
│  ├── MergeCustomerTool    (Lambda → DynamoDB CustomerTable)         │
│  ├── RuleBasedMatchTool   (Lambda → Soundex, Jaro-Winkler)         │
│  │   └── PERSON: normalized 0-1 | ORGANIZATION: cumulative (TCA)   │
│  ├── LLMMatchTool         (Lambda → Bedrock Claude/Nova)            │
│  ├── WriteReviewTool      (Lambda → DynamoDB ReviewQueue)           │
│  └── WriteAuditLogTool    (Lambda → S3 audit bucket)                │
│                                                                     │
│  AgentCore Identity (workload credentials for tool invocation)      │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                     DATA LAYER                                      │
│                                                                     │
│  DynamoDB CustomerTable    DynamoDB ReviewQueue    S3 Buckets       │
│  (simulates Oracle EBS     (pending merge          (batch input,    │
│   TCA / HZ_PARTIES)         candidates)             audit logs,     │
│                                                     batch reports)  │
└─────────────────────────────────────────────────────────────────────┘
```

### AWS Services (16 total)

| # | Service | Role | Cost Model |
|---|---------|------|------------|
| 1 | Amazon Bedrock | LLM inference for Stage 2 fuzzy matching (Amazon Nova Pro) | Variable (per-token) |
| 2 | Bedrock AgentCore Runtime | Hosts Intercept Agent and Clean Agent as separate deployments | Variable (per-invocation) |
| 3 | Bedrock AgentCore Gateway | Exposes Lambda tools as MCP-compatible endpoints | Variable (per-call) |
| 4 | Bedrock AgentCore Identity | Workload identity and credential management | Included with AgentCore |
| 5 | AWS Lambda | All tool implementations (8 functions) | Variable (per-invocation) |
| 6 | Amazon API Gateway | REST endpoints for record submission and review management | Variable (per-request) |
| 7 | AWS Step Functions | Express Workflow (real-time), Standard Workflow (batch) | Variable (per-transition) |
| 8 | Amazon DynamoDB | CustomerTable (Person + Org) + ReviewQueue | Variable (per-read/write) |
| 9 | Amazon S3 | Batch input, audit logs, batch reports | Variable (per-storage/request) |
| 10 | AWS KMS | Customer-managed encryption keys | Fixed ($1/key/month) |
| 11 | AWS IAM | Least-privilege policies per component | Free |
| 12 | Amazon CloudWatch | Logs (per-agent log groups) + basic metrics/alarms | Fixed + Variable |
| 13 | AWS Secrets Manager | Oracle EBS credentials (production readiness) | Fixed ($0.40/secret/month) |
| 14 | Amazon ECR | Container image registry for agent Docker images | Variable (per-storage) |
| 15 | AWS CodeBuild | Build ARM64 container images for AgentCore Runtime | Variable (per-build-minute) |
| 16 | AWS CloudFormation | Infrastructure as Code deployment (6 stacks) | Free |


## Components and Interfaces

### Component 1: API Gateway (REST Endpoints)

**Purpose:** Entry point for all client interactions — record submission and human review.

**Endpoints:**

| Method | Path | Purpose | Backend |
|--------|------|---------|---------|
| POST | /register | Submit new customer record for dedup | Step Functions Express → Intercept Agent |
| GET | /reviews | List pending merge candidates | Lambda → DynamoDB ReviewQueue |
| GET | /reviews/{reviewId} | Get single review detail | Lambda → DynamoDB ReviewQueue |
| POST | /reviews/{reviewId}/approve | Approve merge | Step Functions Express → Intercept Agent |
| POST | /reviews/{reviewId}/reject | Reject merge | Step Functions Express → Intercept Agent |

**Authentication:** API Key (prototype) — IAM auth for production.

**Request Validation:** API Gateway request models validate JSON schema before forwarding.

**POST /register Request Schema (PERSON):**
```json
{
  "partyType": "PERSON (default if omitted)",
  "firstName": "string (required)",
  "lastName": "string (required)",
  "email": "string (optional)",
  "phone": "string (optional)",
  "dateOfBirth": "string YYYY-MM-DD (optional)",
  "address": {
    "street": "string (optional)",
    "city": "string (optional)",
    "state": "string (optional)",
    "postalCode": "string (optional)",
    "country": "string (optional)"
  },
  "sourceSystem": "string (required) — e.g., OneCRM, NES"
}
```

**POST /register Request Schema (ORGANIZATION):**
```json
{
  "partyType": "ORGANIZATION (required)",
  "partyName": "string (required)",
  "taxRegistrationNum": "string (optional)",
  "taxpayerId": "string (optional)",
  "mdrPidId": "string (optional)",
  "matchMarket": "string (optional)",
  "province": "string (optional)",
  "address": {
    "street": "string (optional)",
    "city": "string (optional)",
    "state": "string (optional)",
    "postalCode": "string (optional)",
    "country": "string (optional)"
  },
  "sourceSystem": "string (required) — e.g., OneCRM, NES"
}
```

**POST /register Response Schema:**
```json
{
  "status": "new_record | duplicate_found | review_pending",
  "customerId": "string (if new record created)",
  "reviewId": "string (if routed to review)",
  "confidenceScore": "number (if duplicate found)",
  "confidenceClassification": "high_confidence | potential_duplicate",
  "matchedRecord": { ... },
  "processingTimeMs": "number"
}
```

### Component 2: Intercept Agent (Proactive Layer)

**Purpose:** Real-time deduplication of incoming records from Sales Systems.

**Deployment:** AgentCore Runtime — FastAPI container on port 8080 with `/invocations` and `/ping` endpoints.

**System Prompt Focus:**
- Single-record, low-latency decision-making
- Invoke QueryCustomerTool with blocking strategy first
- Apply RuleBasedMatchTool, then LLMMatchTool if ambiguous
- Route based on confidence thresholds
- Return structured JSON response

**Invocation Flow:**
1. API Gateway → Step Functions Express → InvokeAgent API → Intercept Agent
2. Agent receives customer record payload
3. Agent invokes QueryCustomerTool (with blocking: postal code + phonetic name)
4. If candidates found → invoke RuleBasedMatchTool
5. If rule-based inconclusive (0.4–0.9) → invoke LLMMatchTool
6. Apply decision routing based on final score
7. Return result to API Gateway via Step Functions

**Performance Target:** < 5 seconds end-to-end (Req 3).

### Component 3: Clean Agent (Reactive Layer)

**Purpose:** Batch deduplication of existing records from S3 dataset.

**Deployment:** AgentCore Runtime — separate container instance from Intercept Agent.

**System Prompt Focus:**
- Batch-oriented processing
- Process records sequentially or in controlled parallel
- Track progress and produce summary statistics
- Optimized for throughput over latency

**Invocation Flow:**
1. S3 upload event (or manual trigger) → Step Functions Standard Workflow
2. Step Functions reads CSV/JSON from S3
3. For each record: invoke Clean Agent via InvokeAgent API
4. Clean Agent runs same matching pipeline as Intercept Agent
5. Results written to ReviewQueue
6. After all records processed: generate summary report → S3

### Component 4: Shared Lambda Tools (7 Functions)

All tools are registered in AgentCore Gateway and invocable by both agents.

#### 4.1 QueryCustomerTool
**Purpose:** Search CustomerTable for potential matches using blocking strategy. Supports both PERSON and ORGANIZATION lookups.
**Input:** Customer fields (partyType determines strategy)

**PERSON strategy:**
1. Apply blocking: query by EmailIndex, PhoneIndex, PostalCodeLastNameIndex GSIs
2. Return deduplicated candidate records within the same block (max 10)

**ORGANIZATION strategy:**
1. Scan with filter on partyType=ORGANIZATION and status=active
2. Narrow by taxRegistrationNum, taxpayerId, or matchMarket if provided
3. Fallback to full org scan for small prototype dataset
4. In production: dedicated GSIs or Oracle EBS REST API queries

**Output:** Array of candidate records (max 10), blockingStrategiesUsed, partyType

#### 4.2 RuleBasedMatchTool
**Purpose:** Stage 1 matching — deterministic rule-based scoring. Supports both PERSON and ORGANIZATION party types.
**Input:** Incoming record + array of candidate records (partyType determines scoring algorithm)

**PERSON Scoring (normalized 0.0–1.0):**
1. Exact match on email → +0.4 score
2. Exact match on phone → +0.3 score
3. Jaro-Winkler on firstName → weighted score (threshold 0.85)
4. Jaro-Winkler on lastName → weighted score (threshold 0.85)
5. Soundex match on name → +0.1 score
6. Date of birth exact match → +0.2 score
7. Normalize and combine scores (cap at 1.0)
Match threshold: 0.6 | High confidence: 0.9

**ORGANIZATION Scoring (cumulative, Oracle TCA "Pearson Organization Duplicates"):**
1. partyName Jaro-Winkler (89 points if JW >= 0.85)
2. partyName Soundex (89 points)
3. address Jaro-Winkler (31 points if JW >= 0.80)
4. city Jaro-Winkler (23 points if JW >= 0.85)
5. postalCode exact (55 points)
6. state exact (15 points)
7. province Jaro-Winkler (17 points if JW >= 0.85)
8. taxRegistrationNum exact (146 points)
9. taxpayerId exact (147 points)
10. mdrPidId exact (145 points)
11. matchMarket exact (148 points)
Match threshold: 144 cumulative | High confidence: 200 cumulative

**Output:** Array of {candidateId, ruleBasedScore (normalized), cumulativeScore (org only), contributingFields, isDefinitive, partyType, scoreType}
**Configuration:** Weights and thresholds loaded from `tools/scoring_config.json`

#### 4.3 LLMMatchTool
**Purpose:** Stage 2 matching — LLM-based fuzzy/semantic matching for ambiguous cases.
**Input:** Incoming record + candidate record + rule-based score
**Trigger:** Only invoked when rule-based score is between 0.4 and 0.9
**Logic:**
1. Construct prompt with both records side-by-side
2. Ask Bedrock model to assess likelihood of same person
3. Model returns confidence score + reasoning
4. Combine with rule-based score (weighted average: 60% rule-based, 40% LLM)
**Output:** {finalScore, llmScore, reasoning, matchingMethod: "rule+llm"}
**Model:** Claude 3 Sonnet (prototype) — evaluate Nova for cost optimization

#### 4.4 CreateCustomerTool
**Purpose:** Insert new customer record into CustomerTable.
**Input:** Customer record fields + sourceSystem
**Logic:** Generate customerId (UUID), set status="active", set timestamps
**Output:** {customerId, status: "created"}

#### 4.5 MergeCustomerTool
**Purpose:** Merge duplicate records (human-approved only).
**Input:** sourceRecordId, targetMasterRecordId, reviewId
**Logic:**
1. Read both records from CustomerTable
2. Consolidate fields (prefer most recent, preserve all source data)
3. Update source record: status="merged", mergedInto=targetMasterRecordId
4. Update master record with consolidated fields
5. Update ReviewQueue: status="approved"
6. NO DELETIONS — source record preserved
**Output:** {mergedRecordId, sourceRecordId, fieldsConsolidated}

#### 4.6 WriteReviewTool
**Purpose:** Write merge candidate to ReviewQueue for human review.
**Input:** Incoming record, matched record, confidence score, classification, method, contributing fields, source agent
**Logic:** Generate reviewId (UUID), set status="pending", set timestamps
**Output:** {reviewId, status: "pending"}

#### 4.7 WriteAuditLogTool
**Purpose:** Write audit log entry to S3.
**Input:** Decision type, records involved, confidence score, agent identifier, rationale
**Logic:** Format as JSON, write to S3 audit bucket with date-partitioned key
**Output:** {auditLogKey, timestamp}


## Data Models

### CustomerTable (DynamoDB)

Simulates Oracle EBS TCA (HZ_PARTIES) for the prototype. Supports both PERSON and ORGANIZATION party types.

| Field | Type | Key | Required | Party Type | Description |
|-------|------|-----|----------|------------|-------------|
| customerId | String | PK | Yes | Both | UUID, unique customer identifier |
| partyType | String | — | No | Both | "PERSON" (default) or "ORGANIZATION" |
| firstName | String | — | Person | Person | Customer first name |
| lastName | String | — | Person | Person | Customer last name |
| partyName | String | — | Org | Organization | Organization name |
| email | String | — | No | Person | Email address |
| phone | String | — | No | Person | Phone number (E.164 format) |
| dateOfBirth | String | — | No | Person | Date of birth (YYYY-MM-DD) |
| address | Map | — | No | Both | {street, city, state, postalCode, country} |
| taxRegistrationNum | String | — | No | Organization | Tax registration number |
| taxpayerId | String | — | No | Organization | Taxpayer identifier |
| mdrPidId | String | — | No | Organization | MDR PID identifier |
| matchMarket | String | — | No | Organization | Market segment (e.g., US-EDUCATION) |
| province | String | — | No | Organization | Province (for non-US addresses) |
| sourceSystem | String | — | Yes | Both | Origin system (OneCRM, NES) |
| status | String | — | Yes | Both | "active" or "merged" |
| mergedInto | String | — | No | Both | customerId of master record (if merged) |
| createdAt | String | — | Yes | Both | ISO 8601 timestamp |
| updatedAt | String | — | Yes | Both | ISO 8601 timestamp |

**GSI-1 (EmailIndex):** email (PK) — for exact email lookup
**GSI-2 (PhoneIndex):** phone (PK) — for exact phone lookup
**GSI-3 (PostalCodeLastNameIndex):** postalCode (PK), lastName (SK) — for blocking strategy

### ReviewQueue (DynamoDB)

| Field | Type | Key | Required | Description |
|-------|------|-----|----------|-------------|
| reviewId | String | PK | Yes | UUID, unique review identifier |
| incomingRecord | Map | — | Yes | Full incoming customer record |
| matchedRecord | Map | — | Yes | Full matched customer record from CustomerTable |
| confidenceScore | Number | — | Yes | Final score 0.0–1.0 |
| confidenceClassification | String | — | Yes | "high_confidence" or "potential_duplicate" |
| matchingMethod | String | — | Yes | "rule_based" or "rule+llm" |
| contributingFields | List | — | Yes | Fields that contributed to the score |
| sourceAgent | String | — | Yes | "intercept" or "clean" |
| status | String | — | Yes | "pending", "approved", or "rejected" |
| reviewedBy | String | — | No | Data Steward identifier |
| reviewedAt | String | — | No | ISO 8601 timestamp |
| createdAt | String | — | Yes | ISO 8601 timestamp |

**GSI-1 (StatusIndex):** status (PK), createdAt (SK) — for listing pending reviews

### Audit Log (S3 JSON)

Stored in S3 with key pattern: `audit-logs/{YYYY}/{MM}/{DD}/{timestamp}-{eventType}.json`

```json
{
  "auditId": "uuid",
  "timestamp": "ISO 8601",
  "eventType": "match_recommendation | new_record | merge_approved | merge_rejected | review_routed | override",
  "sourceAgent": "intercept | clean",
  "sourceSystem": "OneCRM | NES",
  "confidenceScore": 0.85,
  "incomingRecordId": "uuid",
  "matchedRecordId": "uuid (if applicable)",
  "reviewId": "uuid (if applicable)",
  "decision": "description of decision",
  "rationale": "why this decision was made",
  "reviewedBy": "steward-id (if human action)",
  "originalRecommendation": "string (if override)",
  "fieldsConsolidated": ["field1", "field2"]
}
```

### Batch Summary Report (S3 JSON)

Stored in S3 with key pattern: `batch-reports/{YYYY}/{MM}/{DD}/{batchId}-summary.json`

```json
{
  "batchId": "uuid",
  "timestamp": "ISO 8601",
  "sourceFile": "s3://bucket/path/to/input.csv",
  "totalRecordsScanned": 500,
  "duplicatesIdentified": 45,
  "highConfidenceDuplicates": 20,
  "potentialDuplicates": 25,
  "newRecordsCreated": 455,
  "reviewsCreated": 45,
  "processingDurationSeconds": 120,
  "averageProcessingTimePerRecord": 0.24
}
```

## Data Flow: Real-Time (Proactive Layer)

```
1. Client (Postman) → POST /register {customer record}
2. API Gateway validates schema → forwards to Step Functions Express
3. Step Functions → InvokeAgent API → Intercept Agent on AgentCore Runtime
4. Intercept Agent:
   a. Invokes QueryCustomerTool (blocking: postalCode + Soundex lastName)
   b. If no candidates → invokes CreateCustomerTool → returns "new_record"
   c. If candidates found → invokes RuleBasedMatchTool
   d. If rule-based definitive (≥0.9 or <0.4) → apply decision
   e. If rule-based ambiguous (0.4–0.9) → invokes LLMMatchTool
   f. Final score ≥0.9 → WriteReviewTool (high_confidence) + WriteAuditLogTool
   g. Final score 0.6–0.9 → WriteReviewTool (potential_duplicate) + WriteAuditLogTool
   h. Final score <0.6 → CreateCustomerTool + WriteAuditLogTool
5. Step Functions returns result → API Gateway → Client
```

## Data Flow: Batch (Reactive Layer)

```
1. Upload CSV/JSON to S3 batch bucket (or manual trigger via API)
2. S3 event notification → Step Functions Standard Workflow
3. Step Functions:
   a. Reads file from S3, parses records
   b. For each record: InvokeAgent API → Clean Agent on AgentCore Runtime
   c. Clean Agent runs same pipeline as Intercept Agent (steps 4a–4h above)
   d. Tracks progress counters
4. After all records processed:
   a. Generate summary report JSON
   b. Write report to S3 batch-reports bucket
5. Step Functions completes → summary available in S3
```

## Data Flow: Human Review

```
1. Data Steward → GET /reviews (lists pending reviews)
2. API Gateway → Lambda → DynamoDB ReviewQueue (status="pending")
3. Data Steward reviews side-by-side comparison
4. Data Steward → POST /reviews/{reviewId}/approve
5. API Gateway → Step Functions Express → Intercept Agent
6. Intercept Agent:
   a. Invokes MergeCustomerTool (consolidate records, preserve source)
   b. Invokes WriteAuditLogTool (log approval)
7. Response returned to Data Steward

OR

4. Data Steward → POST /reviews/{reviewId}/reject
5. API Gateway → Step Functions Express → Intercept Agent
6. Intercept Agent:
   a. Updates ReviewQueue status="rejected"
   b. Invokes WriteAuditLogTool (log rejection)
7. Response returned to Data Steward
```


## Error Handling

### Error Categories and Responses

| Error Type | HTTP Code | Scenario | System Action |
|------------|-----------|----------|---------------|
| Validation | 400 | Malformed JSON, missing required fields | API Gateway returns field-level errors |
| Auth | 403 | Invalid/missing API key | API Gateway rejects request |
| Not Found | 404 | reviewId doesn't exist | Lambda returns error |
| Conflict | 409 | Review already approved/rejected | Lambda returns current status |
| Agent Timeout | 504 | Intercept Agent exceeds 5s SLA | Step Functions timeout → return partial result |
| Tool Failure | 500 | Lambda tool invocation fails | Agent retries 3x with exponential backoff, then returns error |
| Bedrock Throttle | 429 | LLM rate limit exceeded | Lambda retries with backoff, falls back to rule-based score only |
| DynamoDB Throttle | 429 | Read/write capacity exceeded | Lambda retries with backoff (DynamoDB on-demand handles most cases) |

### Retry Strategy

All Lambda tool invocations use exponential backoff:
- Attempt 1: immediate
- Attempt 2: 1 second delay
- Attempt 3: 3 seconds delay
- After 3 failures: log error, return failure response to agent

### Fallback Behavior

If LLMMatchTool fails (Bedrock unavailable/throttled):
- Use rule-based score only
- If rule-based score is 0.4–0.9 (ambiguous), route to ReviewQueue as "potential_duplicate" with note "LLM matching unavailable — rule-based score only"
- Log the fallback in audit log

## Security Design

### Encryption
- **At rest:** AWS KMS customer-managed key (CMK) for DynamoDB (CustomerTable, ReviewQueue) and S3 (all buckets)
- **In transit:** TLS 1.2+ enforced on API Gateway, Lambda-to-DynamoDB, Lambda-to-S3, AgentCore communications

### IAM Policies (Least Privilege)

| Component | Permissions |
|-----------|------------|
| API Gateway | Execute Step Functions only |
| Step Functions | InvokeAgent on AgentCore Runtime only |
| Intercept Agent / Clean Agent | Invoke Lambda tools via AgentCore Gateway only |
| QueryCustomerTool Lambda | DynamoDB:Query, DynamoDB:GetItem on CustomerTable only |
| CreateCustomerTool Lambda | DynamoDB:PutItem on CustomerTable only |
| MergeCustomerTool Lambda | DynamoDB:UpdateItem on CustomerTable, DynamoDB:UpdateItem on ReviewQueue |
| WriteReviewTool Lambda | DynamoDB:PutItem on ReviewQueue only |
| WriteAuditLogTool Lambda | S3:PutObject on audit bucket only |
| RuleBasedMatchTool Lambda | No AWS resource access (pure compute) |
| LLMMatchTool Lambda | Bedrock:InvokeModel only |

### PII Masking
- CloudWatch logs: mask email, phone, dateOfBirth, address fields
- Full PII stored only in encrypted DynamoDB tables and S3 audit logs
- Log only customerId, confidence scores, and decision metadata

## Testing Strategy (Prototype Demo)

### Demo Scenarios

**Scenario 1: New Customer (No Duplicate)**
- POST /register with unique customer
- Expected: status="new_record", customerId returned
- Verify: record exists in CustomerTable

**Scenario 2: High-Confidence Duplicate (≥0.9)**
- Seed CustomerTable with existing record
- POST /register with near-identical record (same email, similar name)
- Expected: status="review_pending", confidenceClassification="high_confidence"
- Verify: review record in ReviewQueue

**Scenario 3: Potential Duplicate (0.6–0.9)**
- POST /register with partially matching record (similar name, different email)
- Expected: status="review_pending", confidenceClassification="potential_duplicate"
- Triggers LLM matching for ambiguous case

**Scenario 4: Approve Merge**
- GET /reviews → list pending reviews
- POST /reviews/{reviewId}/approve
- Verify: source record status="merged", master record updated, audit log written

**Scenario 5: Reject Merge**
- POST /reviews/{reviewId}/reject
- Verify: ReviewQueue status="rejected", audit log written, no data changes

**Scenario 5a: New Organization (No Duplicate)**
- POST /register with partyType=ORGANIZATION, unique partyName and taxRegistrationNum
- Expected: status="new_record", customerId returned
- Verify: record exists in CustomerTable with partyType=ORGANIZATION

**Scenario 5b: Organization Duplicate Detection**
- POST /register with partyType=ORGANIZATION, matching partyName + taxpayerId of existing org
- Expected: status="review_pending", cumulative score >= 144
- Verify: review record in ReviewQueue with partyType=ORGANIZATION, cumulative score shown

**Scenario 5c: Organization Merge Approval**
- GET /reviews → find pending org review
- POST /reviews/{reviewId}/approve
- Verify: source org record status="merged", master org record stays active

**Scenario 6: Batch Deduplication**
- Upload CSV with 10-20 records (mix of duplicates and unique) to S3
- Trigger batch pipeline
- Verify: ReviewQueue populated, summary report in S3

### Test Data

Pre-seed CustomerTable with 20 person + 5 organization sample records covering:
- Exact duplicates (same email/phone for persons, same taxpayerId for orgs)
- Near-duplicates (typos in names: "Chris" vs "Chrish", "Pearson Education Inc." vs "Pearson Edu")
- Same entity, different source systems (OneCRM vs NES)
- Completely unique records (persons and orgs)
- Edge cases: missing fields, partial addresses, international phone formats
- Organization records with varying match attributes (same taxpayerId but different partyName, etc.)

## Prototype Deployment Architecture

```
Region: us-east-1

AgentCore Runtime:
  ├── Intercept Agent (container, port 8080)
  │   ├── /invocations (POST)
  │   └── /ping (GET)
  └── Clean Agent (container, port 8080)
      ├── /invocations (POST)
      └── /ping (GET)

AgentCore Gateway:
  └── Tool Registry (7 Lambda tools registered)

API Gateway:
  └── REST API (dedup-api)
      ├── /register (POST)
      ├── /reviews (GET)
      ├── /reviews/{reviewId} (GET)
      ├── /reviews/{reviewId}/approve (POST)
      └── /reviews/{reviewId}/reject (POST)

Lambda Functions (Python 3.11):
  ├── query-customer-tool
  ├── create-customer-tool
  ├── merge-customer-tool
  ├── rule-based-match-tool
  ├── llm-match-tool
  ├── write-review-tool
  ├── write-audit-log-tool
  └── get-reviews (direct API Gateway integration)

DynamoDB Tables:
  ├── CustomerTable (on-demand, KMS encrypted)
  │   ├── GSI: EmailIndex
  │   ├── GSI: PhoneIndex
  │   └── GSI: PostalCodeLastNameIndex
  └── ReviewQueue (on-demand, KMS encrypted)
      └── GSI: StatusIndex

S3 Buckets:
  ├── dedup-batch-input (batch CSV/JSON files)
  ├── dedup-audit-logs (audit trail, lifecycle: 90 days)
  └── dedup-batch-reports (summary reports)

Step Functions:
  ├── dedup-realtime-workflow (Express, sync)
  └── dedup-batch-workflow (Standard, async)

CloudWatch:
  ├── /aws/agentcore/intercept-agent (log group)
  ├── /aws/agentcore/clean-agent (log group)
  ├── /aws/lambda/dedup-tools (log group)
  └── Alarms: Lambda errors, API Gateway 5xx, agent latency >5s

KMS:
  └── dedup-cmk (customer-managed key for all encryption)

Secrets Manager:
  └── oracle-ebs-credentials (placeholder for production)
```

## Production Swap: DynamoDB → Oracle EBS

The architecture is designed so that moving from prototype to production requires only Lambda tool code changes:

| Component | Prototype | Production | Change Required |
|-----------|-----------|------------|-----------------|
| QueryCustomerTool | DynamoDB Query/Scan | Oracle EBS REST API (HZ_PARTIES) | Lambda code only |
| CreateCustomerTool | DynamoDB PutItem | Oracle EBS REST API (create party) | Lambda code only |
| MergeCustomerTool | DynamoDB UpdateItem | Oracle EBS REST API (merge party) | Lambda code only |
| Intercept Agent | No change | No change | None |
| Clean Agent | No change | No change | None |
| API Gateway | No change | No change | None |
| Matching Pipeline | No change | No change | None |
| ReviewQueue | DynamoDB | DynamoDB (stays) | None |

## Requirements Traceability

| Requirement | Design Component | Status |
|-------------|-----------------|--------|
| Req 1: API Gateway | API Gateway REST endpoints, request schemas | Covered |
| Req 2: Intercept Agent | AgentCore Runtime deployment, system prompt, invocation flow | Covered |
| Req 2a: Clean Agent | Separate AgentCore Runtime deployment, batch system prompt | Covered |
| Req 3: Real-Time Detection | Step Functions Express, <5s SLA, QueryCustomerTool with blocking | Covered |
| Req 4: Two-Stage Matching | RuleBasedMatchTool + LLMMatchTool, score combination logic | Covered |
| Req 5: Decision Routing | Confidence thresholds in agent logic, WriteReviewTool/CreateCustomerTool | Covered |
| Req 6: Human Review | GET/POST /reviews endpoints, MergeCustomerTool, WriteAuditLogTool | Covered |
| Req 7: No-Deletion Policy | MergeCustomerTool preserves source records (status="merged") | Covered |
| Req 8: Data Store Integration | Lambda tools abstract DynamoDB, swappable to Oracle EBS | Covered |
| Req 9: Batch Pipeline | Step Functions Standard + Clean Agent + S3 input/output | Covered |
| Req 10: Audit Logging | WriteAuditLogTool → S3, structured JSON with all required fields | Covered |
| Req 11: Security | KMS CMK, TLS 1.2+, least-privilege IAM, PII masking | Covered |
| Req 12: Observability | CloudWatch log groups per agent, Lambda error alarms | Covered |
