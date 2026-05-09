"""BatchParser Lambda — reads CSV/JSON from S3 and returns parsed records.

Also handles summary generation for the batch Step Functions workflow.

Environment variables:
    BATCH_REPORTS_BUCKET: S3 bucket name for writing summary reports.
"""

import csv
import io
import json
import logging
import os
import uuid
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")

REPORTS_BUCKET = os.environ.get("BATCH_REPORTS_BUCKET", "dedup-batch-reports")


def handler(event, context):
    """Lambda entry point.

    Supports two modes based on the 'action' field:
      - parse (default): Read a file from S3 and return records array.
      - summarize: Aggregate Map state results and write summary to S3.
    """
    action = event.get("action", "parse")

    if action == "summarize":
        return _generate_summary(event)
    return _parse_file(event)


def _parse_file(event):
    """Read a CSV or JSON file from S3 and return parsed records."""
    bucket = event["bucket"]
    key = event["key"]

    logger.info("Parsing file s3://%s/%s", bucket, key)

    resp = s3.get_object(Bucket=bucket, Key=key)
    body = resp["Body"].read().decode("utf-8")

    if key.lower().endswith(".json"):
        records = json.loads(body)
        if isinstance(records, dict):
            # Support {"records": [...]} wrapper
            records = records.get("records", [records])
    elif key.lower().endswith(".csv"):
        reader = csv.DictReader(io.StringIO(body))
        records = list(reader)
    else:
        raise ValueError(f"Unsupported file format: {key}. Use .csv or .json")

    logger.info("Parsed %d records from s3://%s/%s", len(records), bucket, key)

    return {
        "records": records,
        "totalRecords": len(records),
        "sourceFile": f"s3://{bucket}/{key}",
    }


def _generate_summary(event):
    """Aggregate batch results and write summary report to S3."""
    source_file = event.get("sourceFile", "unknown")
    total_records = event.get("totalRecords", 0)
    results = event.get("results", [])
    report_bucket = event.get("reportBucket", REPORTS_BUCKET)

    start_time = datetime.now(timezone.utc)

    duplicates = 0
    high_confidence = 0
    potential = 0
    new_records = 0
    errors = 0

    for item in results:
        result = item.get("result", {})
        status = result.get("status", "error")

        if status == "review_pending":
            duplicates += 1
            classification = result.get("confidenceClassification", "")
            if classification == "high_confidence":
                high_confidence += 1
            else:
                potential += 1
        elif status == "new_record":
            new_records += 1
        elif status == "error":
            errors += 1

    batch_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    report_key = (
        f"batch-reports/{now.strftime('%Y/%m/%d')}/{batch_id}-summary.json"
    )

    summary = {
        "batchId": batch_id,
        "timestamp": now.isoformat(),
        "sourceFile": source_file,
        "totalRecordsScanned": total_records,
        "duplicatesIdentified": duplicates,
        "highConfidenceDuplicates": high_confidence,
        "potentialDuplicates": potential,
        "newRecordsCreated": new_records,
        "errors": errors,
        "reviewsCreated": duplicates,
    }

    s3.put_object(
        Bucket=report_bucket,
        Key=report_key,
        Body=json.dumps(summary, indent=2),
        ContentType="application/json",
    )

    logger.info("Wrote batch summary to s3://%s/%s", report_bucket, report_key)

    return {
        "reportKey": report_key,
        "reportBucket": report_bucket,
        **summary,
    }
