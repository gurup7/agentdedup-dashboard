---
inclusion: manual
---

# Project Methodology - AI Agent Solutions
## End-to-End Delivery Framework

This steering file captures the comprehensive methodology for delivering AI agent solutions, from initial business case validation through implementation and deployment.

---

## Methodology Overview

The AI Agent Solution Delivery Framework follows a structured, phase-based approach that ensures business value, technical rigor, and successful implementation.

**Core Principles**:
1. **Business Value First**: Validate ROI before technical work begins
2. **Requirements-Driven**: Clear acceptance criteria guide all development
3. **Iterative Refinement**: Continuous validation with stakeholders
4. **Data-Driven Decisions**: Use actual data for estimates and projections
5. **Transparent Documentation**: Comprehensive artifacts for client review

---

## Phase 0: Business Value Assessment (2-3 Days)

### Objectives
- Quantify ROI and establish baseline KPIs
- Ensure stakeholder alignment before technical work
- Validate that AI automation delivers measurable value

### Activities

**Day 1: Discovery and Current State**
- Morning: Stakeholder interviews (end users, managers, executives)
- Afternoon: Process mapping and pain point documentation
- Evening: Data collection and baseline KPI calculation

**Day 2: Future State and Value Quantification**
- Morning: Future state workflow design with AI automation
- Afternoon: KPI projection and business value calculation
- Evening: Change impact analysis and success criteria definition

**Day 3: Reporting and Approval**
- Morning: Business value assessment report preparation
- Afternoon: Executive presentation and Q&A
- Evening: Stakeholder sign-off and scope approval

### Deliverables
1. Current State Process Map
2. Future State Process Map
3. KPI Baseline Report
4. KPI Target Report
5. Business Value Quantification (ROI, payback period)
6. Change Impact Analysis
7. Success Criteria Document
8. Executive Presentation
9. Stakeholder Sign-Off

### Key Metrics to Capture
- Time savings (hours freed per day/week/month)
- Labor cost savings (fully loaded hourly rate × time saved)
- Operational improvements (reduced delays, improved accuracy)
- Scalability benefits (handle more volume with same resources)
- Quality improvements (consistency, compliance, audit trail)

### Conservative Estimation Principles
- Use lower bound of time savings ranges
- Account for learning curve and adoption period (30-60 days)
- Include change management overhead
- Document all assumptions clearly
- Validate with historical data where possible

---

## Phase 1: Requirements Decomposition

### Objectives
- Break down high-level business needs into detailed requirements
- Create user stories with clear acceptance criteria
- Establish traceability from business value to technical implementation

### Activities

**1. Stakeholder Identification**
- Primary users (who will interact with agents)
- Secondary users (who will benefit indirectly)
- System administrators (who will manage the solution)
- Approvers (who need visibility and control)

**2. Use Case Identification**
- Map business processes to potential AI agents
- Prioritize use cases by business value and complexity
- Define agent boundaries and responsibilities
- Identify inter-agent dependencies

**3. User Story Generation**
- Write user stories in standard format: "As a [role], I want [capability], so that [benefit]"
- Include acceptance criteria for each story
- Estimate story points or complexity
- Group stories by agent or feature

**4. Requirements Traceability**
- Link user stories to business value metrics
- Create traceability matrix (business need → requirement → user story → task)
- Document assumptions and constraints
- Identify risks and dependencies

### Deliverables
1. Stakeholder Map
2. Use Case Catalog (with prioritization)
3. User Story Backlog (with acceptance criteria)
4. Requirements Traceability Matrix
5. Assumptions and Constraints Document

### Best Practices
- Involve actual end users in user story validation
- Use concrete examples and scenarios
- Define "done" criteria for each story
- Avoid technical implementation details in requirements
- Focus on "what" and "why", not "how"

---

## Phase 2: Architecture Design

### Objectives
- Design scalable, cost-efficient architecture
- Select appropriate AWS services with clear rationale
- Document architecture decisions and alternatives considered

### Activities

