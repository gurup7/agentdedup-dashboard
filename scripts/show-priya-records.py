"""Show the Priya Sharma records in DynamoDB - the merge demo pair."""
import boto3
import json

table = boto3.resource("dynamodb", region_name="us-east-1").Table("dedup-dynamodb-CustomerTable")

# Get both Priya Sharma records
source = table.get_item(Key={"customerId": "demo-merge-source-001"}).get("Item", {})
master = table.get_item(Key={"customerId": "demo-merge-master-001"}).get("Item", {})

print("=" * 70)
print("PRIYA SHARMA RECORDS IN DYNAMODB (CustomerTable)")
print("=" * 70)

print("\nRECORD 1 (Source - OneCRM):")
print(f"  customerId:  {source.get('customerId')}")
print(f"  firstName:   {source.get('firstName')}")
print(f"  lastName:    {source.get('lastName')}")
print(f"  email:       {source.get('email')}")
print(f"  phone:       {source.get('phone')}")
print(f"  DOB:         {source.get('dateOfBirth')}")
print(f"  source:      {source.get('sourceSystem')}")
print(f"  status:      {source.get('status')}")
print(f"  mergedInto:  {source.get('mergedInto', '(none)')}")

print("\nRECORD 2 (Master - NES):")
print(f"  customerId:  {master.get('customerId')}")
print(f"  firstName:   {master.get('firstName')}")
print(f"  lastName:    {master.get('lastName')}")
print(f"  email:       {master.get('email')}")
print(f"  phone:       {master.get('phone')}")
print(f"  DOB:         {master.get('dateOfBirth')}")
print(f"  source:      {master.get('sourceSystem')}")
print(f"  status:      {master.get('status')}")
print(f"  mergedInto:  {master.get('mergedInto', '(none)')}")

# Count active vs merged
resp = table.scan(ProjectionExpression="customerId, #s, mergedInto", ExpressionAttributeNames={"#s": "status"})
active = sum(1 for i in resp["Items"] if i.get("status") == "active")
merged = sum(1 for i in resp["Items"] if i.get("status") == "merged")
total = resp["Count"]

print(f"\n{'=' * 70}")
print(f"SUMMARY: {total} total records | {active} active | {merged} merged")
print(f"{'=' * 70}")

if merged > 0:
    print("\nMERGED RECORDS (no longer active — consolidated into master):")
    for item in resp["Items"]:
        if item.get("status") == "merged":
            print(f"  {item['customerId']} → merged into {item.get('mergedInto', '?')}")
