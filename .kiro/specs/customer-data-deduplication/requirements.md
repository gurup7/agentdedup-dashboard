# Requirements Document

## Introduction

This document defines the requirements for a Customer Data Deduplication Prototype powered by Amazon Bedrock AgentCore on AWS. The system addresses duplicate customer records originating from multiple disconnected sales systems (e.g., OneCRM, NES) that feed into a customer data store as the system of record. Two specialized AI agents hosted on AgentCore Runtime act as an AI middleware layer: the Intercept Agent for real-time deduplication of incoming records, and the Clean Agent for batch deduplication of existing records. Both agents identify duplicates and recommend merge actions to human reviewers.

**Scope**: This prototype addresses customer data deduplication exclusively for the Sales (OneCRM, NES) → TEP Oracle EBS pathway. Other upstream systems shown in the FPSC Functional Architecture — including eCommerce Orders (PMC/Hybris), Subscription Billing and Revenue (Zuora), Service (ServiceNow, SFDC Service Cloud), MDM (DRM), and manual order entry within TEP — are explicitly out of scope for this phase. Future phases may extend deduplication coverage to additional source systems.

The prototype implements a two-layer architecture:

- **Proactive Layer (Intercept Agent)**: Sits between Sales Systems and the customer data store. Intercepts new customer records submitted via API Gateway (simulated via Postman/curl). The API Gateway forwards the payload to the Intercept Agent, which runs the matching pipeline and either creates a new record or writes a merge candidate to the ReviewQueue for human decision.
- **Reactive Layer (Clean Agent)**: Processes existing customer records in batch. Reads a static CSV/JSON file from S3, runs each record through the matching pipeline via Lambda or Step Functions, and writes merge candidates to the ReviewQueue. A summary report is written to S3.

The two agents are deployed independently on AgentCore Runtime, each with its own system prompt optimized for its specific task. Both agents use LangGraph as the agentic orchestration framework, where Amazon Bedrock Claude dynamically decides which tools to call and in what order based on the data it encounters. Both agents share the SAME Lambda tools and two-stage matching pipeline — only the trigger mechanism, operational context, and system prompt differ (API Gateway for the Intercept Agent, S3 event/manual trigger for the Clean Agent).

Both agents drive decision-making (duplicate recommendation, new record, or human review) through a LangGraph StateGraph that loops between LLM calls and tool execution. The LLM invokes tools dynamically via AgentCore Gateway — including Lambda functions to query the customer data store, rule-based matching via Lambda, and Amazon Bedrock for LLM-based fuzzy matching. The prototype uses a two-stage matching pipeline: (1) rule-based checks via Lambda (exact match on email/phone, fuzzy match with Soundex/Jaro-Winkler on name) and (2) LLM-based fuzzy matching via Bedrock for ambiguous edge cases.

For the prototype, Oracle EBS is simulated by a DynamoDB CustomerTable. Lambda tools (QueryCustomerTool, CreateCustomerTool, MergeCustomerTool) operate against DynamoDB. In production, only the Lambda tool implementations change to call Oracle EBS REST APIs — the agents, API contracts, and matching logic stay the same. Neither agent talks to the data store directly; they always operate through Lambda tools via AgentCore Gateway.

Human review is handled via a DynamoDB ReviewQueue table. Data Stewards review pending merge candidates and approve or reject them via API Gateway endpoints (Postman/curl). Confidence score thresholds are hardcoded for the prototype: >= 0.9 high-confidence duplicate recommended to human, 0.6–0.9 potential duplicate routed to human, < 0.6 new record created. All merge actions require human approval — no auto-merge is performed. No customer records are deleted; all deduplication actions are merge operations that consolidate data while preserving source records. Basic CloudWatch logging is used for debugging and monitoring across all components, with separate log groups per agent.

## Glossary

