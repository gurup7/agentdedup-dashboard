# Requirements Document

## Introduction

This document defines the requirements for adding **site-level (address) deduplication** to the existing AgentDedup customer data deduplication prototype. The client's Oracle EBS system contains duplicate site/address records within the same account — for example, one account (ELTHAM HILL SCHOOL, Account #3518670) has 24 duplicate site records with minor address variations (casing, abbreviations, inclusion/exclusion of the school name in the address line). Another account (MERCHANFACTORY, Account #57306583) has 3 site records with identical addresses but different Site Numbers and purposes.

This feature extends the existing Person and Organization deduplication pipeline to detect and recommend merges for duplicate **site records within the same account**. The same two-agent architecture (Intercept + Clean), LangGraph orchestration, Lambda tools, and human-in-the-loop review workflow are reused. The key difference is that site-level dedup operates **within a single account** (intra-account) rather than across accounts, and scoring emphasizes **address similarity** over name/email matching.

**Important**: Site is NOT a party type. Sites are **child records** of Person or Organization accounts in Oracle EBS TCA (HZ_PARTY_SITES / HZ_LOCATIONS linked to HZ_PARTIES). A Person or Organization account can have multiple sites (addresses). Site-level dedup checks for duplicate addresses **within the same account**, not across accounts. The existing Person/Organization dedup (partyType routing) remains unchanged — site dedup is a **separate operation** triggered via a dedicated endpoint (`POST /register-site`).

**Scope**: Site-level deduplication for Oracle EBS TCA site records (HZ_PARTY_SITES / HZ_LOCATIONS). International addresses (UK, Spain, etc.) are in scope. This is an ADDITION to the existing Person/Organization dedup — not a replacement.

## Glossary

- **Site_Record**: A site/address record associated with a customer account in Oracle EBS TCA (HZ_PARTY_SITES / HZ_LOCATIONS). Each site has a unique Site Number, an address, a purpose (Bill To, Ship To), an Operating Unit, and belongs to exactly one account.
- **Account_Number**: The unique identifier for a customer account in Oracle EBS (e.g., 3518670). Multiple site records can belong to the same account.
- **Account_Description**: The human-readable name of the customer account (e.g., "ELTHAM HILL SCHOOL").
- **Site_Number**: The unique identifier for a site record within Oracle EBS (e.g., 4861217, 18468448).
- **Operating_Unit**: The business unit that owns the site record (e.g., "GB Pearson Education OU").
- **Site_Purpose**: The functional role of a site — typically "Bill To", "Ship To", or both.
- **Profile_Class**: A classification attribute on the site record in Oracle EBS (e.g., "DEFAULT", "EDUCATION").
- **Address_Line**: The primary street/location portion of a site address (e.g., "ELTHAM HILL, LONDON, GREENWICH, SE9 5EE").
- **Site_Scoring**: The address-focused scoring algorithm for site-level dedup that uses Jaro-Winkler on address lines as the primary match signal, supplemented by city, postal code, and country exact matches.
- **Intra_Account_Dedup**: Deduplication that operates within a single account — comparing site records that share the same Account_Number, rather than comparing across different accounts.
- **SiteTable**: DynamoDB table that simulates Oracle EBS TCA site records (HZ_PARTY_SITES / HZ_LOCATIONS) for the prototype. In production, Lambda tools swap to Oracle EBS REST APIs.
- **Intercept_Agent**: The existing AI agent on AgentCore Runtime for real-time deduplication (unchanged from existing spec).
- **Clean_Agent**: The existing AI agent on AgentCore Runtime for batch deduplication (unchanged from existing spec).
- **ReviewQueue**: The existing DynamoDB table for pending merge candidates (extended to support site reviews).

## Requirements

### Requirement 1: Site Record Data Model

**User Story:** As a data engineer, I want the prototype to store site/address records with Oracle EBS TCA-equivalent fields, so that the system can represent and compare duplicate sites within the same account.

#### Acceptance Criteria

