"""Demo: Show before/after merge for a review."""
import boto3
import json
import sys

REVIEW_ID = "20b7184f-23cb-4f24-81e5-84f57d180ba3"
REGION = "us-east-1"

dynamodb = boto3.resource("dynamodb", region_name=REGION)
review_table = dynamodb.Table("dedup-dynamodb-ReviewQueue")
customer_table = dynamodb.Table("dedup-dynamodb-CustomerTable")

# Get the review
resp = review_table.get_item(Key={"reviewId": REVIEW_ID})
review = resp.get("Item", {})
incoming = review.get("incomingRecord", {})
matched = review.get("matchedRecord", {})

print("=" * 60)
print("BEFORE MERGE")
print("=" * 60)
print()
print("INCOMING RECORD (from batch scan - NES):")
print(f"  Name:   {incoming.get('firstName')} {incoming.get('lastName')}")
print(f"  Email:  {incoming.get('email')}")
print(f"  Phone:  {incoming.get('phone')}")
print(f"  DOB:    {incoming.get('dateOfBirth')}")
print(f"  Source: {incoming.get('sourceSystem')}")
print()
print("MATCHED RECORD (existing in TEP - OneCRM):")
print(f"  ID:     {matched.get('customerId')}")
print(f"  Name:   {matched.get('firstName')} {matched.get('lastName')}")
print(f"  Email:  {matched.get('email')}")
print(f"  Phone:  {matched.get('phone')}")
print(f"  DOB:    {matched.get('dateOfBirth')}")
print(f"  Source: {matched.get('sourceSystem')}")
print(f"  Status: {matched.get('status')}")
print()
print(f"Confidence Score: {review.get('confidenceScore')}")
print(f"Classification:   {review.get('confidenceClassification')}")
print(f"Review Status:    {review.get('status')}")
print()
print("-" * 60)
print("Approving merge...")
print("-" * 60)
