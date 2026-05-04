"""
AgentDedup — Customer Data Deduplication Dashboard
Streamlit UI for the Customer Data Deduplication prototype.
Calls existing API Gateway endpoints and reads DynamoDB directly for display.
Supports both PERSON and ORGANIZATION party types.
"""

import json
import os
import re
import time
from datetime import datetime, timezone
from decimal import Decimal

import boto3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
load_dotenv()

API_URL = os.getenv("API_URL", "https://qlx4tvau7g.execute-api.us-east-1.amazonaws.com/prod")
API_KEY = os.getenv("API_KEY", "j88R5YxG7f3enQYQnJJO86Wi5Pu8jE4u2s9wgYBc")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
CUSTOMER_TABLE = os.getenv("CUSTOMER_TABLE_NAME", "dedup-dynamodb-CustomerTable")
REVIEW_TABLE = os.getenv("REVIEW_QUEUE_TABLE_NAME", "dedup-dynamodb-ReviewQueue")
BEDROCK_MODEL = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0")
BATCH_STATE_MACHINE_ARN = os.getenv(
    "BATCH_STATE_MACHINE_ARN",
    "arn:aws:states:us-east-1:553556337417:stateMachine:dedup-app-dedup-batch",
)
BATCH_INPUT_BUCKET = os.getenv("BATCH_INPUT_BUCKET", "dedup-s3-dedup-batch-input")
BATCH_INPUT_KEY = os.getenv("BATCH_INPUT_KEY", "scenario3-existing-dupes.json")

API_HEADERS = {"Content-Type": "application/json", "x-api-key": API_KEY}


# ---------------------------------------------------------------------------
# AWS Clients (cached)
# ---------------------------------------------------------------------------
@st.cache_resource
def get_dynamodb():
    return boto3.resource("dynamodb", region_name=AWS_REGION)


@st.cache_resource
def get_sfn_client():
    return boto3.client("stepfunctions", region_name=AWS_REGION)


@st.cache_resource
def get_bedrock_client():
    return boto3.client("bedrock-runtime", region_name=AWS_REGION)


@st.cache_resource
def get_s3_client():
    return boto3.client("s3", region_name=AWS_REGION)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def decimal_default(obj):
    """JSON serializer for Decimal types from DynamoDB."""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def safe_float(val, default=0.0):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def format_record_name(record):
    """Extract a display name from a customer record dict."""
    # Organization records use partyName
    party_name = record.get("partyName")
    if party_name:
        return party_name
    first = record.get("firstName", "")
    last = record.get("lastName", "")
    return f"{first} {last}".strip() or "Unknown"


def format_address(addr):
    if not addr or not isinstance(addr, dict):
        return "N/A"
    parts = [
        addr.get("street", ""),
        addr.get("city", ""),
        addr.get("state", ""),
        addr.get("postalCode", ""),
        addr.get("country", ""),
    ]
    return ", ".join(p for p in parts if p) or "N/A"


def get_party_type(record):
    """Return the party type for a record, defaulting to PERSON."""
    return record.get("partyType", "PERSON").upper()


# ---------------------------------------------------------------------------
# Data Fetching
# ---------------------------------------------------------------------------
def fetch_customers():
    """Scan CustomerTable via boto3."""
    table = get_dynamodb().Table(CUSTOMER_TABLE)
    items = []
    try:
        resp = table.scan()
        items.extend(resp.get("Items", []))
        while "LastEvaluatedKey" in resp:
            resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
            items.extend(resp.get("Items", []))
    except ClientError as e:
        st.error(f"Failed to fetch customers: {e.response['Error']['Message']}")
    return items


def fetch_reviews_dynamo():
    """Scan ReviewQueue via boto3 for full data."""
    table = get_dynamodb().Table(REVIEW_TABLE)
    items = []
    try:
        resp = table.scan()
        items.extend(resp.get("Items", []))
        while "LastEvaluatedKey" in resp:
            resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
            items.extend(resp.get("Items", []))
    except ClientError as e:
        st.error(f"Failed to fetch reviews: {e.response['Error']['Message']}")
    return items


def call_register(payload):
    """POST /register via API Gateway."""
    try:
        resp = requests.post(f"{API_URL}/register", headers=API_HEADERS, json=payload, timeout=30)
        text = resp.text
        try:
            return resp.json()
        except Exception:
            result = {}
            text = text.strip().strip("{}")
            parts = []
            depth = 0
            current = ""
            for ch in text:
                if ch == "{":
                    depth += 1
                    current += ch
                elif ch == "}":
                    depth -= 1
                    current += ch
                elif ch == "," and depth == 0:
                    parts.append(current.strip())
                    current = ""
                else:
                    current += ch
            if current.strip():
                parts.append(current.strip())
            for part in parts:
                if "=" in part:
                    key, _, value = part.partition("=")
                    key = key.strip()
                    value = value.strip()
                    if value == "null":
                        value = None
                    elif value.replace(".", "", 1).isdigit():
                        value = float(value)
                    result[key] = value
            return result
    except requests.exceptions.Timeout:
        return {"error": "Request timed out (agent processing may take up to 30s)"}
    except Exception as e:
        return {"error": str(e)}


def call_approve(review_id):
    """POST /reviews/{id}/approve via API Gateway."""
    try:
        resp = requests.post(f"{API_URL}/reviews/{review_id}/approve", headers=API_HEADERS, timeout=30)
        try:
            return resp.json()
        except Exception:
            return _parse_sfn_output(resp.text)
    except Exception as e:
        return {"error": str(e)}


