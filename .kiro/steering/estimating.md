---
inclusion: manual
---

# Effort Estimation Guidelines

## Estimation Approach

Use a component-based estimation model with IBM Band levels defining resource costs and capabilities.

## AI-Assisted Development Impact

### Overview

AI coding assistants (Claude, GitHub Copilot, AWS CodeWhisperer) can significantly accelerate development, but productivity gains vary by task type. Use research-backed data to create dual estimation scenarios.

### Research-Backed Productivity Gains

**Source Data**:
- **AWS CodeWhisperer Study**: 57% faster task completion on average
- **Anthropic Claude Study**: 80% speedup on familiar tasks, 0% on learning new frameworks
- **GitHub Copilot Study**: 55% faster for boilerplate code

**Key Findings**:
1. AI excels at boilerplate/integration tasks (55% faster)
2. AI helps with familiar patterns (40% faster)
3. AI provides minimal benefit for learning new frameworks (0% faster)
4. AI has limited impact on complex validation logic (10% faster)
5. Quality trade-off: 17% lower comprehension scores (Anthropic research)

### Dual Estimation Approach

Create two scenarios for every agent:

**Conservative Scenario (Traditional Development)**:
- No AI coding assistance
- Historical velocity: 14 story points per week (6.75 FTE team)
- Use for stakeholder commitments and budget planning
- Timeline: 7.5 weeks for medium-complexity agent

**Aggressive Scenario (AI-Assisted Development)**:
- AI coding assistants used throughout
- Selective productivity gains by task category
- Effective velocity: 21 story points per week
- Timeline: 5.0 weeks for medium-complexity agent
- Savings: ~$94,000 (32%) and 2.5 weeks

### Task Categorization for AI Benefit

Categorize story points by AI benefit potential:

| Category | AI Benefit | Productivity Gain | Examples |
|----------|------------|-------------------|----------|
| **Boilerplate/Integration** | High | 55% faster | Salesforce API, Lambda setup, standard patterns |
| **Familiar Patterns** | Medium | 40% faster | Validation logic, CRUD operations, error handling |
| **Learning New Frameworks** | Low | 0% faster | Strands SDK, Bedrock AgentCore (new to team) |
| **Complex Validation** | Low | 10% faster | Multi-dimensional validation, business rules |

### Calculation Method

1. **Categorize Story Points**: Assign each requirement to a category
2. **Calculate Adjusted Backlog**: Apply productivity gains to each category
3. **Calculate Effective Velocity**: Determine adjusted story points per week
4. **Add Integration Buffer**: Round up for integration/testing overhead (35% contingency)

**Example**:
```
Original Backlog: 105 story points
- Boilerplate: 24 SP × 55% speedup = 13 SP saved
- Familiar: 32 SP × 40% speedup = 13 SP saved
- Learning New: 26 SP × 0% speedup = 0 SP saved
- Complex: 23 SP × 10% speedup = 2 SP saved

Adjusted Backlog: 77 effective story points (27% reduction)
Effective Velocity: 21 SP/week (vs. 14 SP/week baseline)
Timeline: 77 SP ÷ 21 SP/week = 3.7 weeks → 5.0 weeks (with buffer)
```

### Quality Mitigation Strategies

To address the 17% lower comprehension scores with AI assistance:

1. **Mandatory Code Review**: All AI-generated code reviewed by senior developers
2. **Property-Based Testing**: 100% coverage of correctness properties
3. **Senior Oversight**: Senior developers review junior developers' AI-assisted work
4. **Learning Curve**: Include 1-week ramp-up for AI tool proficiency

### Additional Costs for AI-Assisted Development

- AI Tool Licenses: $2,000 (Claude/CodeWhisperer subscriptions)
- Training: Included in 1-week ramp-up (no additional cost)

### Velocity Tracking and Validation

**Recommended Approach**:
1. Start with conservative timeline (7.5 weeks)
2. Track actual velocity from Week 1
3. Assess at Week 3 (40% of conservative timeline):
   - Velocity ≥18 SP/week → trending toward aggressive scenario
   - Velocity 14-17 SP/week → on track for conservative scenario
   - Velocity <14 SP/week → risk of overrun, escalate immediately
4. Update forecast at Week 3 based on actual data

### When to Use Each Scenario

**Use Conservative Scenario**:
- For stakeholder commitments and budget approvals
- When team is new to AI coding tools
- For risk-averse projects
- When quality is paramount over speed