**1. Architecture Principles Definition**
- Serverless-first (pay-per-use, auto-scaling)
- Event-driven (responsive, loosely coupled)
- AI-powered (foundation models for intelligence)
- Security-first (encryption, least privilege, audit)
- Cost-optimized (minimize fixed costs, optimize variable costs)

**2. AWS Service Selection**
For each service, document:
- **Role**: What problem does this service solve?
- **Why This Service**: Key benefits and capabilities
- **Alternatives Considered**: What else was evaluated and why not chosen
- **Cost Model**: Fixed vs. variable costs
- **Performance Characteristics**: Latency, throughput, scalability

**3. Architecture Patterns**
- Event-driven architecture (EventBridge, Step Functions)
- Shared infrastructure layer (Lambda Layers, shared services)
- Multi-channel communication gateway (SNS, SES, Connect, Pinpoint)
- System of record integration (external APIs, databases)

**4. Architecture Documentation**
Create comprehensive architecture document including:
- Executive summary with key principles
- Service catalog (13+ services with detailed rationale)
- Architecture patterns and design decisions
- Performance requirements and SLAs
- Security and compliance considerations
- Scalability and reliability strategies
- Cost optimization opportunities
- Monitoring and alerting strategy
- Future enhancement roadmap

### Deliverables
1. Architecture Overview Diagram
2. AWS Services Architecture Document (comprehensive)
3. Service Selection Rationale (per service)
4. Architecture Decision Records (ADRs)
5. Performance Requirements Matrix
6. Security and Compliance Plan

### Best Practices
- Document "why" for every architecture decision
- Consider alternatives and explain trade-offs
- Include cost implications in service selection
- Design for observability from day one
- Plan for future enhancements and scalability

---

## Phase 3: Effort Estimation

### Objectives
- Provide accurate effort estimates for implementation
- Identify resource requirements and skill gaps
- Establish realistic timeline and budget

### Activities

**1. Component-Based Estimation**
Break down work into estimable components:
- Shared infrastructure (foundational services)
- Individual agents (per-agent effort)
- Integration work (system of record, external APIs)
- Testing and quality assurance
- Documentation and training
- Deployment and operations setup

**2. Standard Agent Estimation Template**
Define baseline effort for "medium complexity" agent:
- Duration: 7.5 weeks
- Team Size: 6.75 FTEs
- Total Effort: ~51 person-weeks

Adjust for complexity:
- **Low Complexity** (-15%): Simple workflows, few tools, standard integrations
- **Medium Complexity** (baseline): 7-8 custom tools, 60-68 property-based tests
- **High Complexity** (+15-20%): 10+ tools, complex workflows, external API integrations

**3. Team Composition**
Define standard team structure with IBM Band levels:
- Technical Lead (Band 8): 1.0 FTE
- Senior AI Engineer (Band 7): 1.0 FTE
- Senior Python Developer (Band 7): 1.0 FTE
- Python Developers (Band 6): 2.0 FTE
- QA Engineer (Band 6): 1.0 FTE
- DevOps Engineer (Band 7): 0.5 FTE
- Technical Writer (Band 6): 0.25 FTE

**4. Core Leadership Overhead**
Account for continuous leadership across project:
- Engagement Partner (Band 10): 0.1 FTE
- Delivery Partner (Band 9): 0.5 FTE
- Project Manager (Band 8): 1.0 FTE
- Technical Architect (Band 9): 0.5 FTE
- Practice Lead (Band 8): 0.25 FTE

**5. Parallelization Strategy**
- Maximum 2 agents in parallel development
- Shared infrastructure must complete first
- Most complex agent developed solo
- Peak staffing: ~20 FTEs (2 agent teams + leadership + cross-functional)

### Deliverables
1. Effort Estimation Spreadsheet (by component, by agent)
2. Resource Plan (roles, FTEs, duration)
3. Project Timeline (Gantt chart with dependencies)
4. Budget Estimate (labor + AWS + other costs)
5. Risk-Adjusted Estimates (with contingency)

### Best Practices
- Use historical data from similar projects
- Include buffer for unknowns (10-20%)
- Validate estimates after first agent completion
- Account for learning curve on new technologies
- Include time for testing, documentation, deployment

