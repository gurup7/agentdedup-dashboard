# Client Demo Guide — Customer Data Deduplication Prototype

## Pre-Demo Setup (5 minutes before)

Run this command to reset all data to a clean state:

```bash
python scripts/demo-reset.py
```

This clears all previous test data and seeds fresh records for the demo.

---

## Demo Flow

### API Details

- **Base URL**: `https://qlx4tvau7g.execute-api.us-east-1.amazonaws.com/prod`
- **API Key**: `j88R5YxG7f3enQYQnJJO86Wi5Pu8jE4u2s9wgYBc`
- **Postman Workspace**: Customer Data Deduplication Prototype

---

### Scenario 1: New Unique Customer (Intercept Agent)

**Story**: "A new customer is registered in OneCRM. The Intercept Agent checks if this person already exists in TEP before allowing the record in."

**Steps**:
1. Open Postman → "Scenario 1: Register New Unique Customer (Intercept Agent)"
2. Click **Send**

**Expected Response**:
```
status: new_record
customerId: <new UUID>
confidenceScore: 0.0
sourceAgent: intercept
```

**Talking Points**:
- The Intercept Agent sat between OneCRM and TEP
- It searched the entire customer database — no matches found
- A new record was created in TEP (DynamoDB)
- Processing time: < 3 seconds

**Verify in Database** (optional):
```bash
python -c "
import boto3, json
table = boto3.resource('dynamodb', region_name='us-east-1').Table('dedup-dynamodb-CustomerTable')
resp = table.scan(FilterExpression='firstName = :fn', ExpressionAttributeValues={':fn': 'Guruprakash'})
for item in resp['Items']:
    print(json.dumps({'customerId': item['customerId'], 'name': f\"{item['firstName']} {item['lastName']}\", 'status': item['status'], 'source': item['sourceSystem']}, indent=2))
"
```

---

### Scenario 2: Duplicate Detection (Intercept Agent)

**Story**: "The same person is now being registered from NES — slightly different data (shortened first name, different phone). The Intercept Agent catches it."

**Steps**:
1. Open Postman → "Scenario 2: Duplicate from NES (Intercept Agent)"
2. Click **Send**

**Expected Response**:
```
status: review_pending
confidenceScore: ~0.93
confidenceClassification: high_confidence
matchingMethod: rule_based
sourceAgent: intercept
matchedRecord: {the original OneCRM record}
```

**Talking Points**:
- Same email triggered the match (+0.4 score)
- Same DOB added confidence (+0.2)
- Same postal code + similar last name via Jaro-Winkler
- Even though first name was "Guru" vs "Guruprakash" — still caught at 93%
- Record was NOT created — intercepted before entering TEP
- Routed to ReviewQueue for human decision
- No auto-merge — Data Steward must approve

---

### Scenario 3: Batch Scan of Existing TEP Duplicates (Clean Agent)

**Story**: "There are already duplicate records in TEP from years of manual entry across OneCRM and NES. The Clean Agent scans a batch of existing records to find and flag these historical duplicates."

**Steps**:
1. Open Postman → "Scenario 3: Batch Scan Existing TEP Dupes (Clean Agent)"
2. Set Authorization → AWS Signature (AccessKey, SecretKey, Region: us-east-1, Service: states)
3. Click **Send**

**Expected Response**:
```json
{
  "executionArn": "arn:aws:states:...",
  "startDate": ...
}
```

4. Wait 30-60 seconds, then verify results:
```bash
python scripts/list-reviews.py
```

**Expected**: New reviews with `agent: clean` appear in the ReviewQueue.

**Talking Points**:
- The Clean Agent processed 4 records from a CSV/JSON file in S3
- It found duplicates of existing TEP records (Chris James, Maria Garcia, etc.)
- All flagged for human review — no auto-merge
- Summary report written to S3 with counts
- Different agent, same matching pipeline, same ReviewQueue

**Show Summary Report**:
```bash
aws s3 ls s3://dedup-s3-dedup-batch-reports/batch-reports/ --recursive --region us-east-1
```

---

### Scenario 4: Approve Merge (Data Steward Action)

