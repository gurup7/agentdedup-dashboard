"""Show pending reviews from the Clean Agent batch run with source/target details."""
import boto3
import json

table = boto3.resource("dynamodb", region_name="us-east-1").Table("dedup-dynamodb-ReviewQueue")
resp = table.scan(
    FilterExpression="#s = :pending AND sourceAgent = :clean",
    ExpressionAttributeNames={"#s": "status"},
    ExpressionAttributeValues={":pending": "pending", ":clean": "clean"},
)

print(f"Pending Clean Agent reviews: {resp['Count']}\n")
print(f"{'#':<3} {'ReviewID':<38} {'Incoming (from batch)':<35} {'Matched (existing in TEP)':<35} {'Score'}")
print("-" * 130)

for i, item in enumerate(resp["Items"][:10], 1):
    incoming = item.get("incomingRecord", {})
    matched = item.get("matchedRecord", {})
    inc_name = f"{incoming.get('firstName', '')} {incoming.get('lastName', '')} ({incoming.get('sourceSystem', '')})"
    match_name = f"{matched.get('firstName', '')} {matched.get('lastName', '')} ({matched.get('sourceSystem', '')})"
    match_id = matched.get("customerId", "")[:12] + "..."
    print(f"{i:<3} {item['reviewId']:<38} {inc_name:<35} {match_name} [{match_id}]  {item.get('confidenceScore', '')}")