- **Intercept_Agent**: The AI agent hosted on Amazon Bedrock AgentCore Runtime responsible for the Proactive Layer (Agentic Dedup Layer [Intercept]). It uses LangGraph as the orchestration framework with Amazon Bedrock Claude as the reasoning LLM. It sits between Sales Systems and TEP Oracle EBS, intercepting new customer records in real-time via API Gateway, dynamically deciding which tools to call through the LangGraph agentic loop, and routing decisions (new record, or merge candidate to ReviewQueue). Optimized for low-latency, single-record processing.
- **Clean_Agent**: The AI agent hosted on Amazon Bedrock AgentCore Runtime responsible for the Reactive Layer (Agentic Dedup Layer [Clean]). It uses LangGraph as the orchestration framework with Amazon Bedrock Claude as the reasoning LLM. It processes existing customer records in batch from S3, dynamically deciding which tools to call through the LangGraph agentic loop, writing merge candidates to the ReviewQueue, and producing summary reports. Optimized for batch throughput and bulk comparison.
- **LangGraph**: The agentic AI orchestration framework used by both agents. LangGraph manages a StateGraph where the LLM (Bedrock Claude) decides which tools to call, in what order, and when to stop. This enables adaptive decision-making, state management across tool calls, and extensibility (new tools can be added without changing pipeline code).
- **AgentCore_Gateway**: The Amazon Bedrock AgentCore Gateway service that exposes Lambda functions as MCP-compatible tools for both the Intercept_Agent and Clean_Agent to invoke dynamically.
- **AgentCore_Identity**: The Amazon Bedrock AgentCore Identity service that manages workload identity and credentials for secure tool invocation.
- **Sales_System**: Any upstream system that creates customer records and feeds them into the deduplication pipeline. Examples include OneCRM and NES. Multiple Sales_Systems may exist without integration between them. For the prototype, Sales_Systems are simulated via Postman/curl hitting API Gateway endpoints.
- **API_Gateway**: Amazon API Gateway REST endpoint that receives customer record submissions and review actions, and forwards them to the Intercept_Agent via Step Functions or direct AgentCore invocation.
- **Confidence_Score**: A numerical value between 0.0 and 1.0 representing the likelihood that two customer records refer to the same real-world entity, produced by the two-stage matching pipeline.
- **Oracle_EBS**: Oracle E-Business Suite, the enterprise system of record (single source of truth) for customer master data in production. For the prototype, Oracle EBS TCA (HZ_PARTIES) is simulated by the DynamoDB CustomerTable. In production, Lambda tools are swapped to call Oracle EBS REST APIs; the agents, API contracts, and matching logic remain unchanged.
- **CustomerTable**: DynamoDB table that simulates Oracle EBS TCA customer records for the prototype. Contains customer attributes: customerId (partition key), firstName, lastName, email, phone, dateOfBirth, address, sourceSystem, status (active/merged), mergedInto (optional), createdAt, updatedAt. For ORGANIZATION records, additional fields: partyType, partyName, taxRegistrationNum, taxpayerId, mdrPidId, matchMarket, province.
- **ReviewQueue**: DynamoDB table that stores pending merge candidates for human review. Contains: reviewId, incomingRecord, matchedRecord, confidenceScore, confidenceClassification, matchingMethod, contributingFields, status (pending/approved/rejected), reviewedBy, reviewedAt.
- **Data_Steward**: An authorized human user responsible for reviewing deduplication candidates and approving or rejecting merge proposals via API Gateway endpoints (Postman/curl).
- **Match_Candidate**: An existing customer record identified as a potential match to an incoming record, along with the associated Confidence_Score.
- **Blocking_Strategy**: A technique to reduce comparison space by grouping records (e.g., by postal code, phonetic name encoding) so only records within the same block are compared.

## Requirements

### Requirement 0: Party Type Support (Person & Organization)

**User Story:** As a solutions architect, I want the deduplication system to support both Person and Organization party types with distinct matching rules, so that the prototype demonstrates deduplication for individual customers and corporate accounts as they exist in Oracle EBS TCA (HZ_PARTIES).

#### Acceptance Criteria