def call_reject(review_id):
    """POST /reviews/{id}/reject via API Gateway."""
    try:
        resp = requests.post(f"{API_URL}/reviews/{review_id}/reject", headers=API_HEADERS, timeout=30)
        try:
            return resp.json()
        except Exception:
            return _parse_sfn_output(resp.text)
    except Exception as e:
        return {"error": str(e)}


def _parse_sfn_output(text):
    """Parse Step Functions key=value output format into a dict."""
    result = {}
    text = text.strip().strip("{}")
    parts = []
    depth = 0
    current = ""
    for ch in text:
        if ch == "{":
            depth += 1
            current += ch
        elif ch == "}":
            depth -= 1
            current += ch
        elif ch == "," and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += ch
    if current.strip():
        parts.append(current.strip())
    for part in parts:
        if "=" in part:
            key, _, value = part.partition("=")
            key = key.strip()
            value = value.strip()
            if value == "null":
                value = None
            elif value.replace(".", "", 1).isdigit():
                value = float(value)
            result[key] = value
    return result


def trigger_batch():
    """Start the batch Step Functions execution."""
    try:
        client = get_sfn_client()
        resp = client.start_execution(
            stateMachineArn=BATCH_STATE_MACHINE_ARN,
            input=json.dumps({"bucket": BATCH_INPUT_BUCKET, "key": BATCH_INPUT_KEY}),
        )
        return {
            "executionArn": resp["executionArn"],
            "startDate": resp["startDate"].isoformat(),
        }
    except ClientError as e:
        return {"error": e.response["Error"]["Message"]}


def get_execution_status(execution_arn):
    """Check Step Functions execution status."""
    try:
        client = get_sfn_client()
        resp = client.describe_execution(executionArn=execution_arn)
        result = {"status": resp["status"]}
        if resp["status"] == "SUCCEEDED" and "output" in resp:
            result["output"] = json.loads(resp["output"])
        return result
    except ClientError as e:
        return {"error": e.response["Error"]["Message"]}


# ---------------------------------------------------------------------------
# Chatbot — Bedrock Claude integration
# ---------------------------------------------------------------------------
def parse_chat_command(message):
    """Parse user message for known command patterns. Returns (action, params) or None."""
    msg = message.lower().strip()

    reg_match = re.search(
        r"register\s+(\w+)\s+(\w+)\s+from\s+(\w+)\s+with\s+email\s+([\w.@+-]+)",
        msg,
    )
    if reg_match:
        return "register", {
            "firstName": reg_match.group(1).title(),
            "lastName": reg_match.group(2).title(),
            "sourceSystem": reg_match.group(3),
            "email": reg_match.group(4),
        }

    approve_match = re.search(r"approve\s+(?:review\s+)?([a-zA-Z0-9-]+)", msg)
    if approve_match and "reject" not in msg:
        return "approve", {"reviewId": approve_match.group(1)}

    reject_match = re.search(r"reject\s+(?:review\s+)?([a-zA-Z0-9-]+)", msg)
    if reject_match:
        return "reject", {"reviewId": reject_match.group(1)}

    if any(w in msg for w in ["duplicate", "review", "pending"]):
        if "how many" in msg or "count" in msg:
            return "count_reviews", {}
        return "show_reviews", {}

    if any(w in msg for w in ["account", "customer", "record"]):
        if "how many" in msg or "count" in msg:
            return "count_customers", {}
        return "show_accounts", {}

    if any(w in msg for w in ["scan", "batch"]):
        return "batch_scan", {}

    if any(w in msg for w in ["stat", "dashboard", "summary", "overview"]):
        return "show_dashboard", {}

    return None, None


def ask_bedrock(message, context=""):
    """Use Bedrock Claude to interpret an ambiguous user message."""
    try:
        client = get_bedrock_client()
        prompt = f"""You are a helpful assistant for the AgentDedup customer data deduplication system.
The system has these capabilities:
- Register new customers or organizations (from OneCRM or NES source systems)
- Detect duplicate customer and organization records
- Review pending duplicate pairs (approve or reject merges)
- Run batch scans for historical duplicates
- Show dashboard statistics

The user said: "{message}"
{f"Additional context: {context}" if context else ""}

Respond concisely. If the user wants to perform an action, explain what you would do.
If it's a question, answer it based on the system's capabilities.
Keep your response under 3 sentences."""

        body = json.dumps(
            {
                "messages": [{"role": "user", "content": [{"text": prompt}]}],
                "inferenceConfig": {"maxTokens": 300, "temperature": 0.1},
            }
        )
        resp = client.invoke_model(modelId=BEDROCK_MODEL, body=body, contentType="application/json", accept="application/json")
        result = json.loads(resp["body"].read())
        return result["output"]["message"]["content"][0]["text"]
    except Exception as e:
        return f"I can help with registering customers/organizations, reviewing duplicates, running batch scans, and viewing stats. Could you rephrase your request? (Bedrock unavailable: {e})"


