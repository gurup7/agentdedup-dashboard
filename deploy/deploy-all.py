"""
AgentDedup — Full Deployment Script
====================================
Deploys all infrastructure to a target AWS account.

Usage:
    1. Copy config.env.template to config.env and fill in values
    2. Run: python deploy/deploy-all.py

Prerequisites:
    - AWS CLI configured with target account credentials
    - Docker installed and running
    - Python 3.11+
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Load configuration
# ---------------------------------------------------------------------------
DEPLOY_DIR = Path(__file__).parent
PROJECT_ROOT = DEPLOY_DIR.parent
CONFIG_FILE = DEPLOY_DIR / "config.env"

if not CONFIG_FILE.exists():
    print("ERROR: config.env not found. Copy config.env.template to config.env and fill in values.")
    sys.exit(1)

config = {}
with open(CONFIG_FILE) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            config[key.strip()] = value.strip()

AWS_ACCOUNT_ID = config.get("AWS_ACCOUNT_ID", "")
AWS_REGION = config.get("AWS_REGION", "us-east-1")
STACK_PREFIX = config.get("STACK_PREFIX", "dedup")
BEDROCK_MODEL_ID = config.get("BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0")

if AWS_ACCOUNT_ID == "CHANGE_ME" or not AWS_ACCOUNT_ID:
    print("ERROR: Set AWS_ACCOUNT_ID in config.env")
    sys.exit(1)


def run(cmd, cwd=None, check=True):
    """Run a shell command and print output."""
    print(f"\n  $ {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
    if check and result.returncode != 0:
        print(f"ERROR: Command failed with exit code {result.returncode}")
        sys.exit(1)
    return result


def wait_for_stack(stack_name):
    """Wait for a CloudFormation stack to complete."""
    print(f"  Waiting for {stack_name}...")
    while True:
        result = run(
            f"aws cloudformation describe-stacks --stack-name {stack_name} "
            f"--region {AWS_REGION} --query Stacks[0].StackStatus --output text",
            check=False,
        )
        status = result.stdout.strip()
        if "COMPLETE" in status:
            print(f"  {stack_name}: {status}")
            return status
        elif "FAILED" in status or "ROLLBACK" in status:
            print(f"  ERROR: {stack_name}: {status}")
            sys.exit(1)
        time.sleep(10)


# ---------------------------------------------------------------------------
# Verify AWS access
# ---------------------------------------------------------------------------
def step_0_verify():
    print("=" * 60)
    print("  STEP 0: Verify AWS Access")
    print("=" * 60)
    result = run(f"aws sts get-caller-identity --region {AWS_REGION} --output json")
    identity = json.loads(result.stdout)
    actual_account = identity.get("Account", "")
    if actual_account != AWS_ACCOUNT_ID:
        print(f"WARNING: Config says {AWS_ACCOUNT_ID} but CLI is using {actual_account}")
        response = input("Continue? (y/n): ")
        if response.lower() != "y":
            sys.exit(1)
    print(f"  Account: {actual_account}")
    print(f"  Region: {AWS_REGION}")


# ---------------------------------------------------------------------------
# Deploy CloudFormation stacks
# ---------------------------------------------------------------------------
def step_1_infra():
    print("\n" + "=" * 60)
    print("  STEP 1: Deploy Infrastructure (DynamoDB, S3, IAM, CloudWatch)")
    print("=" * 60)

    stacks = [
        ("dynamodb", "infra/dynamodb.yaml"),
        ("s3", "infra/s3.yaml"),
        ("iam", "infra/iam.yaml"),
        ("cloudwatch", "infra/cloudwatch.yaml"),
    ]

    for name, template in stacks:
        stack_name = f"{STACK_PREFIX}-{name}"
        template_path = PROJECT_ROOT / template
        if not template_path.exists():
            print(f"  SKIP: {template} not found")
            continue

        print(f"\n  Deploying {stack_name}...")
        run(
            f"aws cloudformation deploy "
            f"--template-file {template_path} "
            f"--stack-name {stack_name} "
            f"--capabilities CAPABILITY_NAMED_IAM "
            f"--region {AWS_REGION} "
            f"--no-fail-on-empty-changeset",
        )


def step_2_lambda_tools():
    print("\n" + "=" * 60)
    print("  STEP 2: Deploy Lambda Tools + API Gateway + Step Functions")
    print("=" * 60)

    # Build Lambda packages and deploy via CloudFormation
    # For now, use the SAM template directly
    template_path = PROJECT_ROOT / "infra" / "template.yaml"
    if not template_path.exists():
        print("  ERROR: infra/template.yaml not found")
        return

    stack_name = f"{STACK_PREFIX}-app"
    print(f"\n  Deploying {stack_name} (Lambda tools + API Gateway + Step Functions)...")
    print("  Note: This requires SAM CLI or manual Lambda packaging.")
    print(f"  Template: {template_path}")
    print(f"\n  To deploy manually:")
    print(f"    sam build --template-file infra/template.yaml")
    print(f"    sam deploy --stack-name {stack_name} --capabilities CAPABILITY_IAM --region {AWS_REGION} --resolve-s3")


def step_3_seed_data():
    print("\n" + "=" * 60)
    print("  STEP 3: Seed Test Data")
    print("=" * 60)

    seed_script = PROJECT_ROOT / "scripts" / "demo-reset.py"
    if seed_script.exists():
        run(f"python {seed_script}")
    else:
        print("  SKIP: scripts/demo-reset.py not found")


def step_4_verify():
    print("\n" + "=" * 60)
    print("  STEP 4: Verify Deployment")
    print("=" * 60)

    # Check API Gateway
    result = run(
        f"aws apigateway get-rest-apis --region {AWS_REGION} "
        f"--query \"items[?contains(name,'{STACK_PREFIX}')].{{name:name,id:id}}\" --output table",
        check=False,
    )

    # Check Lambda functions
    result = run(
        f"aws lambda list-functions --region {AWS_REGION} "
        f"--query \"Functions[?contains(FunctionName,'{STACK_PREFIX}')].FunctionName\" --output table",
        check=False,
    )

    # Check DynamoDB tables
    result = run(
        f"aws dynamodb list-tables --region {AWS_REGION} "
        f"--query \"TableNames[?contains(@,'{STACK_PREFIX}')]\" --output table",
        check=False,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("  AgentDedup — Full Deployment")
    print(f"  Account: {AWS_ACCOUNT_ID}")
    print(f"  Region: {AWS_REGION}")
    print(f"  Prefix: {STACK_PREFIX}")
    print("=" * 60)

    step_0_verify()
    step_1_infra()
    step_2_lambda_tools()
    step_3_seed_data()
    step_4_verify()

    print("\n" + "=" * 60)
    print("  DEPLOYMENT COMPLETE")
    print("=" * 60)
    print(f"\n  Next steps:")
    print(f"  1. Get API URL: aws apigateway get-rest-apis --region {AWS_REGION}")
    print(f"  2. Get API Key: aws apigateway get-api-keys --include-values --region {AWS_REGION}")
    print(f"  3. Update dashboard/.env with the new API URL and key")
    print(f"  4. Run: cd dashboard && streamlit run app.py")
    print()


if __name__ == "__main__":
    main()