1. THE system SHALL support two party types: PERSON and ORGANIZATION, identified by a `partyType` field on each customer record.
2. WHEN a record has `partyType=PERSON` (or no partyType specified), THE system SHALL apply normalized scoring (0.0–1.0) using email, phone, name (Jaro-Winkler, Soundex), and date-of-birth matching with a match threshold of 0.6.
3. WHEN a record has `partyType=ORGANIZATION`, THE system SHALL apply cumulative scoring based on the Oracle TCA "Pearson Organization Duplicates" match rule with a match threshold of 144 cumulative points.
4. THE ORGANIZATION scoring SHALL use the following attribute weights: partyName Jaro-Winkler (89), partyName Soundex (89), address Jaro-Winkler (31), city Jaro-Winkler (23), postalCode exact (55), state exact (15), province Jaro-Winkler (17), taxRegistrationNum exact (146), taxpayerId exact (147), mdrPidId exact (145), matchMarket exact (148).
5. THE ORGANIZATION confidence thresholds SHALL be: cumulative >= 200 for high_confidence, cumulative >= 144 for potential_duplicate, cumulative < 144 for new_record.
6. THE CustomerTable data model SHALL support ORGANIZATION-specific fields: partyName, partyType, taxRegistrationNum, taxpayerId, mdrPidId, matchMarket, province.
7. THE QueryCustomerTool SHALL use DynamoDB scan with filter expressions for ORGANIZATION lookups (by taxRegistrationNum, taxpayerId, matchMarket), with dedicated GSIs planned for production.
8. THE scoring configuration SHALL be externalized in `tools/scoring_config.json` so that weights and thresholds can be adjusted without code changes.
9. THE Dashboard SHALL provide separate registration forms for Person and Organization, and party type filters on the Accounts and Duplicate Reviews tabs.
10. THE batch deduplication pipeline SHALL support mixed batches containing both Person and Organization records.

### Requirement 1: API Gateway and Sales System Simulation

**User Story:** As a solutions architect, I want the Intercept Agent to receive customer records via API Gateway endpoints and Data Stewards to manage reviews via API Gateway, so that the prototype can be tested end-to-end using Postman/curl without requiring a web UI.

#### Acceptance Criteria

1. THE API_Gateway SHALL expose a REST POST /register endpoint that accepts customer record payloads in JSON format.
2. WHEN a customer record is received via POST /register, THE API_Gateway SHALL forward the payload to the Intercept_Agent via AWS Step Functions Express Workflow or direct InvokeAgent API call to AgentCore Runtime.
3. THE API_Gateway SHALL require authentication via AWS IAM or API key for all incoming requests.
4. IF the API_Gateway receives a malformed request, THEN THE API_Gateway SHALL return a structured error response with HTTP 400 status and a descriptive error message.
5. THE API_Gateway SHALL accept customer record payloads containing name, date of birth, address, email, and phone number fields, along with a source Sales_System identifier for PERSON records, and partyName, taxRegistrationNum, taxpayerId, mdrPidId, matchMarket, and address fields for ORGANIZATION records.
6. THE API_Gateway SHALL expose a REST GET /reviews endpoint that returns a list of pending merge candidates from the ReviewQueue table.
7. THE API_Gateway SHALL expose a REST POST /reviews/{reviewId}/approve endpoint that triggers the Intercept_Agent to execute the approved merge operation.
8. THE API_Gateway SHALL expose a REST POST /reviews/{reviewId}/reject endpoint that triggers the Intercept_Agent to mark the candidate pair as a confirmed non-match.

### Requirement 2: AgentCore Intercept Agent (Proactive Layer)

**User Story:** As a solutions architect, I want a dedicated Intercept Agent on AgentCore that handles real-time deduplication of incoming records from Sales Systems, so that duplicates are identified before they enter TEP Oracle EBS.

#### Acceptance Criteria