# ---------------------------------------------------------------------------
# Page Config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="AgentDedup — Customer Data Deduplication",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Sidebar — Chatbot
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 🤖 Dedup Assistant")
    st.caption("Ask questions or give commands in natural language.")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = [
            {
                "role": "assistant",
                "content": (
                    "Hi! I'm the AgentDedup assistant. I can help you:\n"
                    "- **Register** a customer or organization\n"
                    "- **Show** duplicate reviews\n"
                    "- **Approve/Reject** a review\n"
                    "- **Scan** for batch duplicates\n"
                    "- **Show** dashboard stats\n\n"
                    "Try: *\"Register John Smith from OneCRM with email john@test.com\"*"
                ),
            }
        ]

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if user_input := st.chat_input("Type a command or question...", key="chat_input"):
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        action, params = parse_chat_command(user_input)
        response = ""

        if action == "register":
            with st.spinner("Registering customer..."):
                result = call_register(params)
            status = result.get("status", "error")
            if status == "new_record":
                response = f"✅ **New record created!** Customer ID: `{result.get('customerId', 'N/A')}`"
            elif status in ("review_pending", "duplicate_found"):
                score = safe_float(result.get("confidenceScore"))
                response = (
                    f"⚠️ **Duplicate detected!** Confidence: {score:.0%}\n"
                    f"Review ID: `{result.get('reviewId', 'N/A')}`\n"
                    f"Check the **Duplicate Reviews** tab."
                )
            else:
                response = f"❌ Error: {result.get('error', json.dumps(result, default=decimal_default))}"

        elif action == "approve":
            with st.spinner("Approving merge..."):
                result = call_approve(params["reviewId"])
            if result.get("status") == "approved":
                response = f"✅ **Merge approved!** Review `{params['reviewId']}` has been processed."
            else:
                response = f"Result: {json.dumps(result, default=decimal_default)}"

        elif action == "reject":
            with st.spinner("Rejecting merge..."):
                result = call_reject(params["reviewId"])
            if result.get("status") == "rejected":
                response = f"✅ **Merge rejected.** Review `{params['reviewId']}` marked as non-match."
            else:
                response = f"Result: {json.dumps(result, default=decimal_default)}"

        elif action == "count_reviews":
            reviews = fetch_reviews_dynamo()
            pending = [r for r in reviews if r.get("status") == "pending"]
            response = f"📊 There are **{len(pending)}** pending reviews out of **{len(reviews)}** total."

        elif action == "show_reviews":
            response = "📋 Switching to the **Duplicate Reviews** tab. Check the main area!"
            st.session_state["active_tab"] = 1

        elif action == "count_customers":
            customers = fetch_customers()
            active = [c for c in customers if c.get("status") == "active"]
            response = f"📊 There are **{len(active)}** active customers out of **{len(customers)}** total records."

        elif action == "show_accounts":
            response = "📋 Switching to the **Accounts** tab. Check the main area!"
            st.session_state["active_tab"] = 0

        elif action == "batch_scan":
            with st.spinner("Triggering batch scan..."):
                result = trigger_batch()
            if "executionArn" in result:
                st.session_state["batch_execution_arn"] = result["executionArn"]
                response = (
                    f"🚀 **Batch scan started!**\n"
                    f"Execution ARN: `{result['executionArn']}`\n"
                    f"Check the **Batch Scan** tab for progress."
                )
            else:
                response = f"❌ Error: {result.get('error', 'Unknown error')}"

        elif action == "show_dashboard":
            response = "📊 Switching to the **Dashboard** tab!"
            st.session_state["active_tab"] = 4

        else:
            with st.spinner("Thinking..."):
                response = ask_bedrock(user_input)

        st.session_state.chat_history.append({"role": "assistant", "content": response})
        with st.chat_message("assistant"):
            st.markdown(response)

    st.divider()
    st.caption(f"🔗 API: `{API_URL}`")
    st.caption(f"📦 Region: `{AWS_REGION}`")


# ---------------------------------------------------------------------------
# Main Area — Title and Tabs
# ---------------------------------------------------------------------------
st.title("🔍 AgentDedup — Customer Data Deduplication")
st.caption("AI-powered duplicate detection with human-in-the-loop review — Person & Organization")

tab_accounts, tab_reviews, tab_register, tab_batch, tab_dashboard = st.tabs(
    ["📇 Accounts", "🔀 Duplicate Reviews", "➕ Register Customer", "📦 Batch Scan", "📊 Dashboard"]
)


# ===================================================================
# TAB 1: Accounts (with Party Type column and filter)
# ===================================================================
with tab_accounts:
    st.subheader("Customer Records")

    col_search, col_type_filter, col_refresh = st.columns([2, 1, 1])
    with col_search:
        search_term = st.text_input(
            "🔎 Search by name or email", placeholder="e.g. Chris James or Pearson...", key="acct_search"
        )
    with col_type_filter:
        party_type_filter = st.selectbox(
            "Party Type", ["All", "Person", "Organization"], key="acct_party_type"
        )
    with col_refresh:
        st.write("")  # spacer
        st.write("")
        refresh_acct = st.button("🔄 Refresh", key="refresh_accounts")

    customers = fetch_customers()

    if customers:
        rows = []
        for c in customers:
            pt = get_party_type(c)
            name = format_record_name(c)
            rows.append(
                {
                    "Customer ID": c.get("customerId", ""),
                    "Party Type": pt,
                    "Name": name,
                    "Email": c.get("email", "N/A") or "N/A",
                    "Phone": c.get("phone", "N/A") or "N/A",
                    "Source System": c.get("sourceSystem", ""),
                    "Status": c.get("status", ""),
                    "Created": c.get("createdAt", "")[:10] if c.get("createdAt") else "",
                }
            )
        df = pd.DataFrame(rows)

        # Apply party type filter
        if party_type_filter == "Person":
            df = df[df["Party Type"] == "PERSON"]
        elif party_type_filter == "Organization":
            df = df[df["Party Type"] == "ORGANIZATION"]

        # Apply search filter
        if search_term:
            mask = df["Name"].str.contains(search_term, case=False, na=False) | df["Email"].str.contains(
                search_term, case=False, na=False
            )
            df = df[mask]

        # Sort by name
        df = df.sort_values("Name").reset_index(drop=True)

        # Color-code status
        def style_status(val):
            if val == "active":
                return "background-color: #d4edda; color: #155724"
            elif val == "merged":
                return "background-color: #fff3cd; color: #856404"
            return ""

        def style_party_type(val):
            if val == "ORGANIZATION":
                return "background-color: #d1ecf1; color: #0c5460"
            return ""

        st.dataframe(
            df.style.map(style_status, subset=["Status"]).map(style_party_type, subset=["Party Type"]),
            use_container_width=True,
            height=500,
        )
        st.caption(f"Showing {len(df)} of {len(customers)} records")
    else:
        st.info("No customer records found. Seed data or register a customer first.")


