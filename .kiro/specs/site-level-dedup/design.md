# Design Document: Site-Level Deduplication

## Overview

This design extends the existing Customer Data Deduplication prototype to support **site-level (address) deduplication within accounts**. The client's Oracle EBS system contains duplicate site/address records within the same account — e.g., ELTHAM HILL SCHOOL (Account #3518670) has 24 duplicate sites with minor address variations.

**What changes from the existing architecture:**
- New `SiteTable` DynamoDB table (parallel to CustomerTable)
- New "SITE" scoring algorithm in `scoring_config.json` (address-focused, cumulative)
- `QueryCustomerTool` extended with `partyType=SITE` branch (queries SiteTable by accountNumber)
- `RuleBasedMatchTool` extended with `partyType=SITE` branch (address normalization + site scoring)
- Orchestrator threshold routing extended for SITE thresholds (120/200)
- New site seed data in `tests/site-seed-data.json`
- Dashboard: Sites tab, site registration form, site review display
- API Gateway: site record request schema added to POST /register

**What stays the same** (see [existing design doc](../customer-data-deduplication/design.md)):
- Two-agent architecture (Intercept + Clean) on AgentCore Runtime
- LangGraph orchestration pattern
- ReviewQueue, audit logging, merge workflow
- LLMMatchTool (invoked for ambiguous site scores 80–200)
- Step Functions (Express for real-time, Standard for batch)
- Security model (KMS, IAM least-privilege, PII masking)

## Architecture

### Delta Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                     EXISTING (unchanged)                            │
│  API Gateway → Step Functions → Intercept/Clean Agent → Tools      │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                     NEW / MODIFIED                                  │
│                                                                     │
│  POST /register {partyType: "SITE"}                                │
│       │                                                             │
│       ▼                                                             │
│  Orchestrator (partyType routing)                                  │
│       │                                                             │
│       ▼                                                             │
│  QueryCustomerTool ──► SiteTable (AccountNumberIndex)              │
│       │                                                             │
│       ▼                                                             │
│  RuleBasedMatchTool ──► Address Normalization + Site Scoring        │
│       │                                                             │
│       ▼                                                             │
│  Decision Routing (120/200 thresholds)                             │
│       │                                                             │
│       ├── >= 200: WriteReviewTool (high_confidence)                │
│       ├── 120-200: WriteReviewTool (potential_duplicate)           │
│       └── < 120: CreateSiteTool (new site in SiteTable)            │
│                                                                     │
│  DATA LAYER (new):                                                 │
│  ┌─────────────────────────────────────────┐                       │
│  │ DynamoDB SiteTable                      │                       │
│  │  PK: siteId (UUID)                     │                       │
│  │  GSI-1: AccountNumberIndex             │                       │
│  │         (accountNumber PK, siteNumber SK)│                      │
│  │  GSI-2: PostalCodeIndex                │                       │
│  │         (postalCode PK)                │                       │
│  └─────────────────────────────────────────┘                       │
└─────────────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### Component 1: SiteTable (DynamoDB) — NEW

Simulates Oracle EBS TCA `HZ_PARTY_SITES` / `HZ_LOCATIONS`. Separate from CustomerTable because sites have a fundamentally different schema (no name/email/phone, address-centric, account-scoped).

**Table Configuration:** On-demand capacity, KMS encrypted (same CMK as CustomerTable).

### Component 2: QueryCustomerTool Extension — MODIFIED

New `partyType=SITE` branch added alongside existing PERSON/ORGANIZATION branches.

**Site query strategy:**
1. Query `AccountNumberIndex` with incoming record's `accountNumber`
2. Filter out the incoming record itself (by `siteId`)
3. Filter to `status=active` only
4. Cap at 50 results (accounts can have 24+ sites)

**Alternative blocking (batch):** Query `PostalCodeIndex` for cross-account site comparison.

### Component 3: RuleBasedMatchTool Extension — MODIFIED

New `_score_site_pair()` function added alongside existing `_score_person_pair()` and `_score_org_pair()`.

**Site scoring flow:**
1. Normalize address fields (uppercase, expand abbreviations, collapse whitespace)
2. Apply Jaro-Winkler on normalized addressLine1, addressLine2, city, county
3. Apply exact match on postalCode, country, operatingUnit
4. Sum cumulative points
5. Compute normalized score (cumulative / maxPossible)
6. Classify: isDefinitive if cumulative >= 200 or < 80

### Component 4: Address Normalization Module — NEW

