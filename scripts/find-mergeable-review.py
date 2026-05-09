"""Find a review where both incoming and matched records have customerIds."""
import boto3

table = boto3.resource("dynamodb", region_name="us-east-1").Table("dedup-dynamodb-ReviewQueue")
resp = table.scan(
    FilterExpression="#s = :pending",
    ExpressionAttributeNames={"#s": "status"},
    ExpressionAttributeValues={":pending": "pending"},
)

print("Reviews with BOTH record IDs (mergeable):\n")
count = 0
for item in resp["Items"]:
    incoming = item.get("incomingRecord", {})
    matched = item.get("matchedRecord", {})
    inc_id = incoming.get("customerId", "")
    match_id = matched.get("customerId", "")
    if inc_id and match_id:
        count += 1
        print(f"  ReviewID: {item['reviewId']}")
        print(f"    Source: {incoming.get('firstName')} {incoming.get('lastName')} (ID: {inc_id}) from {incoming.get('sourceSystem')}")
        print(f"    Master: {matched.get('firstName')} {matched.get('lastName')} (ID: {match_id}) from {matched.get('sourceSystem')}")
        print(f"    Score:  {item.get('confidenceScore')}")
        print()
        if count >= 3:
            break

if count == 0:
    print("  No mergeable reviews found (incoming records don't have customerIds)")
    print("  This is expected for intercepted records that haven't been created yet.")
