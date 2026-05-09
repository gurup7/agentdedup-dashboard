"""
DEMO RESET SCRIPT
=================
Run this BEFORE every client demo to start with a clean state.
Clears all previous test data and seeds fresh records.

Usage:
    python scripts/demo-reset.py
"""
import boto3
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

REGION = "us-east-1"
CUSTOMER_TABLE = "dedup-dynamodb-CustomerTable"
REVIEW_TABLE = "dedup-dynamodb-ReviewQueue"
SITE_TABLE = "dedup-dynamodb-SiteTable"
BATCH_BUCKET = "dedup-s3-dedup-batch-input"

dynamodb = boto3.resource("dynamodb", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)
customer_table = dynamodb.Table(CUSTOMER_TABLE)
review_table = dynamodb.Table(REVIEW_TABLE)
site_table = dynamodb.Table(SITE_TABLE)


def clear_table(table, key_name):
    """Delete all items from a DynamoDB table."""
    resp = table.scan(ProjectionExpression=key_name)
    items = resp.get("Items", [])
    count = 0
    with table.batch_writer() as batch:
        for item in items:
            batch.delete_item(Key={key_name: item[key_name]})
            count += 1
    # Handle pagination
    while resp.get("LastEvaluatedKey"):
        resp = table.scan(
            ProjectionExpression=key_name,
            ExclusiveStartKey=resp["LastEvaluatedKey"],
        )
        with table.batch_writer() as batch:
            for item in resp.get("Items", []):
                batch.delete_item(Key={key_name: item[key_name]})
                count += 1
    return count


def seed_customers():
    """Seed the CustomerTable with demo records (Person + Organization)."""
    seed_path = Path(__file__).parent.parent / "tests" / "seed-data.json"
    with open(seed_path) as f:
        records = json.load(f)

    # Also add the merge demo records (Person)
    merge_records = [
        {
            "customerId": "demo-merge-source-001",
            "firstName": "Priya",
            "lastName": "Sharma",
            "email": "priya.sharma@pearson.com",
            "phone": "+14085551001",
            "dateOfBirth": "1992-04-18",
            "address": {"street": "500 Innovation Dr", "city": "San Jose", "state": "CA", "postalCode": "95101", "country": "US"},
            "sourceSystem": "OneCRM",
            "status": "active",
            "postalCode": "95101",
            "createdAt": "2025-10-15T10:00:00+00:00",
            "updatedAt": "2025-10-15T10:00:00+00:00",
        },
        {
            "customerId": "demo-merge-master-001",
            "firstName": "Priya",
            "lastName": "Sharma",
            "email": "priya.sharma@pearson.com",
            "phone": "+14085551002",
            "dateOfBirth": "1992-04-18",
            "address": {"street": "500 Innovation Drive", "city": "San Jose", "state": "CA", "postalCode": "95101", "country": "US"},
            "sourceSystem": "NES",
            "status": "active",
            "postalCode": "95101",
            "createdAt": "2026-02-20T14:30:00+00:00",
            "updatedAt": "2026-02-20T14:30:00+00:00",
        },
    ]

    # seed-data.json now includes 5 organization records (org-aaaa-1111-bbbb-00000000000X)
    all_records = records + merge_records
    loaded = 0
    person_count = 0
    org_count = 0
    with customer_table.batch_writer() as batch:
        for record in all_records:
            item = {k: v for k, v in record.items() if v is not None}
            if "address" in item and isinstance(item["address"], dict):
                item["address"] = {k: v for k, v in item["address"].items() if v is not None}
            batch.put_item(Item=item)
            loaded += 1
            if item.get("partyType") == "ORGANIZATION":
                org_count += 1
            else:
                person_count += 1

    print(f"      ({person_count} person + {org_count} organization records)")
    return loaded


def seed_sites():
    """Seed the SiteTable with demo site records for site-level dedup."""
    seed_path = Path(__file__).parent.parent / "tests" / "site-seed-data.json"
    with open(seed_path) as f:
        records = json.load(f)

    loaded = 0
    accounts = set()
    with site_table.batch_writer() as batch:
        for record in records:
            item = {k: v for k, v in record.items() if v is not None}
            batch.put_item(Item=item)
            loaded += 1
            accounts.add(record["accountNumber"])

    print(f"      ({loaded} site records across {len(accounts)} accounts)")
    return loaded


