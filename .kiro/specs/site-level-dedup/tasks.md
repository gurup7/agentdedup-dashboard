# Implementation Plan: Site-Level Deduplication

## Overview

This plan extends the existing AgentDedup prototype to support site-level (address) deduplication within accounts. The implementation adds a new SiteTable, address normalization module, site scoring algorithm, and extends existing tools (QueryCustomerTool, RuleBasedMatchTool, MergeCustomerTool) with `partyType=SITE` branches. Dashboard and API Gateway are updated to support site registration and review.

## Tasks

- [x] 1. Infrastructure — SiteTable DynamoDB and scoring configuration
  - [x] 1.1 Add SiteTable DynamoDB resource to `infra/template.yaml`
    - Add `SiteTableName` parameter (default: `SiteTable`)
    - Define SiteTable with `siteId` as partition key (String)
    - Add GSI-1 `AccountNumberIndex` (accountNumber PK, siteNumber SK)
    - Add GSI-2 `PostalCodeIndex` (postalCode PK)
    - Configure on-demand capacity and KMS encryption (same CMK as CustomerTable)
    - Add `SITE_TABLE_NAME` environment variable to Lambda Globals
    - Add DynamoDBCrudPolicy for SiteTable to InterceptAgentProxy and CleanAgentProxy
    - _Requirements: 1.1, 1.2, 1.3_

  - [x] 1.2 Add SITE scoring section to `tools/scoring_config.json`
    - Add "SITE" key with cumulative scoring model
    - Configure weights: addressLine1_jw (90), addressLine2_jw (25), city_jw (30), postalCode_exact (55), country_exact (40), county_jw (15), operatingUnit_exact (20)
    - Configure JW thresholds: addressLine1 (0.80), addressLine2 (0.80), city (0.85), county (0.85)
    - Configure decision thresholds: high_confidence (200), potential_duplicate (120), new_record (120)
    - Configure isDefinitive: high (200), low (80)
    - Set maxCandidates to 50
    - _Requirements: 2.1, 2.3, 2.5_

- [x] 2. Address normalization module
  - [x] 2.1 Create `tools/rule_based_match/address_normalization.py`
    - Implement `normalize_address(text: str) -> str` pure function
    - Convert to uppercase
    - Strip leading/trailing whitespace
    - Remove punctuation (periods, commas become space separators)
    - Expand abbreviations: ST→STREET, RD→ROAD, AVE→AVENUE, BLVD→BOULEVARD, LN→LANE, DR→DRIVE, CT→COURT, PL→PLACE
    - Collapse multiple spaces to single space
    - Handle UK postcodes: normalize spacing (e.g., "SE95EE" → "SE9 5EE")
    - Preserve Spanish address patterns: "C." prefix, "NAVE" preserved
    - Ensure idempotency: normalize(normalize(s)) == normalize(s)
    - _Requirements: 2.2, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

  - [ ]* 2.2 Write property test for address normalization (Property 1)
    - **Property 1: Address Normalization Invariants**
    - Test idempotency, case-insensitivity, no leading/trailing whitespace, no consecutive spaces
    - Use Hypothesis with random strings including mixed case, whitespace, abbreviations, UK/Spanish formats
    - File: `tests/test_site_normalization.py`
    - **Validates: Requirements 2.2, 10.4, 10.5**

- [x] 3. Checkpoint — Ensure normalization tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Site scoring in RuleBasedMatchTool
  - [x] 4.1 Add `_score_site_pair()` function to `tools/rule_based_match/handler.py`
    - Import `normalize_address` from address_normalization module
    - Normalize addressLine1, addressLine2, city, county before Jaro-Winkler comparison
    - Apply Jaro-Winkler on normalized addressLine1 (90 pts if JW >= 0.80)
    - Apply Jaro-Winkler on normalized addressLine2 (25 pts if JW >= 0.80)
    - Apply Jaro-Winkler on normalized city (30 pts if JW >= 0.85)
    - Apply exact match on postalCode (55 pts)
    - Apply exact match on country (40 pts)
    - Apply Jaro-Winkler on normalized county (15 pts if JW >= 0.85)
    - Apply exact match on operatingUnit (20 pts)
    - Sum cumulative points, compute normalized score (cumulative / 275)
    - Return: candidateId (siteId), ruleBasedScore, cumulativeScore, maxPossibleScore (275), contributingFields, isDefinitive, partyType "SITE", scoreType "cumulative"
    - Mark isDefinitive when cumulative >= 200 or < 80
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 4.2 Update `handler()` in `tools/rule_based_match/handler.py` to route partyType "SITE"
    - Add `elif party_type == "SITE"` branch in handler function
    - Call `_score_site_pair(incoming, c)` for each candidate
    - _Requirements: 4.1_

  - [ ]* 4.3 Write property tests for site scoring (Properties 2, 3, 5)
    - **Property 2: Site Scoring Correctness** — cumulative score equals sum of passing attribute weights; classification consistent with score
    - **Property 3: Minimum Score Guarantee** — identical normalized addressLine1 + identical postalCode → score >= 145
    - **Property 5: Account Isolation** — different accountNumbers never produce a match score during intra-account dedup
    - File: `tests/test_site_scoring.py`
    - **Validates: Requirements 2.1, 2.3, 2.4, 2.6, 4.1, 4.4, 4.5**

