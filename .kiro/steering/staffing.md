---
inclusion: manual
---

# Staffing Guidelines

## IBM Band Level Definitions

### Band 10 - Executive Leadership
- Role: Executive Sponsor, Engagement Partner
- Allocation: 5-10%
- Responsibilities: Client relationship, strategic direction, executive stakeholder management

### Band 9 - Senior Leadership
- Role: Delivery Partner, Technical Architect
- Allocation: 25-50%
- Responsibilities: Overall delivery accountability, architecture decisions, risk management

### Band 8 - Management
- Role: Project Manager, Technical Lead, Practice Lead
- Allocation: 75-100%
- Responsibilities: Day-to-day delivery, team management, technical leadership

### Band 7 - Senior Consultant
- Role: Senior Developer, Senior AI Engineer, Senior Cloud Architect
- Allocation: 100%
- Responsibilities: Complex technical implementation, mentoring, design decisions

### Band 6 - Consultant
- Role: Developer, AI Engineer, Cloud Engineer, QA Engineer
- Allocation: 100%
- Responsibilities: Feature implementation, testing, documentation

### Band 5 - Associate Consultant
- Role: Junior Developer, Junior AI Engineer, QA Analyst
- Allocation: 100%
- Responsibilities: Implementation support, testing, documentation

## Critical Skills Requirements

### Must-Have Skills (Band 7-8)
- Strands Agents SDK (Python)
- AWS Bedrock AgentCore
- Property-based testing (fast-check, Hypothesis)
- System of record REST API integration
- AWS Lambda, EventBridge, CloudWatch
- LLM prompt engineering
- System design and architecture

### Important Skills (Band 6-7)
- Python (intermediate to advanced)
- AWS services (SNS, SES, DynamoDB, S3)
- REST API design and integration
- Unit testing (pytest)
- CI/CD pipelines
- Git workflow

### Nice-to-Have Skills
- Geocoding APIs (Google Maps, HERE)
- Traffic and weather data integration
- Infrastructure as Code (Terraform, CloudFormation)
- Performance optimization
- Security best practices

## Staffing Phases

### Phase 0: Business Value Assessment (Weeks 1-3)
- Team Size: 2.5 FTEs + Core Leadership (2.35 FTEs)
- Total: 4.85 FTEs
- Focus: Stakeholder interviews, process mapping, KPI analysis, ROI calculations

### Phase 1: Shared Infrastructure (Weeks 4-9)
- Team Size: 8.5 FTEs + Core Leadership (2.35 FTEs) + Cross-Functional (2.0 FTEs)
- Total: 12.85 FTEs
- Focus: Core services development, Lambda Layer, CI/CD pipeline

### Phase 2-4: Agent Development Waves
- Wave 1-2 (Parallel): 2 agent teams (13.5 FTEs) + Leadership (2.35 FTEs) + Cross-Functional (4.0 FTEs)
- Total: 19.85 FTEs (peak staffing)
- Wave 3 (Single): 1 agent team (6.75 FTEs) + Leadership (2.35 FTEs) + Cross-Functional (3.0 FTEs)
- Total: 12.1 FTEs

### Phase 5: Integration & Optimization
- Team Size: Core Leadership (2.35 FTEs) + Cross-Functional (4.0 FTEs) + Selected developers (3.0 FTEs)
- Total: 9.35 FTEs

## Recruitment Timeline

### Pre-Project (Weeks -4 to -1)
- Identify and recruit core team (Bands 8-9)
- Identify and recruit shared infrastructure team (Bands 6-7)
- Conduct technical interviews
- Secure team commitments

### Week 1
- Onboard core leadership team
- Onboard business value assessment team
- Project kickoff

### Weeks 2-3
- Onboard shared infrastructure team
- Technical training (Strands SDK, Bedrock AgentCore)

### Weeks 8-9
- Onboard agent development teams (Wave 1)
- Agent-specific training

## Onboarding Requirements

### All Team Members
- IBM security clearance
- Client access credentials
- AWS account access
- System of record sandbox/test access
- Strands Agents SDK training (2 days)
- AWS Bedrock AgentCore training (1 day)

### Developers (Bands 6-7)
- Python development environment setup
- Property-based testing training (1 day)
- System of record API training (1 day)
- Git workflow training

### QA Engineers
- Property-based testing deep dive (2 days)
- Test automation framework training

## Staffing Risks and Mitigation

### Risk: Strands SDK Expertise Shortage
- Mitigation: Early training program, pair programming, knowledge sharing
- Contingency: Engage Strands SDK experts as advisors

### Risk: Property-Based Testing Experience Gap
- Mitigation: Dedicated training, QA Lead with PBT expertise, code review
- Contingency: Bring in external PBT consultant for 4-6 weeks

### Risk: Peak Staffing Demand
- Mitigation: Early recruitment, flexible resource pool, cross-training
- Contingency: Extend timeline, reduce parallelization

### Risk: Key Person Dependency
- Mitigation: Knowledge sharing, documentation, pair programming, backup resources
- Contingency: Rapid backfill process, knowledge transfer sessions

### Risk: System Integration Complexity
- Mitigation: Integration architect on team, early integration testing
- Contingency: Engage system integration specialist consultant

## Team Performance KPIs

### Delivery Metrics
- On-time delivery: >95% of milestones
- Budget adherence: Within 10% of estimate
- Quality: <5% defect rate in production

### Technical Metrics
- Code coverage: >80%
- Property-based test coverage: 100% of properties
- Performance SLAs: 100% met

### Team Metrics
- Team satisfaction: >4.0/5.0
- Knowledge transfer: 100% of critical knowledge documented
- Client satisfaction: >4.5/5.0

## Cross-Training Strategy

- Pair programming for knowledge sharing
- Weekly technical deep-dives
- Documentation as code
- Rotation of team members across agents
- Backup resources for critical roles
