---
inclusion: manual
---

# AWS Pricing Analysis - Best Practices
## Comprehensive Cost Estimation for Cloud Solutions

This steering file captures best practices for conducting thorough AWS pricing analysis, distinguishing fixed vs. variable costs, and providing transparent cost estimates for client solutions.

---

## Core Principles

1. **Transparency**: Clearly document all pricing sources, assumptions, and limitations
2. **Accuracy**: Use official AWS Price List API for current pricing data
3. **Clarity**: Distinguish fixed (baseline/idle) costs from variable (consumption) costs
4. **Validation**: Document effective dates and establish validation frequency
5. **Optimization**: Identify cost reduction opportunities at every phase

---

## Pricing Data Sources

### Primary Source: AWS Price List API

**Why Use the API**:
- Official AWS pricing (most accurate and current)
- Programmatic access for automation
- SKU-level detail with effective dates
- Historical pricing available for trend analysis

**API Access**:
```bash
# Example: Query Bedrock pricing
aws pricing get-products \
  --service-code AmazonBedrock \
  --filters Type=TERM_MATCH,Field=location,Value="US East (N. Virginia)" \
  --region us-east-1
```

**Validation Frequency**:
- During project: Monthly validation
- Post-launch: Quarterly validation
- Price change notifications: Subscribe to AWS SNS topic

### Secondary Sources

**AWS Public Pricing Pages**:
- Use for cross-reference validation
- Easier to read than API responses
- Updated when prices change
- URL format: `aws.amazon.com/[service]/pricing/`

**AWS Pricing Calculator**:
- Use for initial estimates and scenario modeling
- Export estimates for documentation
- Share with clients for transparency
- URL: `calculator.aws`

---

## Fixed vs. Variable Cost Framework

### Fixed Costs (Baseline/Idle Costs)

**Definition**: Costs incurred every month regardless of usage, keeping the system ready to respond.

**Common Fixed Cost Services**:

1. **CloudWatch**
   - Custom metrics: $0.30 per metric/month
   - Alarms: $0.10 per alarm/month
   - Dashboards: Included in free tier
   - **Why Fixed**: 24/7 monitoring ensures system readiness

2. **Secrets Manager**
   - Secret storage: $0.40 per secret/month
   - API calls: $0.05 per 10,000 calls
   - **Why Fixed**: Credentials must be available 24/7

3. **DynamoDB Storage**
   - Storage: $0.25 per GB/month
   - **Why Fixed**: Configuration data persists between events

4. **S3 Storage**
   - Standard storage: $0.023 per GB/month
   - **Why Fixed**: Deployment artifacts must be available

**Documentation Requirements for Fixed Costs**:
- List each service with monthly cost
- Document assumptions (number of metrics, secrets, storage volume)
- Explain why these costs are necessary (system readiness)
- Calculate annual cost (monthly × 12)
- Identify optimization opportunities

### Variable Costs (Consumption/Usage-Based)

**Definition**: Costs that scale with actual usage during active periods (e.g., operational events, user interactions).

**Common Variable Cost Services**:

1. **Bedrock (AI Inference)**
   - Input tokens: $0.003 per 1K tokens
   - Output tokens: $0.015 per 1K tokens
   - **Cost Driver**: Number of AI interactions

2. **Bedrock AgentCore (Platform)**
   - Runtime: $0.0895 per vCPU-hour + $0.00945 per GB-hour (active consumption only)
   - Gateway: $0.005 per 1K InvokeTool calls + $0.025 per 1K Search API calls
   - Memory: $0.25 per 1K short-term events + $0.50 per 1K long-term retrievals
   - Tool Indexing: $0.02 per 100 tools/month (fixed component)
   - **Cost Driver**: Number of agent interactions and tool invocations
   - **Typical per-interaction cost**: ~$0.0015

3. **Lambda (Compute)**
   - Requests: $0.20 per 1M requests
   - Compute: $0.0000166667 per GB-second
   - **Cost Driver**: Number of function invocations

4. **SNS (SMS)**
   - Transactional SMS: $0.00645 per message (US)
   - **Cost Driver**: Number of SMS messages sent

5. **SES (Email)**
   - First 62,000 emails/month: Free (from Lambda)
   - Beyond 62K: $0.10 per 1,000 emails
   - **Cost Driver**: Number of emails sent

