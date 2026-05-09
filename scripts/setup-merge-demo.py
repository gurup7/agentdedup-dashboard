"""Set up a merge demo: create two duplicate records in CustomerTable and a review entry."""
import boto3
import uuid
from datetime import datetime, timezone
from decimal import Decimal

REGION = "us-east-1"
dynamodb = boto3.resource("dynamodb", region_name=REGION)
customer_table = dynamodb.Table("dedup-dynamodb-CustomerTable")
review_table = dynamodb.Table("dedup-dynamodb-ReviewQueue")

# Record 1: Original from OneCRM (created 6 months ago)
record_a = {
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
}

# Record 2: Duplicate from NES (created 2 months ago - more recent, has extra data)
record_b = {
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
}

# Insert both records
customer_table.put_item(Item=record_a)
customer_table.put_item(Item=record_b)
print("Created 2 duplicate records in CustomerTable:")
print(f"  SOURCE: {record_a['customerId']} - {record_a['firstName']} {record_a['lastName']} ({record_a['sourceSystem']}, Oct 2025)")
print(f"  MASTER: {record_b['customerId']} - {record_b['firstName']} {record_b['lastName']} ({record_b['sourceSystem']}, Feb 2026)")
print()

# Create a review entry linking them
review_id = str(uuid.uuid4())
review = {
    "reviewId": review_id,
    "incomingRecord": record_a,
    "matchedRecord": record_b,
    "confidenceScore": Decimal("1.0"),
    "confidenceClassification": "high_confidence",
    "matchingMethod": "rule_based",
    "contributingFields": ["email", "lastName", "dateOfBirth", "postalCode"],
    "sourceAgent": "clean",
    "status": "pending",
    "createdAt": datetime.now(timezone.utc).isoformat(),
}
review_table.put_item(Item=review)

print(f"Created review entry: {review_id}")
print(f"  Source record (to be merged): {record_a['customerId']}")
print(f"  Master record (to keep):      {record_b['customerId']}")
print(f"  Score: 1.0 (high_confidence)")
print(f"  Status: pending")
print()
print(f"To approve this merge in Postman, use reviewId: {review_id}")