1. THE Intercept_Agent SHALL be hosted on Amazon Bedrock AgentCore Runtime and exposed via AgentCore Gateway as the real-time deduplication orchestrator for the Proactive Layer.
2. WHEN the Intercept_Agent receives a customer record payload via API Gateway, THE Intercept_Agent SHALL invoke tools dynamically via AgentCore Gateway to execute the two-stage matching pipeline.
3. THE Intercept_Agent SHALL use AgentCore Identity for workload identity and credential management when invoking tools.
4. THE Intercept_Agent SHALL determine whether a customer record is a high-confidence duplicate, a potential duplicate, or a new record based on the final Confidence_Score.
5. WHEN the Confidence_Score is 0.9 or above, THE Intercept_Agent SHALL classify the record as a high-confidence duplicate and write the match candidate pair to the ReviewQueue table with a merge recommendation.
6. WHEN the Confidence_Score is between 0.6 and 0.9 (exclusive of 0.9), THE Intercept_Agent SHALL classify the record as a potential duplicate and write the match candidate pair to the ReviewQueue table for human review.
7. WHEN the Confidence_Score is below 0.6, THE Intercept_Agent SHALL classify the record as a new customer and invoke the CreateCustomerTool to insert the record into the CustomerTable.
8. THE Intercept_Agent SHALL have a system prompt optimized for low-latency, single-record real-time deduplication decisions.
9. THE Intercept_Agent SHALL use LangGraph as the agentic orchestration framework, with Amazon Bedrock Claude as the reasoning LLM that dynamically decides which tools to invoke and in what order based on the data encountered during each pipeline execution.

### Requirement 2a: AgentCore Clean Agent (Reactive Layer)

**User Story:** As a solutions architect, I want a dedicated Clean Agent on AgentCore that handles batch deduplication of existing records in TEP Oracle EBS, so that historical duplicates are identified and recommended for merge.

#### Acceptance Criteria

1. THE Clean_Agent SHALL be hosted on Amazon Bedrock AgentCore Runtime as a separate agent instance from the Intercept_Agent, exposed via AgentCore Gateway as the batch deduplication orchestrator for the Reactive Layer.
2. WHEN the Clean_Agent receives a batch of customer records from S3, THE Clean_Agent SHALL invoke tools dynamically via AgentCore Gateway to execute the two-stage matching pipeline for each record.
3. THE Clean_Agent SHALL use AgentCore Identity for workload identity and credential management when invoking tools.
4. THE Clean_Agent SHALL apply the same Confidence_Score thresholds and decision routing logic as the Intercept_Agent (>= 0.9 high-confidence, 0.6–0.9 potential duplicate, < 0.6 new record).
5. THE Clean_Agent SHALL have a system prompt optimized for batch throughput and bulk comparison of existing records.
6. BOTH the Intercept_Agent and Clean_Agent SHALL share the same Lambda tools (QueryCustomerTool, CreateCustomerTool, MergeCustomerTool) and two-stage matching pipeline.
7. THE Clean_Agent SHALL use LangGraph as the agentic orchestration framework, with Amazon Bedrock Claude as the reasoning LLM, matching the same architecture as the Intercept_Agent but with a batch-oriented system prompt and partial-failure tolerance.

### Requirement 3: Real-Time Duplicate Detection

**User Story:** As a product manager, I want duplicate detection to occur in real time when customer records arrive via the API Gateway, so that duplicates are identified before they enter the customer data store.

#### Acceptance Criteria

1. WHEN a new customer record is received via POST /register, THE Intercept_Agent SHALL search for potential matches against existing CustomerTable records and return results within 5 seconds.
2. WHEN the Intercept_Agent identifies one or more Match_Candidates with a Confidence_Score of 0.6 or above, THE Intercept_Agent SHALL write the match candidate pair to the ReviewQueue table for human decision.
3. WHEN the Intercept_Agent determines no Match_Candidates exist with a Confidence_Score of 0.6 or above, THE Intercept_Agent SHALL create a new record in the CustomerTable.

### Requirement 4: Two-Stage Matching Pipeline

**User Story:** As a data engineer, I want a two-stage matching pipeline that applies rule-based and LLM-based techniques, so that duplicates are identified with high accuracy across varying data quality.

#### Acceptance Criteria