1. THE SiteTable SHALL store site records with the following fields: siteId (partition key, UUID), accountNumber (string, required), accountDescription (string, required), siteNumber (string, required), operatingUnit (string, required), purpose (string — "Bill To", "Ship To", or "Bill To/Ship To"), profileClass (string, optional), status (string — "active" or "merged"), country (string, required), addressLine1 (string, required), addressLine2 (string, optional), city (string, required), postalCode (string, required), county (string, optional), sourceSystem (string, required), createdAt (ISO 8601 timestamp), updatedAt (ISO 8601 timestamp), mergedInto (string, optional — siteId of master site if merged).
2. THE SiteTable SHALL have a Global Secondary Index (AccountNumberIndex) with accountNumber as the partition key and siteNumber as the sort key, enabling efficient retrieval of all sites within a single account.
3. THE SiteTable SHALL have a Global Secondary Index (PostalCodeIndex) with postalCode as the partition key, enabling blocking-strategy lookups for batch dedup.
4. THE SiteTable SHALL support international addresses including United Kingdom (postcode format: "SE9 5EE") and Spain (postal code format: "28021") without requiring US-specific fields like state.
5. IF a site record is missing the required fields (accountNumber, siteNumber, addressLine1, city, postalCode, country), THEN THE system SHALL reject the record with a descriptive validation error.

### Requirement 2: Site-Level Scoring Algorithm

**User Story:** As a data engineer, I want an address-focused scoring algorithm for site records, so that duplicate sites with minor address variations (casing, abbreviations, name inclusion) are detected with high accuracy.

#### Acceptance Criteria

1. THE Site_Scoring algorithm SHALL use a cumulative scoring model (Oracle TCA style) with the following attribute weights: addressLine1 Jaro-Winkler (90 points if JW >= 0.80), addressLine2 Jaro-Winkler (25 points if JW >= 0.80), city Jaro-Winkler (30 points if JW >= 0.85), postalCode exact match (55 points), country exact match (40 points), county Jaro-Winkler (15 points if JW >= 0.85), operatingUnit exact match (20 points).
2. THE Site_Scoring algorithm SHALL normalize address lines before comparison by: converting to uppercase, removing punctuation, collapsing multiple spaces, and expanding common abbreviations ("ST" → "STREET", "RD" → "ROAD", "AVE" → "AVENUE", "BLVD" → "BOULEVARD", "LN" → "LANE", "DR" → "DRIVE", "CT" → "COURT", "PL" → "PLACE").
3. THE Site_Scoring algorithm SHALL apply a match threshold of 120 cumulative points for potential duplicate and 200 cumulative points for high confidence duplicate.
4. THE Site_Scoring algorithm SHALL only compare site records that share the same accountNumber (intra-account dedup), not across different accounts.
5. THE Site_Scoring configuration SHALL be added to the existing `tools/scoring_config.json` file under a "SITE" key, so that weights and thresholds can be adjusted without code changes.
6. WHEN two site records have identical normalized addressLine1 and identical postalCode, THE Site_Scoring algorithm SHALL assign a minimum cumulative score of 145 (addressLine1 JW 1.0 = 90 + postalCode exact = 55), ensuring they are flagged as potential duplicates.

### Requirement 3: Site Query and Blocking Strategy

**User Story:** As a data engineer, I want the QueryCustomerTool to support site-level lookups that retrieve all sites within the same account, so that intra-account duplicate detection is efficient.

#### Acceptance Criteria

1. WHEN the QueryCustomerTool receives a request with partyType "SITE", THE QueryCustomerTool SHALL query the SiteTable AccountNumberIndex to retrieve all active site records sharing the same accountNumber as the incoming site record.
2. THE QueryCustomerTool SHALL exclude the incoming site record itself (by siteId) from the candidate list when performing site-level lookups.
3. THE QueryCustomerTool SHALL return a maximum of 50 candidate site records per account (increased from the 10-record limit for Person/Organization, since accounts like ELTHAM HILL SCHOOL have 24+ sites).
4. IF no accountNumber is provided in the site lookup request, THEN THE QueryCustomerTool SHALL return an error indicating that accountNumber is required for site-level dedup.
5. THE QueryCustomerTool SHALL support an alternative blocking strategy using PostalCodeIndex for batch site dedup scenarios where cross-account site comparison is needed.

### Requirement 4: Site-Level RuleBasedMatchTool Extension

**User Story:** As a data engineer, I want the RuleBasedMatchTool to support site-level scoring using address-focused rules, so that duplicate sites are scored deterministically before optional LLM escalation.