Pure function `normalize_address(text: str) -> str` used by RuleBasedMatchTool before JW comparison.

**Normalization steps:**
1. Convert to uppercase
2. Strip leading/trailing whitespace
3. Remove punctuation (periods, commas retained as space separators)
4. Expand abbreviations: ST→STREET, RD→ROAD, AVE→AVENUE, BLVD→BOULEVARD, LN→LANE, DR→DRIVE, CT→COURT, PL→PLACE
5. Collapse multiple spaces to single space

**International handling:**
- UK postcodes: normalize spacing (e.g., "SE95EE" → "SE9 5EE")
- Spanish addresses: "C." prefix preserved (common abbreviation for "Calle"), "NAVE" preserved

### Component 5: Orchestrator Threshold Routing — MODIFIED

The existing `process_register()` in `orchestrator.py` and LangGraph orchestrator already route by `partyType`. The SITE branch uses:
- **High confidence:** cumulative >= 200 → ReviewQueue
- **Potential duplicate:** cumulative >= 120 → ReviewQueue  
- **New record:** cumulative < 120 → CreateSiteTool (writes to SiteTable)

### Component 6: Dashboard Extensions — MODIFIED

- **Sites tab:** Table view with Account Number, Account Description, Site Number, Address Line 1, City, Postal Code, Country, Operating Unit, Purpose, Status columns
- **Filter:** Account Number filter to view all sites within one account
- **Register Site form:** Fields for accountNumber, siteNumber, addressLine1, city, postalCode, country, operatingUnit, purpose
- **Review display:** Site reviews show partyType "SITE" badge, side-by-side address comparison with Account Number, Site Number, Operating Unit, Purpose

## Data Models

### SiteTable (DynamoDB)

| Field | Type | Key | Required | Description |
|-------|------|-----|----------|-------------|
| siteId | String | PK | Yes | UUID, unique site identifier |
| accountNumber | String | GSI-1 PK | Yes | Oracle EBS account number (e.g., "3518670") |
| accountDescription | String | — | Yes | Account name (e.g., "ELTHAM HILL SCHOOL") |
| siteNumber | String | GSI-1 SK | Yes | Oracle EBS site number (e.g., "4861217") |
| operatingUnit | String | — | Yes | Business unit (e.g., "GB Pearson Education OU") |
| purpose | String | — | Yes | "Bill To", "Ship To", or "Bill To/Ship To" |
| profileClass | String | — | No | Classification (e.g., "DEFAULT", "EDUCATION") |
| status | String | — | Yes | "active" or "merged" |
| country | String | — | Yes | Country name (e.g., "United Kingdom", "Spain") |
| addressLine1 | String | — | Yes | Primary address line |
| addressLine2 | String | — | No | Secondary address line |
| city | String | — | Yes | City name |
| postalCode | String | GSI-2 PK | Yes | Postal/zip code |
| county | String | — | No | County/region |
| sourceSystem | String | — | Yes | Origin system (OneCRM, NES) |
| createdAt | String | — | Yes | ISO 8601 timestamp |
| updatedAt | String | — | Yes | ISO 8601 timestamp |
| mergedInto | String | — | No | siteId of master site (if merged) |

**GSI-1 (AccountNumberIndex):** accountNumber (PK), siteNumber (SK)
**GSI-2 (PostalCodeIndex):** postalCode (PK)

### Site Scoring Configuration (addition to scoring_config.json)

```json
{
  "SITE": {
    "matchThreshold": 120,
    "scoreType": "cumulative",
    "weights": {
      "addressLine1_jw": 90,
      "addressLine2_jw": 25,
      "city_jw": 30,
      "postalCode_exact": 55,
      "country_exact": 40,
      "county_jw": 15,
      "operatingUnit_exact": 20
    },
    "jw_thresholds": {
      "addressLine1": 0.80,
      "addressLine2": 0.80,
      "city": 0.85,
      "county": 0.85
    },
    "thresholds": {
      "high_confidence": 200,
      "potential_duplicate": 120,
      "new_record": 120
    },
    "isDefinitive": {
      "high": 200,
      "low": 80
    },
    "maxCandidates": 50
  }
}
```

**Max possible cumulative score:** 90 + 25 + 30 + 55 + 40 + 15 + 20 = **275**

### POST /register Request Schema (SITE)