1. BOTH the Intercept_Agent and Clean_Agent SHALL apply a Blocking_Strategy (postal code, phonetic name encoding) to reduce the comparison space before executing matching algorithms.
2. WHEN either agent executes matching for a PERSON record, THE agent SHALL first apply rule-based checks via a Lambda tool that performs exact match on email and phone, and fuzzy match using Soundex and Jaro-Winkler distance on name fields. WHEN matching an ORGANIZATION record, THE agent SHALL apply cumulative scoring using Jaro-Winkler on partyName and address fields, Soundex on partyName, and exact match on taxRegistrationNum, taxpayerId, mdrPidId, matchMarket, postalCode, and state — following the Oracle TCA "Pearson Organization Duplicates" match rule.
3. WHEN rule-based matching for a PERSON record does not produce a definitive result (Confidence_Score between 0.4 and 0.9), THE agent SHALL invoke an Amazon Bedrock foundation model via a Lambda tool for LLM-based fuzzy and semantic matching on ambiguous edge cases (e.g., "Chris" vs. "Chrish James"). For ORGANIZATION records, LLM matching MAY be invoked when the cumulative score falls between 100 and 200 for additional context analysis.
4. BOTH agents SHALL produce a final Confidence_Score between 0.0 and 1.0 by combining results from both matching stages.

### Requirement 5: Decision and Action Routing

**User Story:** As a data steward, I want clear routing of deduplication decisions based on confidence scores, so that high-confidence duplicates are recommended for merge, new records are created, and all merge decisions go through human review.

#### Acceptance Criteria

1. WHEN the final Confidence_Score is 0.9 or above, THE agent (Intercept_Agent or Clean_Agent) SHALL write the match candidate pair to the ReviewQueue table with a high-confidence merge recommendation, the Confidence_Score, matching method, and contributing field details.
2. WHEN the final Confidence_Score is below 0.6, THE agent SHALL invoke the CreateCustomerTool to insert the record as a new customer in the CustomerTable.
3. WHEN the final Confidence_Score is between 0.6 and 0.9 (exclusive of 0.9), THE agent SHALL write the match candidate pair to the ReviewQueue table with the Confidence_Score, matching method, and contributing field details for human decision.

### Requirement 6: Human-in-the-Loop Review via API Gateway

**User Story:** As a data steward, I want all merge decisions stored in a ReviewQueue and accessible via API Gateway endpoints, so that no customer records are merged without human approval.

#### Acceptance Criteria

1. WHEN a match candidate pair is routed for human review, THE agent (Intercept_Agent or Clean_Agent) SHALL write a review record to the ReviewQueue table containing the incoming record, matched record, Confidence_Score, confidence classification (high-confidence or potential duplicate), matching method used, contributing fields, and source agent identifier (Intercept or Clean).
2. THE API_Gateway SHALL expose a GET /reviews endpoint that returns all ReviewQueue records with status "pending", including the side-by-side record comparison, Confidence_Score, and matching details.
3. WHEN a Data_Steward submits an approval via POST /reviews/{reviewId}/approve, THE API_Gateway SHALL invoke the Intercept_Agent, which SHALL execute the MergeCustomerTool and record the decision in the audit log.
4. WHEN a Data_Steward submits a rejection via POST /reviews/{reviewId}/reject, THE Intercept_Agent SHALL mark the pair as confirmed non-match in the ReviewQueue table and record the decision in the audit log.
5. BOTH agents SHALL route all merge decisions (both high-confidence and potential duplicates) to the ReviewQueue table for human approval before any merge operation is executed.

### Requirement 7: Data Preservation and No-Deletion Policy

**User Story:** As a compliance officer, I want a strict no-deletion policy for customer records, so that all original data is preserved and deduplication actions only consolidate records without removing source data.

#### Acceptance Criteria

1. NEITHER the Intercept_Agent NOR the Clean_Agent SHALL delete any customer records from the CustomerTable (DynamoDB in prototype, Oracle EBS in production) or any other data store during deduplication operations.
2. BOTH agents SHALL perform all deduplication actions as merge operations that consolidate data from duplicate records into a single master record while preserving all original data from both source records.
3. WHEN a merge operation is executed, THE agent SHALL retain the original source records in the CustomerTable in a merged or inactive state (status set to "merged" with mergedInto referencing the master record), preserving full traceability to the original data.
4. BOTH agents SHALL log every merge operation with the source record identifiers, the target master record identifier, and the fields consolidated.

### Requirement 8: Customer Data Store Integration (DynamoDB Prototype / Oracle EBS Production)