def seed_merge_review():
    """Create the merge review entry for Scenario 4."""
    review_id = "demo-review-merge-001"
    review = {
        "reviewId": review_id,
        "incomingRecord": {
            "customerId": "demo-merge-source-001",
            "firstName": "Priya",
            "lastName": "Sharma",
            "email": "priya.sharma@pearson.com",
            "phone": "+14085551001",
            "sourceSystem": "OneCRM",
        },
        "matchedRecord": {
            "customerId": "demo-merge-master-001",
            "firstName": "Priya",
            "lastName": "Sharma",
            "email": "priya.sharma@pearson.com",
            "phone": "+14085551002",
            "sourceSystem": "NES",
        },
        "confidenceScore": Decimal("1.0"),
        "confidenceClassification": "high_confidence",
        "matchingMethod": "rule_based",
        "contributingFields": ["email", "lastName", "dateOfBirth", "postalCode"],
        "sourceAgent": "clean",
        "status": "pending",
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    review_table.put_item(Item=review)
    return review_id


def upload_batch_file():
    """Upload the batch demo file to S3."""
    batch_path = Path(__file__).parent.parent / "tests" / "batch-scenario3-existing-dupes.json"
    s3.upload_file(str(batch_path), BATCH_BUCKET, "scenario3-existing-dupes.json")


def main():
    print("=" * 60)
    print("  DEMO RESET - Preparing clean state for client demo")
    print("=" * 60)
    print()

    # Step 1: Clear tables
    print("[1/7] Clearing CustomerTable...")
    count = clear_table(customer_table, "customerId")
    print(f"      Deleted {count} records.")

    print("[2/7] Clearing ReviewQueue...")
    count = clear_table(review_table, "reviewId")
    print(f"      Deleted {count} records.")

    print("[3/7] Clearing SiteTable...")
    try:
        count = clear_table(site_table, "siteId")
        print(f"      Deleted {count} records.")
    except Exception:
        print("      SiteTable not deployed yet — skipping.")

    # Step 2: Seed fresh data
    print("[4/7] Seeding CustomerTable with demo records...")
    loaded = seed_customers()
    print(f"      Loaded {loaded} records (20 person + 5 org seeded + 2 merge demo).")

    print("[5/7] Seeding SiteTable with demo site records...")
    try:
        site_loaded = seed_sites()
        print(f"      Loaded {site_loaded} site records.")
    except Exception:
        print("      SiteTable not deployed yet — skipping.")

    # Step 3: Create merge review
    print("[6/7] Creating merge review for Scenario 4...")
    review_id = seed_merge_review()
    print(f"      Review ID: {review_id}")

    # Step 4: Upload batch file
    print("[7/7] Uploading batch file to S3...")
    upload_batch_file()
    print("      Uploaded scenario3-existing-dupes.json")

    print()
    print("=" * 60)
    print("  DEMO READY!")
    print("=" * 60)
    print()
    print("  Postman Collection: Customer Data Deduplication API")
    print("  Environment: Dedup API - Prototype")
    print()
    print("  Scenario 1: Send 'Scenario 1: Register New Unique Customer'")
    print("  Scenario 2: Send 'Scenario 2: Duplicate from NES'")
    print("  Scenario 3: Send 'Scenario 3: Batch Scan' (AWS Signature auth)")
    print("  Scenario 4: Send 'Scenario 4: Approve Merge'")
    print("  Scenario 5: Register Organization (e.g. 'Pearson Education')")
    print("  Scenario 6: Register Site (e.g. 'ELTHAM HILL SCHOOL' address)")
    print()
    print(f"  Merge Review ID (Scenario 4): {review_id}")
    print()
    print("  Organization records seeded:")
    print("    - Pearson Education Inc. (OneCRM) — org-aaaa-1111-bbbb-000000000001")
    print("    - Pearson Education (NES)         — org-aaaa-1111-bbbb-000000000002")
    print("    - McGraw Hill LLC (OneCRM)        — org-aaaa-1111-bbbb-000000000003")
    print("    - Pearson Edu (NES, typo)         — org-aaaa-1111-bbbb-000000000004")
    print("    - Random Corp (OneCRM)            — org-aaaa-1111-bbbb-000000000005")
    print()
    print("  Site records seeded:")
    print("    - ELTHAM HILL SCHOOL (Account 3518670): 6 sites with address variations")
    print("    - MERCHANFACTORY (Account 57306583):    3 sites with identical addresses")
    print("    - WESTFIELD ACADEMY (Account 9912345):  2 sites with different addresses")
    print("    - SOLO TRADING LTD (Account 8800001):   1 site (new record path)")
    print()


if __name__ == "__main__":
    main()