# ===================================================================
# TAB 2: Duplicate Reviews (with party type and cumulative score)
# ===================================================================
with tab_reviews:
    st.subheader("Pending Duplicate Reviews")

    col_filter, col_pt_filter, col_refresh2 = st.columns([2, 1, 1])
    with col_filter:
        status_filter = st.selectbox(
            "Filter by status", ["pending", "all", "approved", "rejected"], key="review_filter"
        )
    with col_pt_filter:
        review_pt_filter = st.selectbox(
            "Party Type", ["All", "Person", "Organization"], key="review_party_type"
        )
    with col_refresh2:
        st.write("")
        st.write("")
        st.button("🔄 Refresh", key="refresh_reviews")

    reviews = fetch_reviews_dynamo()

    if status_filter != "all":
        reviews = [r for r in reviews if r.get("status") == status_filter]

    # Filter by party type
    if review_pt_filter == "Person":
        reviews = [r for r in reviews if get_party_type(r.get("incomingRecord", {})) == "PERSON"]
    elif review_pt_filter == "Organization":
        reviews = [r for r in reviews if get_party_type(r.get("incomingRecord", {})) == "ORGANIZATION"]

    reviews.sort(key=lambda r: (0 if r.get("status") == "pending" else 1, r.get("createdAt", "")), reverse=False)

    if reviews:
        st.caption(f"Showing {len(reviews)} review(s)")

        for idx, review in enumerate(reviews):
            review_id = review.get("reviewId", "N/A")
            score = safe_float(review.get("confidenceScore"))
            classification = review.get("confidenceClassification", "N/A")
            method = review.get("matchingMethod", "N/A")
            agent = review.get("sourceAgent", "N/A")
            status = review.get("status", "N/A")
            contributing = review.get("contributingFields", [])
            incoming = review.get("incomingRecord", {})
            matched = review.get("matchedRecord", {})
            cumulative_score = review.get("cumulativeScore")
            review_party_type = get_party_type(incoming)

            # Score color
            if review_party_type == "ORGANIZATION":
                # For orgs, use cumulative thresholds
                cum = safe_float(cumulative_score) if cumulative_score is not None else score * 866
                if cum >= 200:
                    score_color = "🟢"
                elif cum >= 144:
                    score_color = "🟡"
                else:
                    score_color = "🔴"
                score_display = f"{score:.0%} (cum: {int(cum)})"
            else:
                if score >= 0.9:
                    score_color = "🟢"
                elif score >= 0.6:
                    score_color = "🟡"
                else:
                    score_color = "🔴"
                score_display = f"{score:.0%}"

            status_emoji = {"pending": "⏳", "approved": "✅", "rejected": "❌"}.get(status, "❓")
            type_badge = "🏢" if review_party_type == "ORGANIZATION" else "👤"

            with st.expander(
                f"{status_emoji} {type_badge} {format_record_name(incoming)} ↔ {format_record_name(matched)} — "
                f"{score_color} {score_display} ({classification}) — {status.upper()}",
                expanded=(status == "pending"),
            ):
                # Metadata row
                if review_party_type == "ORGANIZATION":
                    meta_cols = st.columns(5)
                    meta_cols[0].metric("Confidence", f"{score:.0%}")
                    meta_cols[1].metric("Cumulative", str(int(safe_float(cumulative_score))) if cumulative_score else "N/A")
                    meta_cols[2].metric("Method", method)
                    meta_cols[3].metric("Agent", agent)
                    meta_cols[4].metric("Party Type", "Organization")
                else:
                    meta_cols = st.columns(4)
                    meta_cols[0].metric("Confidence", f"{score:.0%}")
                    meta_cols[1].metric("Method", method)
                    meta_cols[2].metric("Agent", agent)
                    meta_cols[3].metric("Status", status.title())

                if contributing:
                    if isinstance(contributing, list):
                        st.caption(f"Contributing fields: {', '.join(str(f) for f in contributing)}")
                    else:
                        st.caption(f"Contributing fields: {contributing}")

                st.divider()

                # Side-by-side comparison
                left, right = st.columns(2)

                if review_party_type == "ORGANIZATION":
                    with left:
                        st.markdown("**📥 Incoming Organization**")
                        st.markdown(f"**Party Name:** {incoming.get('partyName', 'N/A')}")
                        st.markdown(f"**Tax Reg #:** {incoming.get('taxRegistrationNum', 'N/A') or 'N/A'}")
                        st.markdown(f"**Taxpayer ID:** {incoming.get('taxpayerId', 'N/A') or 'N/A'}")
                        st.markdown(f"**MDR PID:** {incoming.get('mdrPidId', 'N/A') or 'N/A'}")
                        st.markdown(f"**Match Market:** {incoming.get('matchMarket', 'N/A') or 'N/A'}")
                        st.markdown(f"**Address:** {format_address(incoming.get('address'))}")
                        st.markdown(f"**Source:** {incoming.get('sourceSystem', 'N/A')}")

                    with right:
                        st.markdown("**📄 Matched Organization**")
                        st.markdown(f"**Party Name:** {matched.get('partyName', 'N/A')}")
                        st.markdown(f"**Tax Reg #:** {matched.get('taxRegistrationNum', 'N/A') or 'N/A'}")
                        st.markdown(f"**Taxpayer ID:** {matched.get('taxpayerId', 'N/A') or 'N/A'}")
                        st.markdown(f"**MDR PID:** {matched.get('mdrPidId', 'N/A') or 'N/A'}")
                        st.markdown(f"**Match Market:** {matched.get('matchMarket', 'N/A') or 'N/A'}")
                        st.markdown(f"**Address:** {format_address(matched.get('address'))}")
                        st.markdown(f"**Source:** {matched.get('sourceSystem', 'N/A')}")
                        if matched.get("customerId"):
                            st.caption(f"ID: {matched['customerId']}")
                else:
                    with left:
                        st.markdown("**📥 Incoming Record**")
                        st.markdown(f"**Name:** {format_record_name(incoming)}")
                        st.markdown(f"**Email:** {incoming.get('email', 'N/A') or 'N/A'}")
                        st.markdown(f"**Phone:** {incoming.get('phone', 'N/A') or 'N/A'}")
                        st.markdown(f"**DOB:** {incoming.get('dateOfBirth', 'N/A') or 'N/A'}")
                        st.markdown(f"**Address:** {format_address(incoming.get('address'))}")
                        st.markdown(f"**Source:** {incoming.get('sourceSystem', 'N/A')}")

                    with right:
                        st.markdown("**📄 Matched Record**")
                        st.markdown(f"**Name:** {format_record_name(matched)}")
                        st.markdown(f"**Email:** {matched.get('email', 'N/A') or 'N/A'}")
                        st.markdown(f"**Phone:** {matched.get('phone', 'N/A') or 'N/A'}")
                        st.markdown(f"**DOB:** {matched.get('dateOfBirth', 'N/A') or 'N/A'}")
                        st.markdown(f"**Address:** {format_address(matched.get('address'))}")
                        st.markdown(f"**Source:** {matched.get('sourceSystem', 'N/A')}")
                        if matched.get("customerId"):
                            st.caption(f"ID: {matched['customerId']}")

                # Action buttons (only for pending)
                if status == "pending":
                    st.divider()
                    btn_cols = st.columns([1, 1, 4])
                    with btn_cols[0]:
                        if st.button("✅ Approve", key=f"approve_{review_id}_{idx}", type="primary"):
                            with st.spinner("Approving merge..."):
                                result = call_approve(review_id)
                            if result.get("status") == "approved":
                                st.success("Merge approved! Refresh to see updated status.")
                                st.rerun()
                            else:
                                st.error(f"Error: {json.dumps(result, default=decimal_default)}")
                    with btn_cols[1]:
                        if st.button("❌ Reject", key=f"reject_{review_id}_{idx}"):
                            with st.spinner("Rejecting..."):
                                result = call_reject(review_id)
                            if result.get("status") == "rejected":
                                st.success("Merge rejected. Refresh to see updated status.")
                                st.rerun()
                            else:
                                st.error(f"Error: {json.dumps(result, default=decimal_default)}")

                st.caption(f"Review ID: `{review_id}` | Created: {review.get('createdAt', 'N/A')}")
    else:
        st.info("No reviews found matching the selected filter.")