**User Story:** As a data engineer, I want both agents to query, create, and merge customer records via shared Lambda tools against a data store, so that the architecture supports swapping DynamoDB for Oracle EBS by changing only Lambda tool implementations.

#### Acceptance Criteria

1. BOTH the Intercept_Agent and Clean_Agent SHALL invoke a QueryCustomerTool Lambda function via AgentCore Gateway to query existing customer records from the CustomerTable using record fields as search criteria.
2. BOTH agents SHALL invoke a CreateCustomerTool Lambda function via AgentCore Gateway to create new customer records in the CustomerTable when a record is classified as a new customer.
3. BOTH agents SHALL invoke a MergeCustomerTool Lambda function via AgentCore Gateway to merge duplicate customer records in the CustomerTable when a merge is approved by a Data_Steward via the API Gateway review endpoints.
4. IF a Lambda tool invocation fails, THEN THE agent SHALL retry the operation up to 3 times with exponential backoff and log the failure.
5. NEITHER agent SHALL invoke any delete operations against customer records in the CustomerTable.
6. THE architecture SHALL be designed so that swapping DynamoDB CustomerTable for Oracle EBS REST APIs requires only Lambda tool code changes, with no changes to either agent, API contracts, or matching logic.

### Requirement 9: Batch Deduplication Pipeline

**User Story:** As a data steward, I want the Clean Agent to process a static dataset from S3 in batch, so that historical duplicates in TEP Oracle EBS are identified and recommended for merge.

#### Acceptance Criteria

1. THE Clean_Agent SHALL read a static CSV or JSON file containing customer records from an S3 bucket designated for batch test data.
2. WHEN a batch deduplication job is triggered manually or via an S3 upload event, THE Clean_Agent SHALL process each record from the static dataset through the two-stage matching pipeline using a Lambda function or AWS Step Functions for orchestration.
3. WHEN a batch scan identifies merge candidates, THE Clean_Agent SHALL write the match candidate pairs to the ReviewQueue table for human review via the API Gateway review endpoints.
4. WHEN a batch scan completes, THE Clean_Agent SHALL produce a summary report containing total records scanned, duplicates identified, records routed to the ReviewQueue table for human decision, and processing duration, and write the report to S3.

### Requirement 10: Audit and Logging

**User Story:** As a compliance officer, I want an audit trail of all deduplication decisions, so that the organization can trace any data change back to its origin.

#### Acceptance Criteria

1. BOTH the Intercept_Agent and Clean_Agent SHALL log every deduplication decision (match recommendation, non-match, merge approval, merge rejection, human review routing) with a timestamp, decision rationale, Confidence_Score, source Sales_System identifier, source agent identifier (Intercept or Clean), and affected record identifiers.
2. BOTH agents SHALL store audit logs in Amazon S3 with a configurable retention period.
3. WHEN a Data_Steward overrides a deduplication recommendation via the API Gateway review endpoints, THE Intercept_Agent SHALL log the override with the Data_Steward identifier, original recommendation, new decision, and justification.

### Requirement 11: Security

**User Story:** As a security architect, I want customer data encrypted and access controlled by least privilege, so that the deduplication system meets enterprise security standards.

#### Acceptance Criteria

1. BOTH the Intercept_Agent and Clean_Agent SHALL encrypt all customer data at rest using AWS KMS with customer-managed keys across all data stores (S3, DynamoDB CustomerTable, DynamoDB ReviewQueue).
2. BOTH agents SHALL encrypt all data in transit using TLS 1.2 or higher.
3. BOTH agents SHALL enforce least-privilege IAM policies, granting each Lambda tool and AgentCore component access only to the AWS resources required for its specific function.
4. BOTH agents SHALL mask personally identifiable information (PII) in all CloudWatch log outputs, storing full PII only in encrypted data stores.

### Requirement 12: Observability

**User Story:** As an operations engineer, I want basic logging for the deduplication system, so that operations can be debugged and monitored during the prototype.

#### Acceptance Criteria

1. BOTH the Intercept_Agent and Clean_Agent SHALL log all operations to Amazon CloudWatch Logs for debugging and basic monitoring, with log groups separated by agent for independent troubleshooting.