#### Acceptance Criteria

1. WHEN the RuleBasedMatchTool receives an incomingRecord with partyType "SITE", THE RuleBasedMatchTool SHALL apply the Site_Scoring algorithm (cumulative, address-focused) instead of the Person or Organization scoring algorithms.
2. THE RuleBasedMatchTool SHALL normalize address fields (addressLine1, addressLine2, city) before applying Jaro-Winkler comparison for site records.
3. THE RuleBasedMatchTool SHALL return results containing: candidateId (siteId), ruleBasedScore (normalized 0.0–1.0), cumulativeScore (raw cumulative points), maxPossibleScore, contributingFields, isDefinitive, partyType ("SITE"), and scoreType ("cumulative").
4. THE RuleBasedMatchTool SHALL mark a site comparison as isDefinitive when the cumulative score is >= 200 (high confidence) or < 80 (clearly not a match).
5. WHEN the cumulative score is between 80 and 200 for a site comparison, THE RuleBasedMatchTool SHALL mark the result as not definitive, enabling LLM escalation for ambiguous address matches.

### Requirement 5: Site Registration and Dedup via API Gateway

**User Story:** As a solutions architect, I want a dedicated POST /register-site endpoint to accept site records and trigger intra-account dedup, so that new sites are checked against existing sites in the same account before creation. Site dedup is a separate operation from Person/Organization dedup — it does NOT use partyType routing.

#### Acceptance Criteria

1. THE API_Gateway SHALL expose a dedicated REST POST /register-site endpoint that accepts site record payloads containing: accountNumber (required), accountDescription (required), siteNumber (required), operatingUnit (required), purpose (required), country (required), addressLine1 (required), addressLine2 (optional), city (required), postalCode (required), county (optional), profileClass (optional), sourceSystem (required). This endpoint is SEPARATE from POST /register (which handles Person/Organization).
2. WHEN a site record is submitted via POST /register-site, THE Intercept_Agent SHALL query the SiteTable for all active sites in the same account and apply Site_Scoring to detect duplicates.
3. WHEN the Site_Scoring cumulative score is 200 or above for any candidate, THE Intercept_Agent SHALL write the site match pair to the ReviewQueue with confidenceClassification "high_confidence".
4. WHEN the Site_Scoring cumulative score is between 120 and 200 (exclusive) for any candidate, THE Intercept_Agent SHALL write the site match pair to the ReviewQueue with confidenceClassification "potential_duplicate".
5. WHEN no candidate site scores 120 or above, THE Intercept_Agent SHALL create the new site record in the SiteTable.
6. THE Intercept_Agent SHALL process site registration requests within 5 seconds end-to-end, consistent with the existing real-time SLA.
7. THE existing POST /register endpoint SHALL NOT be modified — it continues to handle Person and Organization records only via partyType routing.

### Requirement 6: Site-Level Seed Data

**User Story:** As a solutions architect, I want seed data that mimics the client's actual Oracle EBS site records, so that the prototype demonstrates realistic site-level dedup scenarios during demos.

#### Acceptance Criteria

1. THE seed data SHALL include an "ELTHAM HILL SCHOOL" account (accountNumber "3518670") with at least 6 site records demonstrating address variations: full school name in address vs. omitted, casing differences (uppercase vs. mixed case), and minor formatting differences — all sharing postalCode "SE9 5EE" and country "United Kingdom".
2. THE seed data SHALL include a "MERCHANFACTORY" account (accountNumber "57306583") with at least 3 site records having identical addresses ("C. DE LA RESINA, 35, NAVE 7, VILLAVERDE, 28021 MADRID, SPAIN") but different Site Numbers and purposes (Bill To, Ship To, Bill To/Ship To).
3. THE seed data SHALL include at least one account with sites that are NOT duplicates (different addresses within the same account) to demonstrate that the system correctly identifies non-matches.
4. THE seed data SHALL include at least one account with a single site (no duplicates possible) to demonstrate the "new record" path.
5. THE seed data SHALL use realistic Operating Unit values ("GB Pearson Education OU") and Profile Class values consistent with the client's Oracle EBS configuration.

### Requirement 7: Dashboard Site-Level Display