**Use Aggressive Scenario**:
- For internal planning and resource optimization
- When team has AI coding experience
- For time-sensitive projects
- When cost savings are critical

**Recommended**: Plan for conservative, track for aggressive, update at Week 3.

---

## Standard Agent Estimation Template

### Base Agent Effort (Medium Complexity)
- Duration: 7.5 weeks
- Team Size: 6.75 FTEs
- Total Effort: ~51 person-weeks

### Complexity Adjustments

**Medium Complexity** (baseline):
- 7-8 custom tools
- 60-68 property-based tests
- Standard system of record integration
- Single workflow pattern
- Examples: Status check-in, confirmation workflows, standard notifications

**High Complexity** (+15-20% effort):
- 10+ custom tools
- Complex approval workflows
- Multi-format input handling
- External API integrations (geocoding, traffic, weather, etc.)
- Performance optimization requirements (<3s response)
- Examples: Bulk communication, complex timeline tracking

### Standard Team Composition Per Agent

| Role | Band | FTE | Responsibilities |
|------|------|-----|------------------|
| Technical Lead | 8 | 1.0 | Architecture, design, code review |
| Senior AI Engineer | 7 | 1.0 | Strands SDK, system prompts, LLM optimization |
| Senior Python Developer | 7 | 1.0 | Custom tools, complex business logic |
| Python Developer | 6 | 2.0 | Feature implementation, system integration |
| QA Engineer | 6 | 1.0 | Unit testing, property-based testing |
| DevOps Engineer | 7 | 0.5 | Deployment, CloudWatch, EventBridge |
| Technical Writer | 6 | 0.25 | Documentation |

Total: 6.75 FTEs

## Shared Infrastructure Estimation

**Duration**: 6 weeks  
**Team Size**: 8.5 FTEs  
**Effort**: ~51 person-weeks

Must complete before agent development begins.

Components:
- System integration client service
- Shared business logic services
- TimezoneHandler
- ValidationEngine
- ErrorHandler
- EscalationManager
- Lambda Layer deployment
- CI/CD pipeline

## Business Value Assessment

**Duration**: 2-3 days per agent  
**Team Size**: 2.5 FTEs  
**Effort**: ~7.5 person-days per agent

Can be parallelized across multiple agents.

## Project Overhead

### Core Leadership (Continuous)
- Engagement Partner (Band 10): 0.1 FTE
- Delivery Partner (Band 9): 0.5 FTE
- Project Manager (Band 8): 1.0 FTE
- Technical Architect (Band 9): 0.5 FTE
- AI/ML Practice Lead (Band 8): 0.25 FTE

Total: 2.35 FTEs across full project duration

### Cross-Functional Support
- QA Lead + Engineers: 2.0 FTEs average
- DevOps Lead + Engineers: 2.0 FTEs average

Total: 4.0 FTEs average

## Cost Estimation

### IBM Band Blended Rates (Indicative)

| Band | Role Level | Blended Rate ($/week) |
|------|-----------|----------------------|
| Band 10 | Executive Leadership | $8,000 |
| Band 9 | Senior Leadership | $6,500 |
| Band 8 | Management/Technical Lead | $5,000 |
| Band 7 | Senior Consultant | $4,000 |
| Band 6 | Consultant | $3,000 |

### Additional Cost Factors

- AWS infrastructure: ~$50K for full project
- Strands SDK licenses: ~$25K
- Training and onboarding: ~$30K
- Travel and expenses: ~$40K
- Contingency: 10% of labor costs

## Estimation Formula

```
Agent Effort = Base Effort × Complexity Factor
Total Agent Cost = (Effort by Band × Band Rate) + Overhead Allocation

Project Total = Shared Infrastructure + Sum(All Agents) + Core Leadership + Cross-Functional + Additional Costs
```

## Parallelization Strategy

- Maximum 2 agents in parallel development
- Peak staffing: ~20 FTEs (2 agent teams + leadership + cross-functional)
- Most complex agent developed solo (e.g., bulk communication with multi-channel support)

## Risk Buffers

- Add 10% contingency for schedule risk
- Add 15% for first-of-kind Strands SDK implementation
- Add 20% if property-based testing is new to team

## Estimation Validation

After completing first agent:
- Compare actual vs. estimated effort
- Adjust complexity factors for remaining agents
- Update team velocity assumptions
- Refine parallelization strategy