**Story**: "A Data Steward reviews the duplicate pair and approves the merge. The system consolidates the records while preserving all original data."

**Steps**:
1. Open Postman → "Scenario 4: Approve Merge (Intercept Agent)"
2. Click **Send**

**Expected Response**:
```
status: approved
mergedRecordId: demo-merge-master-001
sourceRecordId: demo-merge-source-001
sourceAgent: intercept
```

3. Show the database state after merge:
```bash
python scripts/show-merge-result.py
```

**Expected**:
- Source record: `status: merged`, `mergedInto: demo-merge-master-001`
- Master record: `status: active` (preserved)
- Review: `status: approved`
- NO records deleted

**Talking Points**:
- Human approved the merge — system executed it
- Source record marked as "merged" with pointer to master
- Master record stays active — the surviving record
- Full traceability: you can always trace back to the original
- No data loss — both records still exist in the database
- Audit log written to S3 for compliance

---

### Scenario 5: Organization Duplicate Detection (Intercept Agent)

**Story**: "An organization record is being registered from NES. The Intercept Agent checks if this organization already exists in TEP using Oracle TCA-style cumulative scoring."

**Steps**:
1. Open Dashboard → **Register Customer** tab → switch to **Organization**
2. Enter:
   - Party Name: `Pearson Education`
   - Tax Registration: `TAX-PE-2024-001`
   - Taxpayer ID: `TP-84-1234567`
   - MDR PID: `MDR-PE-0001`
   - Match Market: `US-EDUCATION`
   - Address: `221 River Street, Hoboken, NJ 07030`
   - Source: `NES`
3. Click **Register Organization**

**Expected Response**:
```
status: review_pending
confidenceScore: ~0.98
confidenceClassification: high_confidence
matchingMethod: rule_based
matchedRecord: Pearson Education Inc. (OneCRM)
```

**Talking Points**:
- Oracle TCA "Pearson Organization Duplicates" match rule implemented
- Cumulative scoring: partyName JW (89) + Soundex (89) + taxReg (146) + taxpayerId (147) + mdrPidId (145) + matchMarket (148) + address (31) + city (23) + postalCode (55) + state (15) = 888 out of 866 max
- Threshold: 144 cumulative for potential duplicate, 200 for high confidence
- Same pipeline as Person dedup — just different scoring algorithm
- Organization-specific fields: partyName, taxRegistrationNum, taxpayerId, mdrPidId, matchMarket

---

### Scenario 6: New Unique Organization (Intercept Agent)

**Story**: "A completely new organization is registered. No match found in TEP."

**Steps**:
1. Register an organization with unique details (e.g., "Acme Corp International", unique tax IDs)
2. Expected: `new_record` with low confidence score

---

## Architecture Talking Points

- **Two independent agents**: Intercept (real-time) and Clean (batch)
- **Unified Person + Organization dedup**: Same pipeline, different scoring rules per party type
- **Person scoring**: Normalized 0-1 (email, phone, name JW/Soundex, DOB)
- **Organization scoring**: Oracle TCA cumulative (partyName, address, tax IDs, market — threshold 144)
- **Same matching pipeline**: Rule-based (Jaro-Winkler, Soundex, exact match) + LLM (Bedrock) for ambiguous cases
- **Human-in-the-loop**: All merges require Data Steward approval
- **No deletions**: Merge operations preserve source records
- **Oracle EBS ready**: Swap DynamoDB for Oracle EBS REST APIs by changing only Lambda tool code
- **16 AWS services**: Serverless, pay-per-use, auto-scaling
- **< 3 second response time**: Well under the 5-second SLA

---

## Troubleshooting

**"Internal server error" on GET /reviews**:
- Make sure x-api-key header is set

**Scenario 3 returns "MissingAuthenticationToken"**:
- Set Authorization → AWS Signature in Postman (AccessKey, SecretKey, Region, Service: states)

**Merge returns "missing record IDs"**:
- Run `python scripts/demo-reset.py` to reset the merge demo data

**Want to start fresh**:
```bash
python scripts/demo-reset.py
```