---

## Phase 4: AWS Pricing Analysis

### Objectives
- Provide accurate AWS cost estimates
- Distinguish fixed vs. variable costs
- Identify cost optimization opportunities

### Activities

**1. Service Inventory**
List all AWS services with:
- Service name and purpose
- Usage pattern (always-on vs. event-driven)
- Cost model (fixed, variable, or hybrid)
- Pricing source (AWS Price List API)

**2. Fixed Cost Analysis**
Identify services with always-on costs:
- CloudWatch (metrics, alarms, dashboards)
- Secrets Manager (credential storage)
- DynamoDB (storage for configuration)
- S3 (deployment artifacts, logs)

Document assumptions for each:
- Number of metrics, alarms, secrets
- Storage volume and retention period
- Why these costs are necessary (system readiness)

**3. Variable Cost Analysis**
Identify services with usage-based costs:
- Bedrock (AI inference per interaction)
- Lambda (compute per execution)
- SNS (SMS per message)
- SES (email per message)
- Connect (voice per minute)
- Pinpoint (push notification per message)
- DynamoDB (read/write operations)
- Step Functions (state transitions)
- EventBridge (events)

Document cost drivers:
- Interactions per event/period
- Event frequency per year
- User count and event duration

**4. Scenario Modeling**
Create three scenarios:
- **Low**: Minimal activity (e.g., 2 events/year, 50 users, 5 days)
- **Anticipated**: Normal operations (e.g., 3-4 events/year, 100 users, 7 days)
- **High**: Active season (e.g., 4-5 events/year, 150 users, 10 days)

Calculate costs for each scenario:
- Monthly cost (averaged across year)
- Annual cost
- Cost per event
- Cost per interaction

**5. Cost Optimization Opportunities**
Identify immediate, medium-term, and long-term optimizations:
- **Immediate** (0-3 months): CloudWatch metrics reduction, SMS to push migration
- **Medium-term** (3-6 months): Model selection (Nova vs. Claude), prompt caching
- **Long-term** (6-12 months): Reserved capacity, Savings Plans, PPAs

**6. Pricing Validation**
- Source: AWS Price List API (official pricing)
- Effective dates: Document when pricing was retrieved
- Validation frequency: Monthly during project, quarterly post-launch
- Disclaimer: Note that Private Pricing Agreements (PPAs) and credits not included

### Deliverables
1. AWS Pricing Summary Document
2. Fixed vs. Variable Cost Breakdown
3. Scenario Cost Models (Low, Anticipated, High)
4. Cost Optimization Roadmap
5. Pricing Assumptions Document
6. Pricing Validation Plan

### Best Practices
- Use AWS Price List API for accurate pricing
- Document effective dates for all pricing data
- Clearly separate fixed vs. variable costs
- Include disclaimer about PPAs and credits
- Provide cost optimization recommendations
- Validate pricing quarterly

---

## Phase 5: Business Case Development

### Objectives
- Quantify ROI with accurate cost and benefit data
- Calculate payback period and break-even analysis
- Provide sensitivity analysis for key variables

### Activities

**1. Cost Aggregation**
Combine all cost components:
- Implementation cost (labor + AWS infrastructure + licenses + training + travel + contingency)
- Annual AWS consumption cost (from pricing analysis)
- Ongoing support and maintenance cost

**2. Benefit Quantification**
Calculate annual benefits:
- Labor cost savings (time freed × hourly rate × frequency)
- Operational improvements (reduced delays, improved accuracy)
- Scalability benefits (handle more volume without adding staff)

**Alternative Approach: Placeholder Template**

When business value data is not immediately available (e.g., specs created before stakeholder interviews):

1. **Create Business Case Template**
   - Use comprehensive template with [PLACEHOLDER] markers
   - Include all ROI calculation formulas and frameworks
   - Provide example calculations for reference
   - Document required data sources and validation status

2. **Benefits of Placeholder Approach**
   - Shows stakeholders complete ROI framework upfront
   - Identifies exactly what data is needed
   - Can be filled in incrementally as data becomes available
   - Provides example values to guide data collection
   - Maintains project momentum while awaiting data