# ===================================================================
# TAB 3: Register Customer (with Party Type toggle)
# ===================================================================
with tab_register:
    st.subheader("Register New Customer / Organization")
    st.caption("Submit a record through the Intercept Agent")

    # Party type selector outside the form for dynamic field switching
    reg_party_type = st.radio(
        "Party Type", ["Person", "Organization"], horizontal=True, key="reg_party_type"
    )

    if reg_party_type == "Person":
        with st.form("register_person_form", clear_on_submit=False):
            col1, col2 = st.columns(2)

            with col1:
                first_name = st.text_input("First Name *", placeholder="", key="p_fn")
                last_name = st.text_input("Last Name *", placeholder="", key="p_ln")
                email = st.text_input("Email", placeholder="", key="p_email")
                phone = st.text_input("Phone", placeholder="", key="p_phone")
                dob = st.text_input("Date of Birth", placeholder="YYYY-MM-DD", key="p_dob")

            with col2:
                source_system = st.selectbox("Source System *", ["OneCRM", "NES"], key="p_src")
                street = st.text_input("Street", placeholder="", key="p_street")
                city = st.text_input("City", placeholder="", key="p_city")
                state = st.text_input("State", placeholder="", key="p_state")
                postal_code = st.text_input("Postal Code", placeholder="", key="p_pc")
                country = st.text_input("Country", value="US", key="p_country")

            submitted = st.form_submit_button("🚀 Register Person", type="primary")

        if submitted:
            if not first_name or not last_name:
                st.error("First Name and Last Name are required.")
            else:
                payload = {
                    "firstName": first_name,
                    "lastName": last_name,
                    "sourceSystem": source_system,
                    "partyType": "PERSON",
                }
                if email:
                    payload["email"] = email
                if phone:
                    payload["phone"] = phone
                if dob:
                    payload["dateOfBirth"] = dob

                address = {}
                if street:
                    address["street"] = street
                if city:
                    address["city"] = city
                if state:
                    address["state"] = state
                if postal_code:
                    address["postalCode"] = postal_code
                if country:
                    address["country"] = country
                if address:
                    payload["address"] = address

                with st.spinner("Submitting to Intercept Agent... (may take up to 30s)"):
                    result = call_register(payload)

                st.divider()
                status = result.get("status", "error")

                if status == "new_record":
                    st.success("✅ New person record created!")
                    res_cols = st.columns(3)
                    res_cols[0].metric("Status", "New Record")
                    res_cols[1].metric("Customer ID", result.get("customerId", "N/A")[:12] + "...")
                    res_cols[2].metric("Confidence", f"{safe_float(result.get('confidenceScore')):.0%}")

                elif status in ("review_pending", "duplicate_found"):
                    st.warning("⚠️ Potential duplicate detected — routed to review queue!")
                    res_cols = st.columns(4)
                    res_cols[0].metric("Status", "Review Pending")
                    score = safe_float(result.get("confidenceScore"))
                    res_cols[1].metric("Confidence", f"{score:.0%}")
                    res_cols[2].metric("Classification", result.get("confidenceClassification", "N/A"))
                    res_cols[3].metric("Agent", result.get("sourceAgent", "intercept"))

                    if result.get("reviewId"):
                        st.info(f"Review ID: `{result['reviewId']}`")
                    if result.get("matchedRecord"):
                        matched = result["matchedRecord"]
                        if isinstance(matched, str):
                            st.markdown(f"**Matched existing record:** {matched}")
                        else:
                            st.markdown("**Matched existing record:**")
                            st.markdown(
                                f"- **Name:** {format_record_name(matched)}\n"
                                f"- **Email:** {matched.get('email', 'N/A')}\n"
                                f"- **Source:** {matched.get('sourceSystem', 'N/A')}"
                            )
                    if result.get("matchingMethod"):
                        st.caption(f"Matching method: {result['matchingMethod']}")
                else:
                    st.error(f"❌ Error: {result.get('error', json.dumps(result, default=decimal_default))}")

                with st.expander("Raw API Response"):
                    st.json(json.loads(json.dumps(result, default=decimal_default)))

    else:
        # Organization registration form
        with st.form("register_org_form", clear_on_submit=False):
            col1, col2 = st.columns(2)

            with col1:
                party_name = st.text_input("Party Name (Organization) *", placeholder="e.g. Pearson Education Inc.", key="o_name")
                tax_reg = st.text_input("Tax Registration Number", placeholder="e.g. TAX-PE-2024-001", key="o_taxreg")
                taxpayer_id = st.text_input("Taxpayer ID", placeholder="e.g. TP-84-1234567", key="o_tpid")
                mdr_pid = st.text_input("MDR PID ID", placeholder="e.g. MDR-PE-0001", key="o_mdr")
                match_market = st.text_input("Match Market", placeholder="e.g. US-EDUCATION", key="o_mm")

            with col2:
                source_system_org = st.selectbox("Source System *", ["OneCRM", "NES"], key="o_src")
                street_org = st.text_input("Street", placeholder="", key="o_street")
                city_org = st.text_input("City", placeholder="", key="o_city")
                state_org = st.text_input("State", placeholder="", key="o_state")
                postal_code_org = st.text_input("Postal Code", placeholder="", key="o_pc")
                country_org = st.text_input("Country", value="US", key="o_country")

            submitted_org = st.form_submit_button("🚀 Register Organization", type="primary")

        if submitted_org:
            if not party_name:
                st.error("Party Name is required for organizations.")
            else:
                payload = {
                    "partyType": "ORGANIZATION",
                    "partyName": party_name,
                    "sourceSystem": source_system_org,
                }
                if tax_reg:
                    payload["taxRegistrationNum"] = tax_reg
                if taxpayer_id:
                    payload["taxpayerId"] = taxpayer_id
                if mdr_pid:
                    payload["mdrPidId"] = mdr_pid
                if match_market:
                    payload["matchMarket"] = match_market

                address = {}
                if street_org:
                    address["street"] = street_org
                if city_org:
                    address["city"] = city_org
                if state_org:
                    address["state"] = state_org
                if postal_code_org:
                    address["postalCode"] = postal_code_org
                if country_org:
                    address["country"] = country_org
                if address:
                    payload["address"] = address

                with st.spinner("Submitting organization to Intercept Agent... (may take up to 30s)"):
                    result = call_register(payload)

                st.divider()
                status = result.get("status", "error")

                if status == "new_record":
                    st.success("✅ New organization record created!")
                    res_cols = st.columns(3)
                    res_cols[0].metric("Status", "New Record")
                    res_cols[1].metric("Customer ID", result.get("customerId", "N/A")[:12] + "...")
                    res_cols[2].metric("Confidence", f"{safe_float(result.get('confidenceScore')):.0%}")

                elif status in ("review_pending", "duplicate_found"):
                    st.warning("⚠️ Potential duplicate organization detected — routed to review queue!")
                    res_cols = st.columns(4)
                    res_cols[0].metric("Status", "Review Pending")
                    score = safe_float(result.get("confidenceScore"))
                    res_cols[1].metric("Confidence", f"{score:.0%}")
                    res_cols[2].metric("Classification", result.get("confidenceClassification", "N/A"))
                    res_cols[3].metric("Agent", result.get("sourceAgent", "intercept"))

                    if result.get("reviewId"):
                        st.info(f"Review ID: `{result['reviewId']}`")
                    if result.get("matchingMethod"):
                        st.caption(f"Matching method: {result['matchingMethod']}")
                else:
                    st.error(f"❌ Error: {result.get('error', json.dumps(result, default=decimal_default))}")

                with st.expander("Raw API Response"):
                    st.json(json.loads(json.dumps(result, default=decimal_default)))

    # Quick-fill demo scenarios
    st.divider()
    st.markdown("**Quick Demo Scenarios:**")
    demo_cols = st.columns(3)
    with demo_cols[0]:
        st.markdown(
            "**Scenario 1 — New Unique Person**\n"
            "- Enter any name + unique email\n"
            "- Source: `OneCRM`\n"
            "- Expected: `new_record`"
        )
    with demo_cols[1]:
        st.markdown(
            "**Scenario 2 — Duplicate Person**\n"
            "- Use SAME email as Scenario 1\n"
            "- Change source to `NES`\n"
            "- Expected: `review_pending` (~93%)"
        )
    with demo_cols[2]:
        st.markdown(
            "**Scenario 5 — Org Duplicate**\n"
            "- Switch to Organization\n"
            "- Enter 'Pearson Education' + same Tax ID\n"
            "- Expected: `review_pending` (high cumulative)"
        )


