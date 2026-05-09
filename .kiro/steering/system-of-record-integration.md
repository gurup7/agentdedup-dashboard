---
inclusion: manual
---

# System of Record Integration Guidelines

## Overview

AI agent solutions require integration with an organization's system of record (SOR) to serve as the single source of truth for operational data. This steering file provides guidance on selecting, integrating with, and optimizing system of record integrations for AI agent projects.

---

## Core Principles

1. **Single Source of Truth**: The system of record is the authoritative source for all operational data
2. **Real-Time Synchronization**: Agents read and write data in real-time via APIs
3. **No Data Duplication**: Agents do not maintain local copies of operational data
4. **Audit Trail**: All agent interactions are logged back to the system of record
5. **API-First Integration**: Use REST APIs or GraphQL for all data access

---

## Common Systems of Record

### Salesforce

**Best For**: Field service management, customer relationship management, case management

**Integration Approach**:
- **API**: Salesforce REST API or SOAP API
- **Authentication**: OAuth 2.0 with refresh tokens
- **Data Model**: Standard objects (Account, Contact, Case) + Custom objects
- **Notes/Updates**: Salesforce Notes API or Chatter API for Team Page updates
- **Rate Limits**: 15,000-100,000 API calls/day depending on license tier

**Key Considerations**:
- Verify API call limits are sufficient for agent interaction volumes
- Use bulk APIs for batch operations to conserve API calls
- Implement connection pooling and retry logic for reliability
- Store OAuth tokens in AWS Secrets Manager with automatic rotation

**Cost Implications**:
- Salesforce API usage typically covered under existing license
- Validate with Salesforce account team that license tier includes sufficient API calls
- No per-call API costs in most Salesforce licenses

**Example Use Case - Field Service Coordination**: Salesforce stores crew information, assignments, events, lodging, and operational updates. Agents read from and write to Salesforce via REST APIs for real-time coordination.

---

### ServiceNow

**Best For**: IT service management, incident management, change management, asset management

**Integration Approach**:
- **API**: ServiceNow REST API (Table API, Aggregate API, Import Set API)
- **Authentication**: OAuth 2.0 or Basic Authentication
- **Data Model**: Tables (incident, change_request, cmdb_ci) + Custom tables
- **Notes/Updates**: Work Notes or Additional Comments fields
- **Rate Limits**: Varies by instance size and license

**Key Considerations**:
- Use Table API for CRUD operations on records
- Use Aggregate API for reporting and analytics
- Implement rate limiting and exponential backoff
- Consider ServiceNow Integration Hub for complex workflows

**Cost Implications**:
- ServiceNow API usage typically covered under existing license
- Some advanced APIs may require additional licensing
- Validate API access with ServiceNow account team

**Example Use Case - IT Service Management**: ServiceNow stores incidents, requests, assets, and knowledge articles. Agents automate ticket triage, password resets, and software provisioning via REST APIs.

---

### SAP

**Best For**: Enterprise resource planning (ERP), supply chain management, financial management, human capital management (HCM)

**Integration Approach**:
- **API**: SAP OData services, SAP Gateway, or SAP Cloud Platform APIs
- **Authentication**: OAuth 2.0, SAML, or Basic Authentication
- **Data Model**: SAP business objects (Material, Customer, Sales Order, Employee, Payroll)
- **Notes/Updates**: SAP Notes or custom fields
- **Rate Limits**: Varies by SAP system and configuration

**Key Considerations**:
- SAP integration can be complex due to legacy systems
- Consider using SAP Cloud Platform Integration (CPI) as middleware
- Implement robust error handling for SAP system downtime
- Work with SAP Basis team for API access and credentials
- For HR use cases, integrate with SAP ECC (payroll) and SuccessFactors (HCM, LMS)

**Cost Implications**:
- SAP API access may require additional licensing
- SAP Cloud Platform Integration has separate licensing costs
- Validate costs with SAP account team before implementation

**Example Use Case - HR Service Delivery**: SAP ECC stores payroll and direct deposit data, SuccessFactors stores employee records and learning content. Agents enable conversational access to HR services via OData APIs.

---

### Microsoft Dynamics 365

**Best For**: Customer relationship management, field service, sales automation

**Integration Approach**:
- **API**: Dynamics 365 Web API (OData v4)
- **Authentication**: Azure AD OAuth 2.0
- **Data Model**: Entities (account, contact, incident) + Custom entities
- **Notes/Updates**: Notes entity or Timeline
- **Rate Limits**: Service protection limits (6,000 requests per 5 minutes per user)

**Key Considerations**:
- Use Azure AD for authentication and authorization
- Implement retry logic for service protection limit errors
- Use batch requests to optimize API usage
- Consider Power Automate for complex workflows

**Cost Implications**:
- Dynamics 365 API usage typically covered under existing license
- Validate API limits with Microsoft account team
- Azure AD authentication may require Azure subscription

---

### Custom/Proprietary Systems

**Best For**: Legacy systems, custom-built applications, industry-specific platforms

