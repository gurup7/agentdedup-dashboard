# AgentDedup — Demo Cheat Sheet

## Dashboard URL

**Gradio (App Runner):** https://fpxybbyznx.us-east-1.awsapprunner.com

**Streamlit (local):** http://localhost:8501 (run `streamlit run dashboard/app.py`)

---

## Pre-Demo Setup (run once before demo)

```bash
python scripts/demo-reset.py
```

This seeds 22 person + 5 organization records and clears all previous reviews.

---

## Demo Flow (5 Scenarios, ~15 minutes)

### Scenario 1: Register New Unique Person ✅ → new_record

**Tab:** Register Customer → Person

| Field | Value |
|-------|-------|
| First Name | John |
| Last Name | Doe |
| Email | john.doe@example.com |
| Source System | OneCRM |

**Expected:** Green banner — "New person record created!"
**Talking Point:** "No match found in TEP — record created instantly in < 3 seconds."

---

### Scenario 2: Detect Person Duplicate ⚠️ → review_pending

**Tab:** Register Customer → Person

| Field | Value |
|-------|-------|
| First Name | Chris |
| Last Name | James |
| Email | chris.james@fakecorp.com |
| DOB | 1985-03-15 |
| Source System | NES |

**Expected:** Yellow banner — "Potential duplicate detected!" (~100% confidence)
**Talking Point:** "Same email + DOB + name matched via Jaro-Winkler. Routed to review queue — no auto-merge."

---

### Scenario 3: Register New Unique Organization ✅ → new_record

**Tab:** Register Customer → Organization

| Field | Value |
|-------|-------|
| Party Name | Acme Corp International |
| Tax Registration | TAX-ACME-9999 |
| Match Market | US-TECHNOLOGY |
| Source System | OneCRM |

**Expected:** Green banner — "New organization record created!"
**Talking Point:** "No matching org in TEP. Different market, different tax ID."

---

### Scenario 4: Detect Organization Duplicate ⚠️ → review_pending

**Tab:** Register Customer → Organization

| Field | Value |
|-------|-------|
| Party Name | Pearson Education |
| Tax Registration | TAX-PE-2024-001 |
| Taxpayer ID | TP-84-1234567 |
| MDR PID | MDR-PE-0001 |
| Match Market | US-EDUCATION |
| Street | 221 River Street |
| City | Hoboken |
| State | NJ |
| Postal Code | 07030 |
| Source System | NES |

**Expected:** Yellow banner — "Potential duplicate organization detected!" (~98% confidence)
**Talking Point:** "Oracle TCA cumulative scoring — partyName + taxReg + taxpayerId + address = 888 points, well above 144 threshold."

---

### Scenario 5: Approve Merge ✅ → merged

**Tab:** Duplicate Reviews → find the pending review → click "Approve"

**Expected:** Green banner — "Merge approved!"
**Then show:** Accounts tab → filter by status — source record shows "merged"

**Talking Point:** "Data Steward approved. Source record marked 'merged' with pointer to master. No data deleted — full traceability."

---

## Quick Navigation Guide

| Tab | What to Show |
|-----|-------------|
| 📇 Accounts | All customer records — filter by Party Type (Person/Organization) |
| 🔀 Duplicate Reviews | Pending merge candidates — side-by-side comparison |
| ➕ Register Customer | Toggle Person/Organization — submit new records |
| 📦 Batch Scan | Trigger Clean Agent batch — check status |
| 📊 Dashboard | Pie charts, metrics, confidence distribution |

---

## Key Talking Points

- **Two AI agents:** Intercept (real-time) + Clean (batch) on Amazon Bedrock AgentCore
- **LangGraph orchestration:** LLM dynamically decides which tools to call
- **Two-stage matching:** Rule-based (Jaro-Winkler, Soundex) + LLM (Bedrock Nova Pro)
- **Person + Organization:** Different scoring rules per Oracle TCA match rules
- **Human-in-the-loop:** All merges require Data Steward approval
- **No deletions:** Merged records preserved with full audit trail
- **16 AWS services:** Serverless, pay-per-use, auto-scaling
- **< 3 second response:** Well under 5-second SLA
- **Production-ready:** Swap DynamoDB → Oracle EBS by changing only Lambda tool code

---

## Chatbot Commands (Sidebar)

Try these in the sidebar chatbot:
- "How many customers?" → shows count
- "Show reviews" → switches to reviews tab
- "Register John Smith from OneCRM with email john@test.com" → registers via API
- "Approve [reviewId]" → approves a merge
- "Run batch scan" → triggers Clean Agent

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| No data showing | Run `python scripts/demo-reset.py` |
| "Internal server error" | Check API key is set in .env |
| Merge fails "missing record IDs" | Run demo-reset.py to refresh merge demo data |
| Batch scan fails | Check AWS credentials have Step Functions access |

---

## Architecture Quick Reference

```
Sales Systems (OneCRM, NES)
    ↓
API Gateway (POST /register)
    ↓
Step Functions Express
    ↓
Intercept Agent (AgentCore Runtime + LangGraph)
    ↓
Lambda Tools (Query → RuleMatch → LLMMatch → Decision)
    ↓
DynamoDB (CustomerTable + ReviewQueue)
    ↓
Dashboard (Streamlit on App Runner)
```