6. **Connect (Voice)**
   - Usage: ~$0.018 per minute
   - Transcription: ~$0.024 per minute
   - **Cost Driver**: Number and duration of voice calls

7. **Pinpoint (Push Notifications)**
   - Push notifications: $0.0001 per notification
   - **Cost Driver**: Number of push notifications

8. **DynamoDB (Operations)**
   - Write requests: $1.25 per million writes
   - Read requests: $0.25 per million reads
   - **Cost Driver**: Number of database operations

9. **Step Functions**
   - State transitions: $0.025 per 1,000 transitions
   - **Cost Driver**: Number of workflow executions

10. **EventBridge**
   - Custom events: $1.00 per million events
   - **Cost Driver**: Number of events published

**Documentation Requirements for Variable Costs**:
- List each service with unit cost
- Document cost drivers (interactions, messages, calls)
- Calculate cost per interaction/event
- Model costs across scenarios (low, anticipated, high)
- Show how costs scale with usage

---

## Scenario Modeling

### Three-Scenario Approach

Create three usage scenarios to bracket expected costs:

**1. Low Scenario**
- Minimal activity (e.g., 2 events/year, 50 users, 5 days)
- Use for conservative budgeting
- Represents best-case cost scenario

**2. Anticipated Scenario**
- Normal operations (e.g., 3-4 events/year, 100 users, 7 days)
- Use for primary budget planning
- Based on historical data and trends

**3. High Scenario**
- Active season (e.g., 4-5 events/year, 150 users, 10 days)
- Use for capacity planning and worst-case budgeting
- Ensures solution can scale to peak demand

### Scenario Documentation Template

For each scenario, document:

```markdown
## [Scenario Name] Scenario

**Business Context**: [Description of usage pattern]

**Key Assumptions**:
- Events per year: [number]
- Users per event: [number]
- Days per event: [number]
- Interactions per user per day: [number]
- Total interactions per year: [calculation]

**Cost Breakdown**:
| Service | Monthly Cost | Annual Cost | Notes |
|---------|--------------|-------------|-------|
| [Service 1] | $X.XX | $X.XX | [Cost driver] |
| [Service 2] | $X.XX | $X.XX | [Cost driver] |
| **Total** | **$X.XX** | **$X.XX** | |

**Cost per Interaction**: $X.XX
**Cost per Event**: $X.XX
```

---

## Cost Calculation Methodology

### Step 1: Identify All AWS Services

Create comprehensive service inventory:
- Service name
- Purpose/role in solution
- Usage pattern (always-on vs. event-driven)
- Cost model (fixed, variable, or hybrid)

### Step 2: Gather Pricing Data

For each service:
- Query AWS Price List API for current pricing
- Document SKU and effective date
- Note any free tier benefits
- Identify pricing tiers or volume discounts

### Step 3: Document Assumptions

For each service, document:
- **Fixed Costs**: Number of metrics, alarms, secrets, storage volume
- **Variable Costs**: Interactions per event, event frequency, user count, duration

### Step 4: Calculate Costs

**Fixed Costs**:
```
Monthly Fixed Cost = Sum of all always-on service costs
Annual Fixed Cost = Monthly Fixed Cost × 12
```

**Variable Costs**:
```
Cost per Interaction = Sum of per-interaction costs across all services
Cost per Event = Cost per Interaction × Interactions per Event
Monthly Variable Cost = (Cost per Event × Events per Year) / 12
Annual Variable Cost = Cost per Event × Events per Year
```

**Total Costs**:
```
Monthly Total = Monthly Fixed + Monthly Variable
Annual Total = Annual Fixed + Annual Variable
```

### Step 5: Create Cost Summary Table

```markdown
| Service | Fixed Cost | Variable Cost | Total (Anticipated) |
|---------|-----------|---------------|---------------------|
| [Service 1] | $X.XX/month | $X.XX/interaction | $X.XX/month |
| [Service 2] | $X.XX/month | $X.XX/interaction | $X.XX/month |
| **Total** | **$X.XX/month** | **$X.XX/interaction** | **$X.XX/month** |
```

---

## Pricing Disclaimers and Limitations

### Required Disclaimers

**1. Pricing Source Disclaimer**
```markdown
**Pricing Source**: All pricing data in this document is sourced from the 
AWS Price List API, which provides AWS's official public list prices as of 
the effective dates noted for each service.
```

