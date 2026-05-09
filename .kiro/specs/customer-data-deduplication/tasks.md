# Implementation Tasks: Customer Data Deduplication Prototype

## Phase 1: Foundation & Infrastructure

- [x] 1. Project Setup and AWS Infrastructure
  - [x] 1.1 Create project directory structure
    - Create `infra/` (SAM/CloudFormation templates), `agents/` (Intercept + Clean agent code), `tools/` (Lambda functions), `tests/` (test data + scripts), `scripts/` (deployment helpers)
    - Create `requirements.txt` for shared Python dependencies
    - Create `.env.example` with required environment variables
    - _Requirements: All_

  - [x] 1.2 Create DynamoDB tables (SAM template)
    - Define CustomerTable with on-demand capacity, KMS encryption
    - Add GSI: EmailIndex (email PK), PhoneIndex (phone PK), PostalCodeLastNameIndex (postalCode PK, lastName SK)
    - Define ReviewQueue with on-demand capacity, KMS encryption
    - Add GSI: StatusIndex (status PK, createdAt SK)
    - _Requirements: Req 8, Req 11_

  - [x] 1.3 Create S3 buckets (SAM template)
    - Create `dedup-batch-input` bucket (batch CSV/JSON uploads)
    - Create `dedup-audit-logs` bucket (audit trail, 90-day lifecycle)
    - Create `dedup-batch-reports` bucket (summary reports)
    - Enable KMS encryption on all buckets
    - _Requirements: Req 9, Req 10, Req 11_

  - [x] 1.4 Create KMS key and IAM roles (SAM template)
    - Create customer-managed KMS key (`dedup-cmk`)
    - Create IAM execution role per Lambda tool (least-privilege)
    - Create IAM role for Step Functions execution
    - Create IAM role for API Gateway to invoke Step Functions
    - _Requirements: Req 11_

  - [x] 1.5 Seed test data into CustomerTable
    - Create `tests/seed-data.json` with 50-100 sample customer records
    - Include exact duplicates, near-duplicates (typos), cross-system records (OneCRM vs NES), unique records, edge cases (missing fields)
    - Create seed script (`scripts/seed-data.py`) to load into DynamoDB
    - _Requirements: Req 3, Req 4_

## Phase 2: Lambda Tools (Shared by Both Agents)

- [x] 2. Data Store Tools
  - [x] 2.1 Implement QueryCustomerTool Lambda
    - Accept customer fields as input (name, email, phone, postalCode)
    - Apply blocking strategy: query PostalCodeLastNameIndex first, then EmailIndex and PhoneIndex for exact lookups
    - Return max 10 candidate records
    - Include PII masking in CloudWatch logs
    - Write unit tests with mocked DynamoDB
    - _Requirements: Req 4 AC1, Req 8 AC1, Req 12_

  - [x] 2.2 Implement CreateCustomerTool Lambda
    - Accept customer record fields + sourceSystem
    - Generate UUID for customerId, set status="active", set timestamps
    - PutItem to CustomerTable
    - Return {customerId, status: "created"}
    - Write unit tests
    - _Requirements: Req 5 AC2, Req 8 AC2_

  - [x] 2.3 Implement MergeCustomerTool Lambda
    - Accept sourceRecordId, targetMasterRecordId, reviewId
    - Read both records, consolidate fields (prefer most recent)
    - Update source record: status="merged", mergedInto=targetMasterRecordId
    - Update master record with consolidated fields
    - Update ReviewQueue: status="approved", reviewedBy, reviewedAt
    - NO DELETE operations
    - Return {mergedRecordId, sourceRecordId, fieldsConsolidated}
    - Write unit tests
    - _Requirements: Req 7, Req 8 AC3_

- [x] 3. Matching Pipeline Tools
  - [x] 3.1 Implement RuleBasedMatchTool Lambda
    - Accept incoming record + array of candidate records
    - Implement scoring: email exact (+0.4), phone exact (+0.3), Jaro-Winkler firstName (threshold 0.85), Jaro-Winkler lastName (threshold 0.85), Soundex name (+0.1), DOB exact (+0.2)
    - Install `jellyfish` library for Jaro-Winkler and Soundex
    - Normalize and cap combined score at 1.0
    - Return array of {candidateId, ruleBasedScore, contributingFields, isDefinitive}
    - Write unit tests with known match/non-match pairs
    - _Requirements: Req 4 AC2_

  - [x] 3.2 Implement LLMMatchTool Lambda
    - Accept incoming record + candidate record + rule-based score
    - Only process when rule-based score is 0.4–0.9
    - Construct Bedrock prompt with both records side-by-side, ask for confidence assessment + reasoning
    - Call Bedrock InvokeModel (Claude 3 Sonnet)
    - Parse LLM response, extract confidence score
    - Combine scores: 60% rule-based + 40% LLM
    - Return {finalScore, llmScore, reasoning, matchingMethod: "rule+llm"}
    - Implement fallback: if Bedrock fails, return rule-based score with note
    - Write unit tests with mocked Bedrock responses
    - _Requirements: Req 4 AC3, Req 4 AC4_