3. **Data Collection Plan**
   - List specific metrics needed (hours/week, hourly rate, cycles/year)
   - Identify data sources (stakeholder interviews, timesheets, system of record)
   - Schedule stakeholder interviews and data gathering sessions
   - Track validation status (❌ Not validated → ✅ Validated)

4. **Incremental Updates**
   - Update business case as data becomes available
   - Recalculate ROI with actual values
   - Validate assumptions with stakeholders
   - Document changes and rationale

**3. ROI Calculation**
- Net annual benefit = Annual benefits - Annual AWS costs
- ROI % = (Net annual benefit - Implementation cost) / Implementation cost × 100
- Payback period = Implementation cost / Net annual benefit

**4. Sensitivity Analysis**
Test impact of key variables:
- AI absorption rate (% of interactions handled by AI)
- Labor cost per hour
- Event frequency per year
- Event duration (days per event)
- Interactions per hour
- AI cost per interaction

**5. Risk-Adjusted ROI**
Account for risks:
- Adoption risk (users resist AI)
- Technical risk (performance issues)
- Frequency risk (fewer events than anticipated)

Calculate expected value with probability-weighted scenarios.

**6. Break-Even Analysis**
- Break-even AI absorption rate
- Break-even event frequency
- Break-even labor cost

### Deliverables
1. Business Case Model Document
2. ROI Calculation Spreadsheet
3. Sensitivity Analysis Charts
4. Risk-Adjusted ROI Model
5. Break-Even Analysis
6. Executive Summary (1-page)

### Best Practices
- Use conservative estimates for benefits
- Include risk-adjusted scenarios
- Document all assumptions clearly
- Provide sensitivity analysis for key variables
- Compare to alternative solutions (status quo, manual process, other vendors)
- Include non-financial benefits (quality, scalability, compliance)

---

## Phase 6: Documentation Standards

### Objectives
- Create comprehensive, client-ready documentation
- Ensure traceability and transparency
- Enable future maintenance and enhancements

### Documentation Hierarchy

**1. Business Documentation**
- Business Case Model (ROI, payback, sensitivity)
- Business Value Assessment (baseline KPIs, targets)
- Project Assumptions (traceability matrix)

**2. Architecture Documentation**
- AWS Services Architecture (comprehensive service catalog)
- Architecture diagrams (high-level, detailed)
- Architecture Decision Records (ADRs)

**3. Pricing Documentation**
- AWS Pricing Summary (fixed vs. variable costs)
- Pricing Calculator Inputs (detailed assumptions)
- Pricing Validation Plan

**4. Staffing Documentation**
- Staffing Plan (roles, FTEs, timeline)
- Resource Allocation (weekly breakdown)
- Skills Matrix (required vs. available)

**5. Working Notes**
- Design updates and decisions
- Status tracking and progress reports
- Lessons learned and retrospectives

### Documentation Best Practices

**Clarity and Transparency**
- Use clear, concise language (avoid jargon)
- Document "why" for every decision
- Include alternatives considered
- Provide examples and scenarios

**Traceability**
- Link business value → requirements → design → tasks
- Reference source documents (AWS Price List API, system of record documentation)
- Include effective dates and version numbers

**Assumptions and Disclaimers**
- Document all assumptions clearly
- Include disclaimers (e.g., PPAs not included in pricing)
- Note validation frequency and next review dates

**Visual Aids**
- Use tables for comparisons and summaries
- Include diagrams for architecture and workflows
- Provide charts for sensitivity analysis

**Version Control**
- Document version, date, and author
- Track changes and approvals
- Schedule regular reviews and updates

---

## Phase 7: Delivery Schedule

### Objectives
- Create realistic, achievable project timeline
- Identify dependencies and critical path
- Plan for parallelization and resource optimization

### Activities

**1. Phase Definition**
- Phase 0: Business Value Assessment (2-3 days)
- Phase 1: Shared Infrastructure (6 weeks)
- Phase 2-4: Agent Development (waves of 2 agents in parallel)
- Phase 5: Integration & Optimization (4 weeks)

