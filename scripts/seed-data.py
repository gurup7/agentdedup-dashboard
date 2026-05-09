#!/usr/bin/env python3
"""Seed CustomerTable with test data from tests/seed-data.json.

Usage:
    python scripts/seed-data.py <table-name>
    CUSTOMER_TABLE_NAME=my-table python scripts/seed-data.py
"""

import json
import os
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError


def get_table_name() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1]
    name = os.environ.get("CUSTOMER_TABLE_NAME")
    if name:
        return name
    print("Error: Provide table name as argument or set CUSTOMER_TABLE_NAME env var.")
    print("Usage: python scripts/seed-data.py <table-name>")
    sys.exit(1)


def load_seed_data() -> list[dict]:
    seed_path = Path(__file__).resolve().parent.parent / "tests" / "seed-data.json"
    with open(seed_path) as f:
        return json.load(f)


def seed_table(table_name: str, records: list[dict]) -> None:
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)

    # Verify table exists
    try:
        table.table_status
    except ClientError as e:
        print(f"Error accessing table '{table_name}': {e.response['Error']['Message']}")
        sys.exit(1)

    loaded = 0
    with table.batch_writer() as batch:
        for record in records:
            # Strip None values — DynamoDB doesn't accept None for non-key attributes
            item = {k: v for k, v in record.items() if v is not None}
            # Clean nested address map
            if "address" in item and isinstance(item["address"], dict):
                item["address"] = {k: v for k, v in item["address"].items() if v is not None}
            batch.put_item(Item=item)
            loaded += 1
            print(f"  [{loaded}/{len(records)}] Loaded {record['customerId']}")

    print(f"\nDone. {loaded} records loaded into '{table_name}'.")


def main() -> None:
    table_name = get_table_name()
    records = load_seed_data()
    print(f"Seeding {len(records)} records into '{table_name}'...\n")
    seed_table(table_name, records)


if __name__ == "__main__":
    main()