- [x] 4. Review and Audit Tools
  - [x] 4.1 Implement WriteReviewTool Lambda
    - Accept incoming record, matched record, confidence score, classification, method, contributing fields, source agent
    - Generate UUID for reviewId, set status="pending", set timestamps
    - PutItem to ReviewQueue
    - Return {reviewId, status: "pending"}
    - Write unit tests
    - _Requirements: Req 5 AC1, Req 5 AC3, Req 6 AC1_

  - [x] 4.2 Implement WriteAuditLogTool Lambda
    - Accept decision type, records involved, confidence score, agent identifier, rationale
    - Format as structured JSON
    - Write to S3 audit bucket with key: `audit-logs/{YYYY}/{MM}/{DD}/{timestamp}-{eventType}.json`
    - Mask PII in log output
    - Return {auditLogKey, timestamp}
    - Write unit tests
    - _Requirements: Req 10_

  - [x] 4.3 Implement GetReviews Lambda (direct API Gateway integration)
    - Query ReviewQueue StatusIndex where status="pending"
    - Return array of review records with side-by-side comparison
    - Support single review lookup by reviewId
    - Write unit tests
    - _Requirements: Req 6 AC2_

## Phase 3: AgentCore Agents

- [x] 5. Intercept Agent (Proactive Layer)
  - [x] 5.1 Create Intercept Agent FastAPI application
    - Create `agents/intercept/agent.py` with FastAPI app
    - Implement POST `/invocations` endpoint
    - Implement GET `/ping` health check
    - Define Pydantic request/response models
    - Add structured logging
    - _Requirements: Req 2_

  - [x] 5.2 Implement Intercept Agent orchestration logic
    - Parse incoming customer record from invocation payload
    - Implement tool invocation flow: QueryCustomerTool → RuleBasedMatchTool → (conditional) LLMMatchTool → decision routing
    - Apply confidence thresholds: ≥0.9 high-confidence, 0.6–0.9 potential, <0.6 new record
    - Call WriteReviewTool or CreateCustomerTool based on decision
    - Call WriteAuditLogTool for every decision
    - Handle review approval/rejection flows (MergeCustomerTool)
    - Implement retry logic (3x with exponential backoff) for tool failures
    - _Requirements: Req 2, Req 3, Req 5_

  - [x] 5.3 Write Intercept Agent system prompt
    - Optimize for low-latency, single-record real-time decisions
    - Define tool usage instructions and decision logic
    - Include confidence threshold definitions
    - Include response format instructions (structured JSON)
    - _Requirements: Req 2 AC8_

  - [x] 5.4 Create Intercept Agent Dockerfile
    - Use `python:3.11-slim` base image (NOT Lambda base)
    - Install FastAPI, uvicorn, pydantic, boto3
    - Expose port 8080
    - CMD: `uvicorn agent:app --host 0.0.0.0 --port 8080`
    - Test locally with curl before deploying
    - _Requirements: Req 2 AC1_

- [x] 6. Clean Agent (Reactive Layer)
  - [x] 6.1 Create Clean Agent FastAPI application
    - Create `agents/clean/agent.py` with FastAPI app
    - Implement POST `/invocations` endpoint (accepts single record or batch reference)
    - Implement GET `/ping` health check
    - Add structured logging
    - _Requirements: Req 2a_

  - [x] 6.2 Implement Clean Agent orchestration logic
    - Same matching pipeline as Intercept Agent (shared tool invocations)
    - Optimized for batch context: track progress counters, handle partial failures
    - Apply same confidence thresholds and decision routing
    - _Requirements: Req 2a, Req 9_

  - [x] 6.3 Write Clean Agent system prompt
    - Optimize for batch throughput and bulk comparison
    - Include batch-specific instructions (progress tracking, error tolerance)
    - Same tool usage and threshold definitions as Intercept Agent
    - _Requirements: Req 2a AC5_

  - [x] 6.4 Create Clean Agent Dockerfile
    - Same structure as Intercept Agent Dockerfile
    - Separate container image for independent deployment
    - Test locally before deploying
    - _Requirements: Req 2a AC1_

## Phase 4: API Gateway & Step Functions