```json
{
  "partyType": "SITE",
  "accountNumber": "string (required)",
  "accountDescription": "string (required)",
  "siteNumber": "string (required)",
  "operatingUnit": "string (required)",
  "purpose": "string (required) — Bill To | Ship To | Bill To/Ship To",
  "country": "string (required)",
  "addressLine1": "string (required)",
  "addressLine2": "string (optional)",
  "city": "string (required)",
  "postalCode": "string (required)",
  "county": "string (optional)",
  "profileClass": "string (optional)",
  "sourceSystem": "string (required)"
}
```

### Site Seed Data Structure

```json
[
  {
    "siteId": "site-0001-eltham-hill-001",
    "accountNumber": "3518670",
    "accountDescription": "ELTHAM HILL SCHOOL",
    "siteNumber": "4861217",
    "operatingUnit": "GB Pearson Education OU",
    "purpose": "Bill To",
    "profileClass": "EDUCATION",
    "status": "active",
    "country": "United Kingdom",
    "addressLine1": "ELTHAM HILL",
    "addressLine2": "",
    "city": "LONDON",
    "postalCode": "SE9 5EE",
    "county": "GREENWICH",
    "sourceSystem": "OneCRM",
    "createdAt": "2023-06-15T08:00:00Z",
    "updatedAt": "2023-06-15T08:00:00Z",
    "mergedInto": null
  },
  {
    "siteId": "site-0001-eltham-hill-002",
    "accountNumber": "3518670",
    "accountDescription": "ELTHAM HILL SCHOOL",
    "siteNumber": "18468448",
    "operatingUnit": "GB Pearson Education OU",
    "purpose": "Ship To",
    "profileClass": "EDUCATION",
    "status": "active",
    "country": "United Kingdom",
    "addressLine1": "ELTHAM HILL SCHOOL, ELTHAM HILL",
    "addressLine2": "",
    "city": "LONDON",
    "postalCode": "SE9 5EE",
    "county": "GREENWICH",
    "sourceSystem": "NES",
    "createdAt": "2023-09-20T10:30:00Z",
    "updatedAt": "2023-09-20T10:30:00Z",
    "mergedInto": null
  }
]
```

Full seed data includes:
- **ELTHAM HILL SCHOOL** (Account 3518670): 6 sites with variations — "ELTHAM HILL" vs "ELTHAM HILL SCHOOL, ELTHAM HILL", uppercase vs mixed case, with/without addressLine2
- **MERCHANFACTORY** (Account 57306583): 3 sites with identical address "C. DE LA RESINA, 35, NAVE 7" but different purposes (Bill To, Ship To, Bill To/Ship To)
- **WESTFIELD ACADEMY** (Account 9912345): 2 sites with genuinely different addresses (non-duplicate control)
- **SOLO TRADING LTD** (Account 8800001): 1 site only (new record path)


## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Address Normalization Invariants

*For any* address string, normalizing it should be idempotent (normalize(normalize(s)) == normalize(s)), case-insensitive (normalize(s.upper()) == normalize(s.lower())), and produce output with no leading/trailing whitespace and no consecutive internal spaces.

**Validates: Requirements 2.2, 10.4, 10.5**

### Property 2: Site Scoring Correctness

*For any* pair of site records sharing the same accountNumber, the Site_Scoring algorithm SHALL compute a cumulative score equal to the sum of individual attribute weights where the corresponding comparison (Jaro-Winkler >= threshold or exact match) passes, and the resulting classification (high_confidence if >= 200, potential_duplicate if >= 120, new_record if < 120) SHALL be consistent with the cumulative score.

**Validates: Requirements 2.1, 2.3, 4.1, 4.4, 4.5**

### Property 3: Minimum Score Guarantee for Identical Address + PostalCode

*For any* two site records where the normalized addressLine1 values are identical and the postalCode values are identical, the cumulative score SHALL be at least 145 (addressLine1 JW 1.0 = 90 points + postalCode exact = 55 points).

**Validates: Requirements 2.6**

### Property 4: Intra-Account Query Correctness

*For any* site record with a given accountNumber, querying with partyType "SITE" SHALL return all active site records in the SiteTable sharing that accountNumber, excluding the queried record itself, capped at 50 results.

**Validates: Requirements 3.1, 3.2, 3.3**

### Property 5: Account Isolation

*For any* two site records with different accountNumbers, the system SHALL never produce a match score between them during intra-account dedup. Site scoring is only applied to candidates within the same account.

**Validates: Requirements 2.4, 8.1**

### Property 6: Required Field Validation

*For any* site record submission missing one or more required fields (accountNumber, siteNumber, addressLine1, city, postalCode, country), the system SHALL reject the record with a validation error and SHALL NOT write it to the SiteTable.