**User Story:** As a data steward, I want the dashboard to display site records with Account Number, Site Number, Country, and Operating Unit columns, so that I can identify and review duplicate sites within accounts.

#### Acceptance Criteria

1. THE Dashboard SHALL display a "Sites" tab (or section within the Accounts tab) showing site records with columns: Account Number, Account Description, Site Number, Address Line 1, City, Postal Code, Country, Operating Unit, Purpose, Status.
2. THE Dashboard SHALL provide a filter by Account Number so that a data steward can view all sites within a specific account.
3. THE Dashboard SHALL display site-level duplicate reviews in the existing Duplicate Reviews tab with partyType "SITE" badge, showing side-by-side address comparison with highlighted differences.
4. WHEN displaying a site-level review, THE Dashboard SHALL show Account Number, Site Number, Operating Unit, and Purpose for both the incoming and matched site records.
5. THE Dashboard SHALL provide a "Register Site" form in the Register Customer tab that accepts site-specific fields (accountNumber, siteNumber, addressLine1, city, postalCode, country, operatingUnit, purpose).

### Requirement 8: Batch Site-Level Deduplication

**User Story:** As a data steward, I want the Clean Agent to process site records in batch and identify duplicate sites within each account, so that historical site duplicates in Oracle EBS are surfaced for review.

#### Acceptance Criteria

1. WHEN a batch file containing site records (partyType "SITE") is uploaded to S3, THE Clean_Agent SHALL group records by accountNumber and apply Site_Scoring within each account group.
2. THE Clean_Agent SHALL process site batch files containing mixed record types (Person, Organization, Site) by routing each record to the appropriate scoring algorithm based on partyType.
3. WHEN batch site dedup identifies duplicate sites within an account, THE Clean_Agent SHALL write the match pairs to the ReviewQueue with sourceAgent "clean" and partyType "SITE".
4. THE batch summary report SHALL include site-specific metrics: total sites scanned, accounts with duplicate sites, total duplicate site pairs identified, and sites routed to ReviewQueue.

### Requirement 9: Site Merge Operations

**User Story:** As a data steward, I want to approve merges of duplicate site records while preserving the original data, so that accounts are cleaned up without losing traceability.

#### Acceptance Criteria

1. WHEN a Data_Steward approves a site-level merge via POST /reviews/{reviewId}/approve, THE MergeCustomerTool SHALL consolidate the duplicate site records by: retaining the master site record as active, setting the source site record status to "merged" with mergedInto referencing the master siteId, and preserving all original field values.
2. THE MergeCustomerTool SHALL select the site record with the lowest (oldest) Site Number as the master record when merging duplicate sites, consistent with Oracle EBS convention of preserving the original site.
3. WHEN merging sites with different purposes (e.g., one is "Bill To" and another is "Ship To"), THE MergeCustomerTool SHALL consolidate purposes on the master record to "Bill To/Ship To".
4. THE MergeCustomerTool SHALL NOT delete any site records from the SiteTable during merge operations, consistent with the existing no-deletion policy.
5. THE audit log SHALL record site merge operations with: source siteId, master siteId, accountNumber, fields consolidated, and Data_Steward identifier.

### Requirement 10: Address Normalization for International Addresses

**User Story:** As a data engineer, I want address normalization that handles UK and Spanish address formats, so that site-level dedup works correctly for the client's international accounts.

#### Acceptance Criteria

1. THE address normalization SHALL handle UK postcode formats (e.g., "SE9 5EE", "SW1A 1AA") by normalizing spacing and casing before comparison.
2. THE address normalization SHALL handle Spanish address formats including: "C." prefix for "Calle", "NAVE" for warehouse units, and comma-separated address components.
3. THE address normalization SHALL treat the following as equivalent during comparison: "ELTHAM HILL" and "ELTHAM HILL SCHOOL, ELTHAM HILL" (the school name prepended to the street address) by using Jaro-Winkler similarity rather than exact match on addressLine1.
4. THE address normalization SHALL be case-insensitive, treating "LONDON" and "London" and "london" as equivalent.
5. THE address normalization SHALL strip leading/trailing whitespace and collapse multiple internal spaces to a single space before comparison.
6. THE address normalization SHALL NOT alter the stored address data — normalization is applied only during comparison, preserving the original address as entered.