- [x] 7. API Gateway and Orchestration
  - [x] 7.1 Create API Gateway REST API (SAM template)
    - Define POST /register with request validation model
    - Define GET /reviews → GetReviews Lambda integration
    - Define GET /reviews/{reviewId} → GetReviews Lambda integration
    - Define POST /reviews/{reviewId}/approve → Step Functions integration
    - Define POST /reviews/{reviewId}/reject → Step Functions integration
    - Configure API key authentication
    - Enable CORS for Postman testing
    - _Requirements: Req 1_

  - [x] 7.2 Create Step Functions Express Workflow (real-time)
    - Define state machine: receive payload → InvokeAgent (Intercept Agent) → return result
    - Set 10-second timeout (buffer for 5s SLA)
    - Configure error handling and retry
    - Wire to API Gateway POST /register, /approve, /reject
    - _Requirements: Req 1 AC2, Req 3 AC1_

  - [x] 7.3 Create Step Functions Standard Workflow (batch)
    - Define state machine: read S3 file → parse records → Map state (invoke Clean Agent per record) → generate summary → write report to S3
    - Configure S3 event notification trigger on batch-input bucket
    - Add manual trigger option via StartExecution API
    - Set appropriate timeouts for batch processing
    - _Requirements: Req 9_

## Phase 5: AgentCore Deployment

- [x] 8. Deploy Agents to AgentCore
  - [x] 8.1 Build and push Docker images to ECR
    - Create ECR repositories for intercept-agent and clean-agent
    - Build ARM64 images for both agents
    - Push to ECR
    - Validate images locally before push
    - _Requirements: Req 2 AC1, Req 2a AC1_

  - [x] 8.2 Deploy Intercept Agent to AgentCore Runtime
    - Create AgentCore Runtime for Intercept Agent
    - Configure with ECR image URI
    - Verify status=READY
    - Test /ping and /invocations endpoints
    - _Requirements: Req 2 AC1_

  - [x] 8.3 Deploy Clean Agent to AgentCore Runtime
    - Create AgentCore Runtime for Clean Agent (separate instance)
    - Configure with ECR image URI
    - Verify status=READY
    - Test /ping and /invocations endpoints
    - _Requirements: Req 2a AC1_

  - [x] 8.4 Register Lambda tools in AgentCore Gateway
    - Register all 7 Lambda tools as MCP-compatible tools
    - Configure tool descriptions and input schemas for agent discovery
    - Configure AgentCore Identity trust policies
    - Test tool invocation from both agents
    - _Requirements: Req 2 AC2, Req 2a AC6_

## Phase 6: Integration & CloudWatch

- [x] 9. Observability and Monitoring
  - [x] 9.1 Configure CloudWatch log groups
    - Create `/aws/agentcore/intercept-agent` log group
    - Create `/aws/agentcore/clean-agent` log group
    - Create `/aws/lambda/dedup-tools` log group
    - Set retention policies (30 days for prototype)
    - _Requirements: Req 12_

  - [x] 9.2 Create CloudWatch alarms
    - Lambda error rate alarm (>5% errors in 5 minutes)
    - API Gateway 5xx alarm
    - Intercept Agent latency alarm (>5 seconds p99)
    - Step Functions execution failure alarm
    - _Requirements: Req 12_

## Phase 7: End-to-End Testing & Demo Prep