**Validates: Requirements 1.5**

### Property 7: Storage Round-Trip Preserves Original Address

*For any* site record stored in the SiteTable, retrieving it SHALL return the original address fields (addressLine1, addressLine2, city, postalCode, county, country) exactly as submitted, without normalization applied to stored data.

**Validates: Requirements 10.6, 1.4**

### Property 8: Merge Master Selection and Purpose Consolidation

*For any* pair of duplicate site records being merged, the site with the numerically lowest siteNumber SHALL be selected as the master record. If the two sites have different purposes, the master record's purpose SHALL be updated to "Bill To/Ship To". The source record SHALL have status set to "merged" with mergedInto referencing the master siteId, and no records SHALL be deleted.

**Validates: Requirements 9.1, 9.2, 9.3, 9.4**

## Error Handling

Follows the same error handling patterns as the existing design (see [existing design doc](../customer-data-deduplication/design.md#error-handling)). Additional site-specific errors:

| Error Type | HTTP Code | Scenario | System Action |
|------------|-----------|----------|---------------|
| Validation | 400 | Missing accountNumber in site record | Return field-level error: "accountNumber is required for site records" |
| Validation | 400 | Missing required site fields | Return list of missing fields |
| Validation | 400 | Invalid purpose value | Return allowed values: "Bill To", "Ship To", "Bill To/Ship To" |
| Not Found | 404 | accountNumber has no existing sites | Proceed with CreateSite (not an error — first site in account) |

## Testing Strategy

### Property-Based Tests (using Hypothesis for Python)

Each correctness property is implemented as a property-based test with minimum 100 iterations:

| Property | Test File | Generator Strategy |
|----------|-----------|-------------------|
| 1: Normalization invariants | `tests/test_site_normalization.py` | Random strings with mixed case, whitespace, abbreviations, UK/Spanish formats |
| 2: Scoring correctness | `tests/test_site_scoring.py` | Random site record pairs with controlled field similarities |
| 3: Minimum score guarantee | `tests/test_site_scoring.py` | Random records with identical addressLine1 + postalCode |
| 4: Query correctness | `tests/test_site_query.py` | Random accounts with 1–60 sites, verify result set |
| 5: Account isolation | `tests/test_site_scoring.py` | Random records with different accountNumbers |
| 6: Field validation | `tests/test_site_validation.py` | Random subsets of required fields removed |
| 7: Storage round-trip | `tests/test_site_storage.py` | Random international addresses stored and retrieved |
| 8: Merge logic | `tests/test_site_merge.py` | Random site pairs with varying siteNumbers and purposes |

**Configuration:** Each test runs minimum 100 iterations via `@settings(max_examples=100)`.
**Tagging:** Each test is tagged with `# Feature: site-level-dedup, Property N: <property text>`.

### Unit Tests (example-based)

- API Gateway schema validation (valid/invalid site payloads)
- Seed data structure verification
- Dashboard rendering of site records (manual/visual)
- Specific demo scenarios (ELTHAM HILL SCHOOL duplicate detection, MERCHANFACTORY identical addresses)

### Integration Tests

- End-to-end site registration via POST /register
- Batch site dedup with mixed partyTypes
- Site merge approval/rejection flow
- Performance: site registration < 5 seconds

### Demo Scenarios

**Scenario A: ELTHAM HILL SCHOOL — Address Variation Detection**
1. Seed SiteTable with 6 ELTHAM HILL SCHOOL sites
2. POST /register with a 7th variation: "Eltham Hill School, Eltham Hill, London, SE9 5EE"
3. Expected: review_pending, high_confidence (addressLine1 JW high + postalCode exact + city exact + country exact)

**Scenario B: MERCHANFACTORY — Identical Address, Different Purpose**
1. Seed SiteTable with 3 MERCHANFACTORY sites (same address, different purposes)
2. POST /register with identical address, new siteNumber
3. Expected: review_pending, high_confidence (cumulative score near max)

**Scenario C: New Site in Existing Account (No Duplicate)**
1. POST /register with WESTFIELD ACADEMY account, genuinely different address
2. Expected: new_record created in SiteTable

**Scenario D: First Site in New Account**
1. POST /register with SOLO TRADING LTD account (no existing sites)
2. Expected: new_record created (no candidates to compare)

**Scenario E: Batch Site Dedup**
1. Upload JSON with 12 site records (mix of accounts, some duplicates)
2. Expected: batch groups by accountNumber, identifies duplicates within each group, summary report includes site metrics
