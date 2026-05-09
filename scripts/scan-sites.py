"""Simulate batch site dedup scan for ELTHAM HILL SCHOOL."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("CUSTOMER_TABLE_NAME", "dedup-dynamodb-CustomerTable")
os.environ.setdefault("REVIEW_QUEUE_TABLE_NAME", "dedup-dynamodb-ReviewQueue")
os.environ.setdefault("SITE_TABLE_NAME", "dedup-dynamodb-SiteTable")
os.environ.setdefault("AUDIT_LOGS_BUCKET", "dedup-s3-dedup-audit-logs")

import boto3
from boto3.dynamodb.conditions import Key
from agents.intercept.orchestrator import process_register_site

dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
site_table = dynamodb.Table("dedup-dynamodb-SiteTable")

# Get all ELTHAM HILL SCHOOL sites
resp = site_table.query(
    IndexName="AccountNumberIndex",
    KeyConditionExpression=Key("accountNumber").eq("3518670"),
)
sites = resp["Items"]
print(f"Found {len(sites)} sites for ELTHAM HILL SCHOOL (Account 3518670)")
print()

# Check each site against the account (simulates batch scan)
for i, site in enumerate(sites[1:3], 2):  # Check sites 2 and 3
    result = process_register_site({
        "accountNumber": site["accountNumber"],
        "accountDescription": site["accountDescription"],
        "siteNumber": site["siteNumber"],
        "siteId": site["siteId"],
        "operatingUnit": site["operatingUnit"],
        "purpose": site["purpose"],
        "country": site["country"],
        "addressLine1": site["addressLine1"],
        "city": site["city"],
        "postalCode": site["postalCode"],
        "county": site.get("county", ""),
        "sourceSystem": site["sourceSystem"],
    }, source_agent="clean")
    print(f"Site #{i} (siteNumber={site['siteNumber']}, address=\"{site['addressLine1']}\"):")
    print(f"  Status: {result['status']}")
    print(f"  Cumulative: {result.get('cumulativeScore', 'N/A')}")
    print(f"  Classification: {result.get('confidenceClassification', 'N/A')}")
    if result.get("reviewId"):
        print(f"  Review ID: {result['reviewId']}")
    print()

print("Check the Duplicate Reviews tab for new site-level reviews!")