# ===================================================================
# TAB 4: Batch Scan
# ===================================================================
with tab_batch:
    st.subheader("Batch Deduplication Scan")
    st.caption("Trigger the Clean Agent to scan existing records for historical duplicates (Scenario 3)")

    st.markdown(
        f"**Batch Configuration:**\n"
        f"- State Machine: `{BATCH_STATE_MACHINE_ARN.split(':')[-1]}`\n"
        f"- Input Bucket: `{BATCH_INPUT_BUCKET}`\n"
        f"- Input Key: `{BATCH_INPUT_KEY}`\n"
        f"- Includes both Person and Organization records"
    )

    st.divider()

    if st.button("🚀 Start Batch Scan", type="primary", key="start_batch"):
        with st.spinner("Starting batch execution..."):
            result = trigger_batch()
        if "executionArn" in result:
            st.session_state["batch_execution_arn"] = result["executionArn"]
            st.success(f"Batch scan started! Execution ARN: `{result['executionArn']}`")
        else:
            st.error(f"Failed to start batch: {result.get('error', 'Unknown error')}")

    if "batch_execution_arn" in st.session_state:
        arn = st.session_state["batch_execution_arn"]
        st.divider()
        st.markdown(f"**Tracking Execution:** `{arn.split(':')[-1]}`")

        if st.button("🔄 Check Status", key="check_batch_status"):
            with st.spinner("Checking..."):
                status_result = get_execution_status(arn)

            exec_status = status_result.get("status", "UNKNOWN")
            status_colors = {
                "RUNNING": "🔵",
                "SUCCEEDED": "🟢",
                "FAILED": "🔴",
                "TIMED_OUT": "🟠",
                "ABORTED": "⚫",
            }
            emoji = status_colors.get(exec_status, "❓")
            st.markdown(f"### {emoji} Status: **{exec_status}**")

            if exec_status == "SUCCEEDED":
                st.success("Batch scan completed successfully!")
                output = status_result.get("output", {})
                if output:
                    summary = output.get("summary", {}).get("summary", {})
                    if summary:
                        sum_cols = st.columns(4)
                        sum_cols[0].metric("Records Scanned", summary.get("totalRecords", "N/A"))
                        sum_cols[1].metric("Duplicates Found", summary.get("duplicatesIdentified", "N/A"))
                        sum_cols[2].metric("Reviews Created", summary.get("reviewsCreated", "N/A"))
                        sum_cols[3].metric("New Records", summary.get("newRecordsCreated", "N/A"))

                    with st.expander("Full Output"):
                        st.json(json.loads(json.dumps(output, default=decimal_default)))

                st.info("Check the **Duplicate Reviews** tab for new reviews from the Clean Agent.")

            elif exec_status == "RUNNING":
                st.info("Batch is still running. Check back in 30-60 seconds.")

            elif exec_status == "FAILED":
                st.error("Batch execution failed. Check CloudWatch logs for details.")

            if "error" in status_result:
                st.error(status_result["error"])

    # Show batch reports from S3
    st.divider()
    st.markdown("**Recent Batch Reports:**")
    try:
        s3 = get_s3_client()
        resp = s3.list_objects_v2(
            Bucket="dedup-s3-dedup-batch-reports", Prefix="batch-reports/", MaxKeys=10
        )
        objects = resp.get("Contents", [])
        if objects:
            objects.sort(key=lambda o: o["LastModified"], reverse=True)
            for obj in objects[:5]:
                key = obj["Key"]
                size = obj["Size"]
                modified = obj["LastModified"].strftime("%Y-%m-%d %H:%M:%S")
                st.caption(f"📄 `{key}` — {size} bytes — {modified}")
        else:
            st.caption("No batch reports found yet.")
    except ClientError:
        st.caption("Could not list batch reports (bucket may not exist or no permissions).")


