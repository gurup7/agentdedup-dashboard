# AgentDedup — Deployment Guide

## Prerequisites

1. AWS CLI configured with admin access to the target account
2. Docker installed and running
3. Python 3.11+ installed
4. SAM CLI installed (optional — we use CloudFormation directly)

## Quick Start

```bash
# 1. Configure your target environment
cp deploy/config.env.template deploy/config.env
# Edit config.env with your account ID, region, etc.

# 2. Run the full deployment
python deploy/deploy-all.py
```

## What Gets Deployed

| Stack | Resources |
|-------|-----------|
| dedup-dynamodb | CustomerTable, ReviewQueue (DynamoDB) |
| dedup-s3 | Batch input, audit logs, batch reports (S3) |
| dedup-iam | IAM roles for all Lambda tools |
| dedup-cloudwatch | Log groups, alarms |
| dedup-app | 8 Lambda tools, API Gateway, Step Functions |
| AgentCore | Intercept Agent + Clean Agent on AgentCore Runtime |

## Estimated Deployment Time: ~30 minutes