**Integration Approach**:
- **API**: REST API, SOAP API, or custom protocol
- **Authentication**: Varies (API keys, OAuth, SAML, custom)
- **Data Model**: Custom schema
- **Notes/Updates**: Custom fields or tables
- **Rate Limits**: Varies by system

**Key Considerations**:
- Document API endpoints, authentication, and data models thoroughly
- Implement comprehensive error handling for undocumented edge cases
- Plan for API versioning and backward compatibility
- Consider building an integration layer (API Gateway) for abstraction

**Cost Implications**:
- Varies widely depending on system
- May require custom development or middleware
- Validate API access and costs with system owner

---

## Integration Architecture Patterns

### Pattern 1: Direct API Integration

**Description**: Agents call system of record APIs directly from Lambda functions

**When to Use**:
- Simple CRUD operations
- Low latency requirements (<1 second)
- System of record has reliable, well-documented APIs

**Pros**:
- Simple architecture
- Low latency
- No additional infrastructure

**Cons**:
- Tight coupling between agents and system of record
- Difficult to switch systems of record
- No caching or optimization layer

**Implementation**:
```python
# Lambda function calls Salesforce API directly
import requests

def get_crew_info(crew_id):
    response = requests.get(
        f"https://instance.salesforce.com/services/data/v58.0/sobjects/Crew__c/{crew_id}",
        headers={"Authorization": f"Bearer {oauth_token}"}
    )
    return response.json()
```

---

### Pattern 2: Integration Layer (API Gateway)

**Description**: Agents call a shared integration service that abstracts system of record APIs

**When to Use**:
- Multiple agents accessing same system of record
- Need for caching, rate limiting, or retry logic
- Potential to switch systems of record in future

**Pros**:
- Loose coupling between agents and system of record
- Centralized caching, rate limiting, and error handling
- Easier to switch systems of record

**Cons**:
- Additional infrastructure and complexity
- Slightly higher latency
- Requires maintenance of integration layer

**Implementation**:
```python
# Shared integration service (Lambda Layer or separate service)
class SystemOfRecordClient:
    def __init__(self, system_type):
        self.system_type = system_type
        self.client = self._get_client()
    
    def get_crew_info(self, crew_id):
        if self.system_type == "salesforce":
            return self._salesforce_get_crew(crew_id)
        elif self.system_type == "servicenow":
            return self._servicenow_get_crew(crew_id)
        # ... other systems
    
    def _salesforce_get_crew(self, crew_id):
        # Salesforce-specific implementation
        pass
```

---

### Pattern 3: Event-Driven Integration

**Description**: System of record publishes events to EventBridge, agents subscribe to relevant events

**When to Use**:
- Need for real-time notifications of data changes
- System of record supports webhooks or event publishing
- Multiple agents need to react to same events

**Pros**:
- Real-time data synchronization
- Decoupled architecture
- Scalable to many agents

**Cons**:
- Requires system of record to support event publishing
- More complex architecture
- Potential for event delivery delays

**Implementation**:
```python
# EventBridge rule triggers Lambda when Salesforce publishes event
def handle_crew_update_event(event, context):
    crew_id = event['detail']['crew_id']
    # Agent reacts to crew update
    update_agent_state(crew_id)
```

---

## API Integration Best Practices

### Authentication and Security

1. **Use OAuth 2.0** for authentication when available
2. **Store credentials in AWS Secrets Manager** with automatic rotation
3. **Implement least privilege access** - only request necessary permissions
4. **Use HTTPS** for all API calls
5. **Validate SSL certificates** to prevent man-in-the-middle attacks

### Rate Limiting and Throttling

1. **Understand system of record rate limits** before implementation
2. **Implement exponential backoff** for rate limit errors
3. **Use connection pooling** to reuse HTTP connections
4. **Batch requests** when possible to conserve API calls
5. **Monitor API usage** with CloudWatch metrics

### Error Handling and Resilience

1. **Implement retry logic** with exponential backoff for transient errors
2. **Handle rate limit errors** gracefully (HTTP 429)
3. **Log all API errors** to CloudWatch for debugging
4. **Implement circuit breaker pattern** for system of record downtime
5. **Provide fallback responses** when system of record is unavailable

### Performance Optimization

1. **Cache frequently accessed data** in DynamoDB or ElastiCache
2. **Use bulk APIs** for batch operations
3. **Implement connection pooling** to reduce connection overhead
4. **Minimize API calls** by fetching only necessary fields
5. **Use pagination** for large result sets

### Data Consistency

1. **Read from system of record** for every agent interaction (no stale data)
2. **Write back to system of record** immediately after agent actions
3. **Use transactions** when available for multi-step operations
4. **Implement idempotency** for write operations
5. **Log all data changes** to system of record for audit trail

---

## Cost Considerations

### API Call Costs

Most enterprise systems of record (Salesforce, ServiceNow, SAP) include API access in the base license, but with limits:

| System | Typical API Limit | Overage Cost | Notes |
|--------|-------------------|--------------|-------|
| **Salesforce** | 15K-100K calls/day | Varies by license | Validate with account team |
| **ServiceNow** | Varies by instance | Varies by license | Validate with account team |
| **SAP** | Varies by system | Varies by license | May require additional licensing |
| **Dynamics 365** | 6K calls per 5 min/user | Included in license | Service protection limits |

### Optimization Strategies

1. **Use bulk APIs** to reduce API call count (e.g., Salesforce Bulk API)
2. **Cache reference data** (crew rosters, lodging assignments) in DynamoDB
3. **Batch write operations** to minimize API calls
4. **Monitor API usage** and optimize high-volume operations
5. **Negotiate higher API limits** with system of record vendor if needed

---

## System of Record Selection Criteria

When selecting a system of record for an AI agent solution, consider:

### Technical Criteria

- [ ] **API Availability**: Does the system have well-documented REST or GraphQL APIs?
- [ ] **API Rate Limits**: Are API limits sufficient for projected agent interaction volumes?
- [ ] **Authentication**: Does the system support OAuth 2.0 or other secure authentication?
- [ ] **Data Model**: Is the data model flexible enough to support agent use cases?
- [ ] **Real-Time Access**: Can agents read and write data in real-time (<1 second latency)?
- [ ] **Audit Trail**: Can all agent interactions be logged back to the system?

### Business Criteria

- [ ] **Existing License**: Does the organization already have a license for this system?
- [ ] **API Costs**: Are API calls included in the license or charged separately?
- [ ] **Vendor Support**: Does the vendor provide support for API integration?
- [ ] **Data Ownership**: Does the organization own the data in the system?
- [ ] **Compliance**: Does the system meet regulatory and compliance requirements?

### Operational Criteria

- [ ] **Reliability**: What is the system's uptime SLA?
- [ ] **Performance**: What is the typical API response time?
- [ ] **Scalability**: Can the system handle projected agent interaction volumes?
- [ ] **Maintenance Windows**: Are there scheduled maintenance windows that would impact agents?
- [ ] **Support**: Is there 24/7 support available for API issues?

---

## Migration and Transition

### Switching Systems of Record

If migrating from one system of record to another:

1. **Use Integration Layer Pattern** to abstract system of record APIs
2. **Implement dual-write** during transition period (write to both systems)
3. **Validate data consistency** between old and new systems
4. **Test agents thoroughly** with new system before cutover
5. **Plan for rollback** in case of issues

### Data Migration

1. **Export data** from old system of record
2. **Transform data** to match new system's data model
3. **Import data** to new system of record
4. **Validate data integrity** after migration
5. **Update agent configurations** to point to new system

---

## Troubleshooting Common Issues

### Issue: API Rate Limit Exceeded

**Symptoms**: HTTP 429 errors, agent interactions failing

**Solutions**:
- Implement exponential backoff and retry logic
- Use bulk APIs to reduce API call count
- Cache frequently accessed data in DynamoDB
- Negotiate higher API limits with vendor

### Issue: API Authentication Failures

**Symptoms**: HTTP 401 errors, "Invalid token" errors

**Solutions**:
- Verify OAuth token is valid and not expired
- Implement automatic token refresh
- Check Secrets Manager for correct credentials
- Verify API permissions are sufficient

### Issue: Slow API Response Times

**Symptoms**: Agent interactions taking >3 seconds, timeouts

**Solutions**:
- Implement connection pooling
- Cache frequently accessed data
- Use pagination for large result sets
- Optimize API queries (fetch only necessary fields)

### Issue: Data Inconsistency

**Symptoms**: Agents showing stale data, data not updating

**Solutions**:
- Verify agents are reading from system of record (not cache)
- Check for write failures in CloudWatch logs
- Implement data validation and reconciliation
- Use transactions for multi-step operations

---

## Recommendations

### For New Projects

1. **Conduct API Assessment** during Phase 0 (Business Value Assessment)
   - Document available APIs, authentication, and rate limits
   - Validate API access with system of record vendor
   - Estimate API call volumes based on projected agent interactions

2. **Use Integration Layer Pattern** for flexibility
   - Abstracts system of record APIs
   - Enables future migration to different system
   - Centralizes caching, rate limiting, and error handling

3. **Implement Comprehensive Monitoring**
   - Track API call volumes, latency, and error rates
   - Set up CloudWatch alarms for rate limit warnings
   - Monitor data consistency between agents and system of record

### For Existing Projects

1. **Optimize API Usage** to reduce costs and improve performance
   - Identify high-volume API calls and optimize
   - Implement caching for frequently accessed data
   - Use bulk APIs for batch operations

2. **Improve Resilience** to handle system of record downtime
   - Implement circuit breaker pattern
   - Provide fallback responses when system unavailable
   - Test agent behavior during system of record maintenance windows

3. **Enhance Audit Trail** for compliance and debugging
   - Log all API calls to CloudWatch
   - Write all agent interactions back to system of record
   - Implement data validation and reconciliation

---

**Document Owner**: IBM Consulting - AI Agent Practice  
**Last Updated**: February 2026  
**Next Review**: Quarterly (or after each major project completion)

---

**END OF DOCUMENT**