**2. Private Pricing Agreements (PPAs) Disclaimer**
```markdown
**⚠️ Private Pricing Agreements (PPAs) Not Included**

This pricing analysis is based on **standard AWS public pricing** and does 
**NOT** account for:

1. Private Pricing Agreements (PPAs): Custom negotiated pricing
2. Enterprise Discount Programs (EDPs): Volume-based discounts
3. AWS Credits: Promotional credits or migration incentives
4. Reserved Instance Discounts: 1-year or 3-year commitments
5. Savings Plans: Compute Savings Plans or other commitment-based discounts
6. AWS Partner Discounts: Discounts provided through consulting partners

**Actual Costs May Be Lower**: If the client has negotiated any of the above 
arrangements with AWS, actual costs will be lower than the estimates in this 
document. We recommend:

1. Consult with the client's AWS Account Team to understand existing agreements
2. Apply negotiated discount rates to the usage estimates
3. Factor in any available AWS credits
4. Consider Reserved Capacity after establishing baseline usage patterns
```

**3. Validation Disclaimer**
```markdown
**Cost Validation**: The client should validate these estimates with their 
AWS account team and apply any applicable discounts before finalizing budget 
approvals.

**Last Validated**: [Date]
**Next Validation Due**: [Date]
```

---

## Cost Optimization Framework

### Immediate Optimizations (0-3 Months)

**1. CloudWatch Metrics Reduction**
- Current: 50 custom metrics
- Optimized: 20 essential metrics
- Savings: $9/month (43% reduction in fixed costs)

**2. Secrets Manager to Parameter Store**
- Migrate non-sensitive config to Systems Manager Parameter Store
- Cost: $0.05 per 10K requests vs. $0.40 per secret
- Savings: $2-3/month

**3. S3 Lifecycle Policies**
- Move logs to S3 Glacier after 30 days
- Cost: $0.004 per GB (Glacier) vs. $0.023 per GB (Standard)
- Savings: 90% on archived logs

### Medium-Term Optimizations (3-6 Months)

**4. Foundation Model Selection**
- Evaluate Amazon Nova vs. Claude 3 Sonnet
- Potential savings: 30-50% of AI inference costs
- Test performance vs. cost tradeoff

**5. Prompt Caching**
- Cache system prompts and common context
- Potential savings: 20-30% of Bedrock costs

**6. SMS to Mobile App Migration**
- Shift 50% of SMS to push notifications
- SMS: $0.00645 per message
- Push: $0.0001 per notification
- Savings: ~$2.37/month per 1,000 messages

### Long-Term Optimizations (6-12 Months)

**7. Reserved Capacity**
- Lambda Provisioned Concurrency: 30-50% savings
- DynamoDB Reserved Capacity: 30-50% savings
- Requires predictable baseline usage patterns

**8. Savings Plans**
- Compute Savings Plans for Lambda and Fargate
- 1-year or 3-year commitment
- Up to 17% savings vs. on-demand

**9. Private Pricing Agreements (PPAs)**
- Negotiate with AWS account team
- Present actual usage data
- Potential 10-40% discount depending on volume

---

## Documentation Structure

### Required Documents

**1. AWS Pricing Summary**
- Executive summary with total costs
- Fixed vs. variable cost breakdown
- Scenario cost models (low, anticipated, high)
- Service-by-service pricing with assumptions
- Cost optimization roadmap
- Pricing disclaimers and validation plan

**2. AWS Pricing Calculator Inputs**
- Detailed assumptions for each service
- Usage patterns and cost drivers
- Scenario definitions
- Calculation formulas
- Development and testing costs

**3. Pricing Validation Plan**
- Validation methodology
- Validation frequency (monthly during project, quarterly post-launch)
- Validation commands (AWS CLI examples)
- Next review date

### Document Templates

**Service Pricing Template**:
```markdown
### [Service Name]

**Service Type**: [Category]
**Role**: [Purpose in solution]

**Pricing**:
- [Pricing dimension 1]: $X.XX per [unit]
- [Pricing dimension 2]: $X.XX per [unit]
- **Source**: AWS Price List API, SKU: [SKU]
- **Effective Date**: [YYYY-MM-DD]

**Monthly Cost Calculations**:
| Scenario | [Dimension 1] | [Dimension 2] | Total |
|----------|---------------|---------------|-------|
| Low | [value] | [value] | **$X.XX** |
| Anticipated | [value] | [value] | **$X.XX** |
| High | [value] | [value] | **$X.XX** |

**Assumptions**:
- [Assumption 1]
- [Assumption 2]
- [Assumption 3]

**Free Tier**: [Description if applicable]
```

