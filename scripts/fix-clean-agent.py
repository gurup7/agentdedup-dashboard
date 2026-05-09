"""Add sourceAgent: clean to all return statements in the clean orchestrator."""

with open("agents/clean/orchestrator.py", "r") as f:
    content = f.read()

# Add sourceAgent to error return
content = content.replace(
    '"error": str(exc),\n            "batchId": batch_id,',
    '"error": str(exc),\n            "sourceAgent": "clean",\n            "batchId": batch_id,',
)

# Add sourceAgent to new record (no candidates)
content = content.replace(
    '"matchingMethod": "none",\n            "batchId": batch_id,',
    '"matchingMethod": "none",\n            "sourceAgent": "clean",\n            "batchId": batch_id,',
)

# Add sourceAgent to review pending
content = content.replace(
    '"matchedRecord": matched_record,\n            "batchId": batch_id,',
    '"matchedRecord": matched_record,\n            "sourceAgent": "clean",\n            "batchId": batch_id,',
)

# Add sourceAgent to new record (low score)  
content = content.replace(
    '"matchingMethod": matching_method,\n            "batchId": batch_id,',
    '"matchingMethod": matching_method,\n            "sourceAgent": "clean",\n            "batchId": batch_id,',
)

with open("agents/clean/orchestrator.py", "w") as f:
    f.write(content)

print("Added sourceAgent: clean to all return statements.")