- [x] 5. QueryCustomerTool site query extension
  - [x] 5.1 Add `_query_site_by_account()` function to `tools/query_customer/handler.py`
    - Add `SITE_TABLE_NAME` environment variable lookup
    - Query AccountNumberIndex with incoming record's accountNumber
    - Filter to status="active" only
    - Exclude the incoming record itself by siteId
    - Cap results at 50 candidates
    - Return error if accountNumber is missing
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [x] 5.2 Update `handler()` in `tools/query_customer/handler.py` to route partyType "SITE"
    - Add `elif party_type == "SITE"` branch in handler function
    - Call `_query_site_by_account()` for site lookups
    - Return candidates with blockingStrategiesUsed: ["account_number_index"]
    - _Requirements: 3.1, 3.4_

  - [ ]* 5.3 Write property test for site query (Property 4)
    - **Property 4: Intra-Account Query Correctness**
    - Verify all active sites with same accountNumber returned, excluding queried record, capped at 50
    - File: `tests/test_site_query.py`
    - **Validates: Requirements 3.1, 3.2, 3.3**

- [x] 6. Site creation and merge tools
  - [x] 6.1 Create `tools/create_customer/handler.py` site creation branch (or new CreateSiteTool)
    - Add site record creation logic in existing CreateCustomerTool handler
    - Validate required fields: accountNumber, siteNumber, addressLine1, city, postalCode, country
    - Generate UUID siteId, set status="active", set createdAt/updatedAt timestamps
    - Write to SiteTable
    - Return created site record with siteId
    - _Requirements: 1.1, 1.5, 5.5_

  - [x] 6.2 Extend `tools/merge_customer/handler.py` for site merge operations
    - Add `partyType=SITE` branch in MergeCustomerTool handler
    - Select master record as the site with numerically lowest siteNumber
    - Set source site status to "merged" with mergedInto referencing master siteId
    - Consolidate purposes: if different, set master to "Bill To/Ship To"
    - Never delete records from SiteTable
    - Write audit log with source siteId, master siteId, accountNumber, fields consolidated
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [ ]* 6.3 Write property test for site merge (Property 8)
    - **Property 8: Merge Master Selection and Purpose Consolidation**
    - Verify lowest siteNumber selected as master, purpose consolidation, no deletions
    - File: `tests/test_site_merge.py`
    - **Validates: Requirements 9.1, 9.2, 9.3, 9.4**

  - [ ]* 6.4 Write property test for field validation (Property 6)
    - **Property 6: Required Field Validation**
    - Verify records missing required fields are rejected with validation error
    - File: `tests/test_site_validation.py`
    - **Validates: Requirements 1.5**

- [x] 7. Checkpoint — Ensure all tool tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Orchestrator and agent proxy site routing
  - [x] 8.1 Update `tools/agent_proxy/` to handle partyType "SITE" in register action
    - Route SITE records through the same pipeline: query → score → decide
    - Use site-specific thresholds: >= 200 high_confidence, 120-200 potential_duplicate, < 120 new_record
    - Call CreateSite (SiteTable) instead of CreateCustomer when creating new site records
    - _Requirements: 5.2, 5.3, 5.4, 5.5_

  - [x] 8.2 Update LangGraph orchestrator system prompt for site support
    - Add SITE pipeline description to `agents/intercept/langgraph_orchestrator.py` SYSTEM_PROMPT
    - Add site-specific tool wrappers (query_site_tool, create_site_tool) or extend existing wrappers
    - Document SITE thresholds (120/200 cumulative) in system prompt
    - _Requirements: 5.2, 5.3, 5.4, 5.5, 5.6_

