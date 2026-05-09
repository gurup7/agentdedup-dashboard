---
inclusion: manual
---

# Business Value Assessment Guidelines

## Assessment Purpose

Every agent implementation begins with a 2-3 day Business Value Assessment to quantify ROI, establish baseline KPIs, and ensure stakeholder alignment before technical work begins.

## When Business Value Data Is Not Available

### Scenario: Specs Created Before Stakeholder Interviews

Sometimes technical specifications are created before business value assessment is complete. In these cases:

**1. Create Placeholder Business Case Template**
- Use comprehensive template with [PLACEHOLDER] markers
- Include all ROI calculation formulas and frameworks
- Provide example calculations for reference
- Document required data sources and validation status (❌ → ✅)

**2. Benefits of Placeholder Approach**
- Shows stakeholders complete ROI framework upfront
- Identifies exactly what data is needed
- Can be filled in incrementally as data becomes available
- Provides example values to guide data collection
- Maintains project momentum while awaiting data
- Enables parallel work on technical and business tracks

**3. Data Collection Plan**
- List specific metrics needed:
  - Current manual effort (hours/week, hours/cycle)
  - Fully loaded hourly rate (salary + benefits + overhead)
  - Cycle frequency (events/year, cycles/year)
  - Manual effort per unit (minutes/team, minutes/interaction)
- Identify data sources:
  - Stakeholder interviews (end users, managers)
  - Timesheets and time tracking systems
  - System of record data (historical activity)
  - HR/Finance data (labor costs)
- Schedule stakeholder interviews and data gathering sessions
- Track validation status for each assumption

**4. Incremental Updates**
- Update business case as data becomes available
- Recalculate ROI with actual values
- Validate assumptions with stakeholders
- Document changes and rationale
- Update validation status (❌ Not validated → ✅ Validated)

**5. Example Placeholder Template Structure**
```markdown
| Metric | Current State | Data Source | Validation Status |
|--------|---------------|-------------|-------------------|
| Hours/Week | [PLACEHOLDER] | [Interview/timesheet] | ❌ Not validated |
| Hourly Rate | $[PLACEHOLDER] | [HR/Finance] | ❌ Not validated |
| Cycles/Year | [PLACEHOLDER] | [Historical data] | ❌ Not validated |

Example Values (for reference only):
- Hours/Week: 20 hours during events
- Hourly Rate: $75/hour (including benefits, overhead)
- Cycles/Year: 25 cycles (weekly during 3-4 events)
```

**6. When to Use Placeholder Approach**
- Specs created before Phase 0 assessment
- Business value data collection delayed
- Need to maintain technical momentum
- Stakeholders unavailable for immediate interviews
- Parallel technical and business workstreams

---

## Assessment Framework (Phase 0)

### Day 1: Discovery and Current State
- Morning: Stakeholder interviews (end users, managers, executives)
- Afternoon: Process mapping and pain point documentation
- Evening: Data collection and baseline KPI calculation

### Day 2: Future State and Value Quantification
- Morning: Future state workflow design
- Afternoon: KPI projection and business value calculation
- Evening: Change impact analysis and success criteria definition

### Day 3: Reporting and Approval
- Morning: Business value assessment report preparation
- Afternoon: Executive presentation and Q&A
- Evening: Stakeholder sign-off and scope approval

## Assessment Team

| Role | Band | FTE | Responsibilities |
|------|------|-----|------------------|
| Management Consultant | 8 | 1.0 | Lead assessments, facilitate workshops, create reports |
| Business Analyst | 7 | 1.0 | Process mapping, KPI analysis, ROI calculations |
| Data Analyst | 6 | 0.5 | Baseline data collection, metrics analysis |

Total: 2.5 FTEs for 3 days

## Key Assessment Activities

### 1. Stakeholder Interviews
- Interview end users on current processes
- Interview managers on current reporting methods
- Document pain points and manual effort
- Identify bottlenecks and inefficiencies

### 2. Current State Process Mapping
- Map as-is workflows with detailed steps
- Document manual touchpoints and handoffs
- Identify process inefficiencies and delays
- Calculate time spent per operation

### 3. Baseline KPI Definition
- Establish current performance metrics
- Document completion rates and response times
- Measure manual effort (hours/day)
- Assess accuracy and reliability of current data