# ===================================================================
# TAB 5: Dashboard (with Person vs Organization metrics)
# ===================================================================
with tab_dashboard:
    st.subheader("System Dashboard")

    # Fetch data for stats
    all_customers = fetch_customers()
    all_reviews = fetch_reviews_dynamo()

    active_customers = [c for c in all_customers if c.get("status") == "active"]
    merged_customers = [c for c in all_customers if c.get("status") == "merged"]
    pending_reviews = [r for r in all_reviews if r.get("status") == "pending"]
    approved_reviews = [r for r in all_reviews if r.get("status") == "approved"]
    rejected_reviews = [r for r in all_reviews if r.get("status") == "rejected"]

    # Party type breakdown
    person_records = [c for c in all_customers if get_party_type(c) == "PERSON"]
    org_records = [c for c in all_customers if get_party_type(c) == "ORGANIZATION"]

    # Top-level metrics
    st.markdown("### Key Metrics")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Records", len(all_customers), f"{len(active_customers)} active")
    m2.metric("Person Records", len(person_records), f"👤")
    m3.metric("Org Records", len(org_records), f"🏢")
    m4.metric("Pending Reviews", len(pending_reviews))
    m5.metric("Merges Completed", len(approved_reviews))

    st.divider()

    # Charts row
    chart1, chart2 = st.columns(2)

    with chart1:
        st.markdown("#### Records by Party Type")
        pt_counts = {"Person": len(person_records), "Organization": len(org_records)}
        if any(pt_counts.values()):
            fig_pt = go.Figure(
                data=[
                    go.Pie(
                        labels=list(pt_counts.keys()),
                        values=list(pt_counts.values()),
                        marker_colors=["#007bff", "#17a2b8"],
                        hole=0.4,
                    )
                ]
            )
            fig_pt.update_layout(height=300, margin=dict(t=20, b=20, l=20, r=20))
            st.plotly_chart(fig_pt, use_container_width=True)
        else:
            st.info("No customer data available.")

    with chart2:
        st.markdown("#### Customer Status Breakdown")
        status_counts = {"Active": len(active_customers), "Merged": len(merged_customers)}
        if any(status_counts.values()):
            fig_status = go.Figure(
                data=[
                    go.Pie(
                        labels=list(status_counts.keys()),
                        values=list(status_counts.values()),
                        marker_colors=["#28a745", "#ffc107"],
                        hole=0.4,
                    )
                ]
            )
            fig_status.update_layout(height=300, margin=dict(t=20, b=20, l=20, r=20))
            st.plotly_chart(fig_status, use_container_width=True)
        else:
            st.info("No customer data available.")

    st.divider()

    # Second row of charts
    chart3, chart4 = st.columns(2)

    with chart3:
        st.markdown("#### Review Status Breakdown")
        review_counts = {
            "Pending": len(pending_reviews),
            "Approved": len(approved_reviews),
            "Rejected": len(rejected_reviews),
        }
        if any(review_counts.values()):
            fig_reviews = go.Figure(
                data=[
                    go.Pie(
                        labels=list(review_counts.keys()),
                        values=list(review_counts.values()),
                        marker_colors=["#007bff", "#28a745", "#dc3545"],
                        hole=0.4,
                    )
                ]
            )
            fig_reviews.update_layout(height=300, margin=dict(t=20, b=20, l=20, r=20))
            st.plotly_chart(fig_reviews, use_container_width=True)
        else:
            st.info("No review data available.")

    with chart4:
        st.markdown("#### Confidence Score Distribution")
        scores = [safe_float(r.get("confidenceScore")) for r in all_reviews if r.get("confidenceScore") is not None]
        if scores:
            fig_scores = go.Figure(
                data=[
                    go.Histogram(
                        x=scores,
                        nbinsx=10,
                        marker_color="#FF6B35",
                        xbins=dict(start=0, end=1.0, size=0.1),
                    )
                ]
            )
            fig_scores.update_layout(
                height=300,
                margin=dict(t=20, b=20, l=20, r=20),
                xaxis_title="Confidence Score",
                yaxis_title="Count",
                xaxis=dict(range=[0, 1.05]),
            )
            st.plotly_chart(fig_scores, use_container_width=True)
        else:
            st.info("No confidence score data available.")

    st.divider()

    # Third row
    chart5, chart6 = st.columns(2)

    with chart5:
        st.markdown("#### Reviews by Agent")
        agent_counts = {}
        for r in all_reviews:
            agent = r.get("sourceAgent", "unknown")
            agent_counts[agent] = agent_counts.get(agent, 0) + 1
        if agent_counts:
            fig_agents = go.Figure(
                data=[
                    go.Bar(
                        x=list(agent_counts.keys()),
                        y=list(agent_counts.values()),
                        marker_color=["#FF6B35", "#4ECDC4", "#95E1D3"][: len(agent_counts)],
                    )
                ]
            )
            fig_agents.update_layout(
                height=300,
                margin=dict(t=20, b=20, l=20, r=20),
                xaxis_title="Agent",
                yaxis_title="Count",
            )
            st.plotly_chart(fig_agents, use_container_width=True)
        else:
            st.info("No agent data available.")

    with chart6:
        st.markdown("#### Records by Source System")
        source_counts = {}
        for c in all_customers:
            src = c.get("sourceSystem", "Unknown")
            source_counts[src] = source_counts.get(src, 0) + 1
        if source_counts:
            fig_src = go.Figure(
                data=[
                    go.Bar(
                        x=list(source_counts.keys()),
                        y=list(source_counts.values()),
                        marker_color=["#6f42c1", "#e83e8c"][: len(source_counts)],
                    )
                ]
            )
            fig_src.update_layout(
                height=300,
                margin=dict(t=20, b=20, l=20, r=20),
                xaxis_title="Source System",
                yaxis_title="Count",
            )
            st.plotly_chart(fig_src, use_container_width=True)
        else:
            st.info("No source system data available.")