---

## Pricing Validation Process

### Monthly Validation (During Project)

**1. Check for Price Changes**
```bash
# List recent price lists for a service
aws pricing list-price-lists \
  --service-code [ServiceCode] \
  --currency-code USD \
  --effective-date $(date +%Y-%m-%d) \
  --region us-east-1
```

**2. Compare Effective Dates**
- Check if version number has changed
- Review any new pricing tiers or models
- Update estimates if material changes (>10% variance)

**3. Document Changes**
- Note what changed and when
- Recalculate affected scenarios
- Update business case if needed
- Notify stakeholders of material changes

### Quarterly Validation (Post-Launch)

**1. Compare Actual vs. Estimated Costs**
- Pull actual AWS costs from Cost Explorer
- Compare to pricing estimates
- Identify variances and root causes

**2. Adjust Assumptions**
- Update usage assumptions based on actual data
- Refine cost models for future projects
- Document lessons learned

**3. Optimize Costs**
- Implement cost optimization recommendations
- Track savings achieved
- Identify new optimization opportunities

---

## Common Pitfalls to Avoid

1. **Ignoring Free Tiers**: Lambda and SES have generous free tiers that significantly reduce costs
2. **Forgetting Data Transfer**: Include data transfer costs (especially for multi-region)
3. **Underestimating CloudWatch**: Metrics and alarms can be significant fixed costs
4. **Overlooking API Calls**: Secrets Manager, DynamoDB, and S3 API calls add up
5. **Not Accounting for Development**: Include dev/test environment costs in project budget
6. **Missing External Services**: Don't forget third-party APIs (geocoding, traffic, weather)
7. **Ignoring PPAs**: Always note that client may have negotiated discounts
8. **Static Estimates**: Update estimates as usage patterns become clear

---

## Best Practices Checklist

Before finalizing pricing analysis:

- [ ] All AWS services identified and documented
- [ ] Pricing sourced from AWS Price List API with effective dates
- [ ] Fixed vs. variable costs clearly distinguished
- [ ] Assumptions documented for each service
- [ ] Three scenarios modeled (low, anticipated, high)
- [ ] Cost per interaction calculated
- [ ] Free tier benefits identified and applied
- [ ] External service costs included
- [ ] PPA disclaimer included
- [ ] Cost optimization opportunities identified
- [ ] Validation plan established
- [ ] Client review and approval obtained

---

## Example: Complete Service Analysis

### Amazon Bedrock - Claude 3 Sonnet

**Service Type**: AI/ML - Foundation Models  
**Role**: Core AI inference engine for agent responses

**Pricing**:
- Input tokens: $0.003 per 1K tokens ($3.00 per 1M tokens)
- Output tokens: $0.015 per 1K tokens ($15.00 per 1M tokens)
- **Source**: AWS Price List API, SKU: ZEJSXGT973DYB7JF
- **Effective Date**: 2026-01-01

**Usage Pattern**:
- Average prompt size: 1,500 tokens (system prompt + context)
- Average response size: 500 tokens
- Total tokens per interaction: 2,000 tokens (1,500 input + 500 output)

**Monthly Cost Calculations**:
| Scenario | Interactions | Input Tokens | Output Tokens | Input Cost | Output Cost | Total |
|----------|--------------|--------------|---------------|------------|-------------|-------|
| Low | 208 | 312,500 | 104,167 | $0.94 | $1.56 | **$2.50** |
| Anticipated | 1,225 | 1,837,500 | 612,500 | $5.51 | $9.19 | **$14.70** |
| High | 5,000 | 7,500,000 | 2,500,000 | $22.50 | $37.50 | **$60.00** |

**Assumptions**:
- 3-5 turns per interaction (average 4 turns)
- System prompt cached (not counted in input tokens)
- Response includes structured data (JSON) for tool calls

**Cost Model**: Variable - $0.02-0.05 per interaction

**Optimization Opportunities**:
1. Evaluate Amazon Nova (30-50% cheaper)
2. Implement prompt caching (20-30% savings)
3. Optimize prompt length (reduce input tokens)

---

**Document Owner**: IBM Consulting - Cloud Economics Practice  
**Last Updated**: February 2026  
**Next Review**: Quarterly (or after major AWS pricing changes)

---

**END OF DOCUMENT**