- [x] 10a. Organization Dedup Implementation (Unified Person + Organization)
  - [x] 10a.1 Create scoring configuration file
    - Create `tools/scoring_config.json` with PERSON (normalized) and ORGANIZATION (cumulative) scoring configs
    - PERSON: weights for email, phone, name JW/Soundex, DOB; threshold 0.6; high_confidence 0.9
    - ORGANIZATION: Oracle TCA weights (partyName 89, address 31, city 23, postalCode 55, state 15, province 17, taxReg 146, taxpayerId 147, mdrPidId 145, matchMarket 148); threshold 144; high_confidence 200
    - _Requirements: Req 0 AC4, AC5, AC8_

  - [x] 10a.2 Update RuleBasedMatchTool for dual party type scoring
    - Add `_score_org_pair()` function with cumulative scoring logic
    - Implement Jaro-Winkler on partyName (threshold 0.85), address (threshold 0.80), city, province
    - Implement exact match on postalCode, state, taxRegistrationNum, taxpayerId, mdrPidId, matchMarket
    - Return both normalized score and cumulative score for organizations
    - Detect partyType from incoming record, route to correct scoring function
    - _Requirements: Req 0 AC2, AC3, AC4_

  - [x] 10a.3 Update QueryCustomerTool for organization lookups
    - Add `_scan_organizations()` function using DynamoDB scan with filter expressions
    - Filter by partyType=ORGANIZATION and status=active
    - Narrow by taxRegistrationNum, taxpayerId, matchMarket when available
    - Fallback to full org scan for prototype dataset
    - _Requirements: Req 0 AC7_

  - [x] 10a.4 Add organization seed data
    - Add 5 organization records to `tests/seed-data.json`: Pearson Education Inc. (OneCRM), Pearson Education (NES), McGraw Hill LLC (OneCRM), Pearson Edu (NES, typo variant), Random Corp (OneCRM)
    - Include org-specific fields: partyType, partyName, taxRegistrationNum, taxpayerId, mdrPidId, matchMarket
    - _Requirements: Req 0 AC6_

  - [x] 10a.5 Update demo-reset.py for organization records
    - Seed organization records alongside person records
    - Print org record summary in demo output
    - Add Scenario 5 (Register Organization) to demo instructions
    - _Requirements: Req 0 AC9_

  - [x] 10a.6 Update Dashboard for organization support
    - Add Organization registration form with org-specific fields (partyName, taxReg, taxpayerId, mdrPidId, matchMarket)
    - Add Party Type filter on Accounts tab and Duplicate Reviews tab
    - Display cumulative score for organization reviews
    - Show org-specific fields in review side-by-side comparison
    - Add Person vs Organization pie chart on Dashboard tab
    - _Requirements: Req 0 AC9_

  - [x] 10a.7 Deploy updated Lambda tools to AWS
    - Update rule-based-match-tool Lambda with org scoring code
    - Update query-customer-tool Lambda with org scan code
    - Upload scoring_config.json to Lambda deployment package
    - Update create-customer-tool Lambda with org field support
    - Update write-review-tool Lambda with float-to-Decimal conversion
    - Update agent proxy Lambdas (intercept + clean) with all tool changes
    - Install jellyfish for Python 3.13 Linux x86_64 in Lambda packages
    - Update API Gateway model to accept organization fields (relaxed validation)
    - Update Bedrock model ID to amazon.nova-pro-v1:0 across all Lambdas
    - Verify both tools work for Person and Organization payloads
    - _Requirements: Req 0 AC2, AC3, AC7_

  - [x] 10a.8 Redeploy agents to AgentCore Runtime
    - Agent proxy Lambdas updated with org-aware tool code (AgentCore Runtime agents use same tools)
    - Both intercept and clean agent proxies handle Person and Organization records
    - _Requirements: Req 2, Req 2a_

  - [x] 10a.9 End-to-end test: Organization dedup flow
    - Run demo-reset.py to seed 5 org records + 22 person records
    - Register new unique org (Acme Corp) → verified new_record (score 0.18)
    - Register duplicate org (Pearson Education) → verified review_pending (score 0.98, high_confidence)
    - Person dedup verified still working (Chris James → 100%, new unique → 0%)
    - _Requirements: Req 0 AC10_

- [ ] 10. Integration Testing and Demo
  - [ ] 10.1 End-to-end test: New customer (no duplicate)
    - POST /register with unique customer record
    - Verify: HTTP 200, status="new_record", customerId returned
    - Verify: record exists in CustomerTable with status="active"
    - Verify: audit log written to S3
    - _Requirements: Req 3 AC3, Req 5 AC2_

  - [ ] 10.2 End-to-end test: High-confidence duplicate (≥0.9)
    - Seed CustomerTable with existing record
    - POST /register with near-identical record (same email, similar name)
    - Verify: status="review_pending", confidenceClassification="high_confidence"
    - Verify: review record in ReviewQueue with correct details
    - _Requirements: Req 3 AC2, Req 5 AC1_

  - [ ] 10.3 End-to-end test: Potential duplicate (0.6–0.9, triggers LLM)
    - POST /register with partially matching record (similar name, different email)
    - Verify: LLMMatchTool invoked, status="review_pending", confidenceClassification="potential_duplicate"
    - Verify: matchingMethod="rule+llm" in ReviewQueue
    - _Requirements: Req 4 AC3, Req 5 AC3_

  - [ ] 10.4 End-to-end test: Approve merge
    - GET /reviews → verify pending review listed
    - POST /reviews/{reviewId}/approve
    - Verify: source record status="merged", mergedInto set, master record updated
    - Verify: ReviewQueue status="approved"
    - Verify: audit log records approval
    - _Requirements: Req 6 AC3, Req 7 AC3_

  - [ ] 10.5 End-to-end test: Reject merge
    - POST /reviews/{reviewId}/reject
    - Verify: ReviewQueue status="rejected", no data changes to CustomerTable
    - Verify: audit log records rejection
    - _Requirements: Req 6 AC4_

  - [ ] 10.6 End-to-end test: Batch deduplication
    - Upload CSV with 10-20 records (mix of duplicates and unique) to S3
    - Verify: Step Functions batch workflow triggers
    - Verify: ReviewQueue populated with merge candidates
    - Verify: summary report written to S3 with correct counts
    - _Requirements: Req 9_

  - [x] 10.7 Create Postman collection for client demo
    - Create collection with all 5 API endpoints
    - Add example requests for each demo scenario
    - Add environment variables (API URL, API key)
    - Include pre-request scripts for seeding test data
    - Document demo walkthrough steps
    - _Requirements: Req 1_