- [x] 9. Site seed data and demo reset
  - [x] 9.1 Create `tests/site-seed-data.json` with realistic site records
    - ELTHAM HILL SCHOOL (Account 3518670): 6 sites with address variations — "ELTHAM HILL" vs "ELTHAM HILL SCHOOL, ELTHAM HILL", casing differences, with/without addressLine2
    - MERCHANFACTORY (Account 57306583): 3 sites with identical address "C. DE LA RESINA, 35, NAVE 7" but different purposes (Bill To, Ship To, Bill To/Ship To)
    - WESTFIELD ACADEMY (Account 9912345): 2 sites with genuinely different addresses (non-duplicate control)
    - SOLO TRADING LTD (Account 8800001): 1 site only (new record path)
    - Use realistic Operating Unit ("GB Pearson Education OU") and Profile Class values
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 9.2 Update `scripts/demo-reset.py` to seed SiteTable
    - Load `tests/site-seed-data.json` and batch-write to SiteTable
    - Clear existing site records before seeding (truncate pattern)
    - Add SiteTable name to environment/config
    - _Requirements: 6.1_

- [ ] 10. API Gateway schema update for SITE payloads
  - [ ] 10.1 Update `CustomerRecordModel` in `infra/template.yaml` to accept SITE fields
    - Add site-specific properties to the JSON schema: accountNumber, accountDescription, siteNumber, operatingUnit, purpose, addressLine1, addressLine2, city, postalCode, county, country, profileClass
    - Ensure validation allows both existing Person/Organization and new SITE payloads
    - _Requirements: 5.1_

- [ ] 11. Dashboard UI changes
  - [ ] 11.1 Add Sites tab to `dashboard/app.py`
    - Add "🏠 Sites" tab to the main tab bar
    - Display site records table with columns: Account Number, Account Description, Site Number, Address Line 1, City, Postal Code, Country, Operating Unit, Purpose, Status
    - Add Account Number filter input
    - Fetch sites from SiteTable via boto3 scan
    - Add SITE_TABLE environment variable to dashboard config
    - _Requirements: 7.1, 7.2_

  - [ ] 11.2 Add "Register Site" form to Register Customer tab in `dashboard/app.py`
    - Add partyType selector including "Site" option
    - Show site-specific form fields: accountNumber, accountDescription, siteNumber, operatingUnit, purpose (dropdown), country, addressLine1, addressLine2, city, postalCode, county, profileClass, sourceSystem
    - Submit via POST /register with partyType "SITE"
    - _Requirements: 7.5_

  - [ ] 11.3 Update Duplicate Reviews tab for site reviews in `dashboard/app.py`
    - Add "Site" option to Party Type filter dropdown
    - Display partyType "SITE" badge (🏠) for site reviews
    - Show side-by-side address comparison with Account Number, Site Number, Operating Unit, Purpose
    - Highlight address differences between incoming and matched site records
    - _Requirements: 7.3, 7.4_

- [ ] 12. Checkpoint — Ensure dashboard renders correctly with site data
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 13. End-to-end integration wiring
  - [ ] 13.1 Wire WriteReviewTool to include partyType "SITE" and cumulativeScore in review records
    - Ensure site reviews written to ReviewQueue include partyType, accountNumber, siteNumber, cumulativeScore
    - Ensure review display has all fields needed for site-level review UI
    - _Requirements: 5.3, 5.4, 7.3, 7.4_

  - [ ] 13.2 Update `tools/agent_proxy/` scoring_config.json copy (if separate from `tools/scoring_config.json`)
    - Ensure agent_proxy has access to the SITE scoring configuration
    - Verify `tools/agent_proxy/tools/scoring_config.json` includes SITE section
    - _Requirements: 2.5_

  - [ ]* 13.3 Write end-to-end integration tests for demo scenarios
    - Test Scenario A: ELTHAM HILL SCHOOL address variation detection (expect high_confidence)
    - Test Scenario B: MERCHANFACTORY identical address, different purpose (expect high_confidence)
    - Test Scenario C: WESTFIELD ACADEMY genuinely different address (expect new_record)
    - Test Scenario D: SOLO TRADING LTD first site in account (expect new_record)
    - File: `tests/test_site_e2e.py`
    - _Requirements: 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.3, 6.4_

- [ ] 14. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- The existing Person and Organization dedup pipelines remain unchanged — site support is additive
- All tools exist in `tools/` directory (shared between agents) and are deployed via `infra/template.yaml`
- Dashboard uses Streamlit (`dashboard/app.py`) and reads DynamoDB directly
