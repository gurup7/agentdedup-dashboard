# AgentDedup — Client Sandbox Prerequisites

## AWS Account Requirements

Please provision the following access in the sandbox AWS account before deployment.

### 1. IAM Permissions Required

The deployer IAM user/role needs these permissions:

| AWS Service | Permissions Needed |
|---|---|
| **CloudFormation** | CreateStack, UpdateStack, DeleteStack, DescribeStacks |
| **Lambda** | CreateFunction, UpdateFunctionCode, InvokeFunction, CreateEventSourceMapping |
| **DynamoDB** | CreateTable, DescribeTable, Scan, Query, PutItem, UpdateItem, GetItem |
| **S3** | CreateBucket, PutObject, GetObject, ListBucket |
| **API Gateway** | CreateRestApi, CreateDeployment, CreateApiKey, CreateUsagePlan |
| **Step Functions** | CreateStateMachine, StartExecution, DescribeExecution |
| **IAM** | CreateRole, AttachRolePolicy, PutRolePolicy (for service roles) |
| **KMS** | CreateKey, CreateAlias, Encrypt, Decrypt |
| **CloudWatch** | CreateLogGroup, PutMetricAlarm, DescribeAlarms |
| **ECR** | CreateRepository, PutImage, GetAuthorizationToken |
| **Bedrock** | InvokeModel (for Amazon Nova Pro or Claude) |
| **Bedrock AgentCore** | CreateAgentRuntime, InvokeAgent, CreateGateway |

**Recommended:** Attach `AdministratorAccess` for the sandbox deployment, then scope down for production.

### 2. Amazon Bedrock Model Access

Enable the following model in the target region:
- **Amazon Nova Pro** (`amazon.nova-pro-v1:0`)
- Go to: Bedrock Console → Model access → Request access

### 3. Region Selection

| Question | Recommendation |
|---|---|
| Which region? | Same region as Oracle EBS (or closest) to minimize latency |
| Bedrock availability? | Check https://docs.aws.amazon.com/bedrock/latest/userguide/models-regions.html |
| AgentCore availability? | Check if AgentCore Runtime is available in the target region |

### 4. Network Requirements

| Requirement | Details |
|---|---|
| VPC | Default VPC is fine for sandbox. Production needs private subnets. |
| Internet access | Lambda functions need outbound internet for Bedrock API calls |
| Oracle EBS connectivity | If Mulesoft API is used, Lambda needs to reach the Mulesoft endpoint |

### 5. Service Quotas to Check

| Service | Default Quota | We Need |
|---|---|---|
| Lambda concurrent executions | 1000 | 50+ |
| DynamoDB tables | 2500 | 2 |
| API Gateway REST APIs | 600 | 1 |
| Step Functions state machines | 10000 | 2 |
| S3 buckets | 100 | 3 |

## Deployment Steps (After Prerequisites Met)

```bash
# 1. Configure AWS CLI with sandbox credentials
aws configure --profile client-sandbox

# 2. Copy and edit config
cp deploy/config.env.template deploy/config.env
# Set AWS_ACCOUNT_ID, AWS_REGION

# 3. Deploy
AWS_PROFILE=client-sandbox python deploy/deploy-all.py

# 4. Seed test data
python scripts/demo-reset.py

# 5. Start dashboard
cd dashboard && streamlit run app.py
```

## Estimated Costs (Sandbox)

| Service | Monthly Cost |
|---|---|
| DynamoDB (on-demand) | < $1 |
| Lambda | < $1 |
| API Gateway | < $1 |
| Step Functions | < $1 |
| S3 | < $1 |
| Bedrock (per-token) | ~$5-10 (depends on usage) |
| CloudWatch | < $2 |
| **Total** | **~$10-15/month** |
