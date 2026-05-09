"""List all reviews from ReviewQueue showing sourceAgent field."""
import boto3

table = boto3.resource("dynamodb", region_name="us-east-1").Table("dedup-dynamodb-ReviewQueue")
resp = table.scan(
    ProjectionExpression="reviewId, sourceAgent, confidenceScore, confidenceClassification, #s",
    ExpressionAttributeNames={"#s": "status"},
)

print(f"Total reviews: {resp['Count']}\n")
print(f"{'ReviewID':<40} {'Agent':<12} {'Score':<8} {'Classification':<22} {'Status'}")
print("-" * 100)
for item in resp["Items"]:
    rid = item.get("reviewId", "")
    agent = item.get("sourceAgent", "N/A")
    score = str(item.get("confidenceScore", ""))
    cls = item.get("confidenceClassification", "")
    status = item.get("status", "")
    print(f"{rid:<40} {agent:<12} {score:<8} {cls:<22} {status}")