**2. Dependency Mapping**
- Shared infrastructure must complete before agent development
- Agents can be developed in parallel (max 2 at a time)
- Most complex agent developed solo
- Integration testing requires all agents complete

**3. Resource Leveling**
- Peak staffing: ~20 FTEs (2 agent teams + leadership + cross-functional)
- Minimum staffing: ~5 FTEs (shared infrastructure phase)
- Average staffing: ~12-15 FTEs across project

**4. Milestone Definition**
- Phase 0 Complete: Business case approved
- Phase 1 Complete: Shared infrastructure deployed
- Agent Wave 1 Complete: First 2 agents in production
- Agent Wave 2 Complete: Next 2 agents in production
- Agent Wave 3 Complete: Final agents in production
- Phase 5 Complete: Full system integrated and optimized

### Deliverables
1. Project Timeline (Gantt chart)
2. Resource Allocation Plan (by week)
3. Dependency Map
4. Milestone Schedule
5. Risk Mitigation Plan

### Best Practices
- Build in buffer time (10-20% contingency)
- Plan for learning curve on new technologies
- Allow time for testing and validation
- Schedule regular stakeholder reviews
- Plan for holidays and team availability

---

## Phase 8: Continuous Validation

### Objectives
- Validate assumptions throughout project
- Adjust estimates based on actual data
- Ensure alignment with business value

### Activities

**1. After First Agent Completion**
- Compare actual vs. estimated effort
- Validate AI absorption rate assumptions
- Adjust complexity factors for remaining agents
- Update business case if material changes

**2. Monthly Reviews**
- Track actual AWS costs vs. estimates
- Monitor KPIs and business value realization
- Identify issues and risks early
- Adjust plans as needed

**3. Post-Implementation Reviews**
- 30-day review: Compare actual KPIs to baseline
- 90-day review: Compare actual KPIs to targets
- Annual review: Recalculate ROI with actual data

### Deliverables
1. Variance Reports (actual vs. estimated)
2. Lessons Learned Documents
3. Updated Business Case (with actual data)
4. Recommendations for Future Projects

---

## Key Success Factors

1. **Executive Sponsorship**: Active engagement from leadership
2. **User Involvement**: Frontline users participate in requirements and testing
3. **Data-Driven Decisions**: Use actual data for estimates and projections
4. **Transparent Communication**: Regular updates with stakeholders
5. **Iterative Refinement**: Continuous validation and adjustment
6. **Change Management**: Plan for adoption and training
7. **Risk Management**: Identify and mitigate risks proactively
8. **Quality Focus**: Property-based testing and comprehensive validation

---

## Common Pitfalls to Avoid

1. **Overpromising ROI**: Use conservative estimates, validate assumptions
2. **Underestimating Complexity**: Account for learning curve and unknowns
3. **Ignoring Change Management**: Plan for user adoption and training
4. **Skipping Business Value Assessment**: Validate ROI before technical work
5. **Poor Documentation**: Comprehensive docs enable future maintenance
6. **Inadequate Testing**: Property-based testing catches edge cases
7. **Cost Surprises**: Distinguish fixed vs. variable costs, monitor actual usage
8. **Scope Creep**: Document approved scope, manage expectations

---

## Checklist: Project Readiness

Before starting implementation, ensure:

- [ ] Business value assessment complete and approved
- [ ] ROI and payback period validated with stakeholders
- [ ] Requirements decomposed into user stories with acceptance criteria
- [ ] Architecture designed with clear service selection rationale
- [ ] Effort estimates validated with historical data
- [ ] AWS pricing analysis complete with fixed vs. variable breakdown
- [ ] Business case model complete with sensitivity analysis
- [ ] Delivery schedule created with dependencies mapped
- [ ] Resource plan approved with skills validated
- [ ] Documentation standards established
- [ ] Stakeholder sign-off obtained
- [ ] Project kickoff scheduled

---

**Document Owner**: IBM Consulting - AI Agent Practice  
**Last Updated**: February 2026  
**Next Review**: Quarterly (or after each major project completion)

---

**END OF DOCUMENT**