### 4. Future State KPI Projection
- Define target performance with agent automation
- Project completion rates and response times
- Calculate expected time savings
- Estimate accuracy improvements

### 5. Business Value Quantification
- Calculate time savings (hours freed per day)
- Calculate cost savings (labor cost reduction)
- Estimate operational improvements
- Calculate ROI projection

### 6. Process Change Impact Analysis
- Document to-be workflows
- Identify role changes for end users
- Define training requirements
- Create change management plan

### 7. Success Criteria Definition
- Define go-live success criteria
- Define 30-day success metrics
- Define 90-day success metrics
- Establish ongoing monitoring KPIs

## ROI Calculation Framework

### Time Savings Calculation
```
Annual Time Savings = (Hours Saved per Day) × (Days per Year) × (Number of End Users)
Annual Labor Cost Savings = Annual Time Savings × (Hourly Rate + Benefits)
```

### Operational Improvement Calculation
```
Improved Resource Utilization = (Reduction in Delays) × (Average Team Size) × (Hourly Resource Cost)
Improved Visibility Value = (Reduction in Escalations) × (Average Escalation Cost)
```

### Total ROI
```
Total Annual Benefit = Labor Cost Savings + Operational Improvements + Visibility Value
ROI % = (Total Annual Benefit - Implementation Cost) / Implementation Cost × 100
Payback Period = Implementation Cost / (Total Annual Benefit / 12)
```

## Expected Business Value Patterns

### Example Agent 1: Daily Status Check-In
- 80-90% reduction in manual check-in calls
- 2-3 hours/day time savings per coordinator
- >95% check-in completion rate
- <20 minute morning response window enforcement

### Example Agent 2: Bulk Communication
- 90% reduction in message distribution time
- 3-second response classification
- 5-second response delivery
- 100% consistent messaging across all teams
- 4-6 hours/event time savings per coordinator

### Example Agent 3: Location-Based Timeline Tracking
- 85% reduction in manual location check-in calls
- Intelligent check-in scheduling (distance-based)
- >85% ETA accuracy with confidence levels
- <30 minute delay detection
- 3-4 hours/day time savings per coordinator

### Example Agent 4: Completion Confirmation
- 85% reduction in manual confirmation calls
- >95% confirmation completion rate
- <30 minute non-responsive detection
- >90% timeline accuracy
- 2-3 hours/day time savings per coordinator

## Assessment Deliverables

1. Current State Process Map
2. Future State Process Map
3. KPI Baseline Report
4. KPI Target Report
5. Business Value Quantification
6. Change Impact Analysis
7. Success Criteria Document
8. Executive Presentation
9. Stakeholder Sign-Off

## Post-Implementation Value Tracking

### 30-Day Review
- Compare actual KPIs to baseline
- Identify early wins and challenges
- Adjust agent configuration if needed

### 90-Day Review
- Compare actual KPIs to targets
- Calculate realized ROI
- Document lessons learned
- Plan optimization opportunities

### Ongoing Monitoring
- Monthly KPI dashboard
- Quarterly business value review
- Annual ROI recalculation

## Success Factors

### Critical Success Factors
1. Executive Sponsorship: Leadership actively engaged
2. End User Participation: Frontline input on current processes
3. Data Availability: Access to historical performance data
4. Realistic Projections: Conservative estimates for business value
5. Change Management Focus: Early identification of training and adoption needs

### Risk Mitigation
1. Overpromising: Use conservative estimates, validate assumptions
2. Resistance to Change: Involve end users early, emphasize time savings
3. Data Quality: Establish baseline measurement process before go-live
4. Scope Creep: Document approved scope clearly, manage expectations

## KPI Dashboard Template

| KPI | Baseline | Target | Actual (30-day) | Actual (90-day) |
|-----|----------|--------|-----------------|-----------------|
| [Primary metric] | [Current] | [Goal] | TBD | TBD |
| [Completion rate] | [Current] | [Goal] | TBD | TBD |
| [Response time] | [Current] | [Goal] | TBD | TBD |
| [Time savings] | 0 | [Goal] | TBD | TBD |
| [Cost savings] | $0 | [Goal] | TBD | TBD |

## Conservative Estimation Principles

- Use lower bound of time savings ranges
- Account for learning curve and adoption period
- Include change management overhead
- Plan for 30-60 day ramp-up to full productivity
- Document all assumptions clearly
- Validate with historical data where possible
