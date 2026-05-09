"""
AgentDedup — Customer Data Deduplication Dashboard (Gradio)
Gradio UI for the Customer Data Deduplication prototype.
Calls existing API Gateway endpoints and reads DynamoDB directly for display.
Supports both PERSON and ORGANIZATION party types.
No WebSocket required — works on AWS App Runner.
"""

import json
import os
import re
import time
from datetime import datetime, timezone
from decimal import Decimal

import boto3
import gradio as gr
import pandas as pd
import plotly.graph_objects as go
import requests
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
BEDROCK_MODEL = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0")
BATCH_STATE_MACHINE_ARN = os.getenv(
    "BATCH_STATE_MACHINE_ARN",
    "arn:aws:states:us-east-1:553556337417:stateMachine:dedup-app-dedup-batch",
)
BATCH_INPUT_BUCKET = os.getenv("BATCH_INPUT_BUCKET", "dedup-s3-dedup-batch-input")
BATCH_INPUT_KEY = os.getenv("BATCH_INPUT_KEY", "scenario3-existing-dupes.json")

API_HEADERS = {"Content-Type": "application/json", "x-api-key": API_KEY}

# ---------------------------------------------------------------------------
# AWS Clients
# ---------------------------------------------------------------------------
_dynamodb = None
_sfn = None
_bedrock = None
_s3 = None


def get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    return _dynamodb


def get_sfn_client():
    global _sfn
    if _sfn is None:
        _sfn = boto3.client("stepfunctions", region_name=AWS_REGION)
    return _sfn


def get_bedrock_client():
    global _bedrock
    if _bedrock is None:
        _bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION)
    return _bedrock


def get_s3_client():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3", region_name=AWS_REGION)
    return _s3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def decimal_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def safe_float(val, default=0.0):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def format_record_name(record):
    party_name = record.get("partyName")
    if party_name:
        return party_name
    first = record.get("firstName", "")
    last = record.get("lastName", "")
    return f"{first} {last}".strip() or "Unknown"


def format_address(addr):
    if not addr or not isinstance(addr, dict):
        return "N/A"
    parts = [addr.get("street", ""), addr.get("city", ""), addr.get("state", ""),
             addr.get("postalCode", ""), addr.get("country", "")]
    return ", ".join(p for p in parts if p) or "N/A"


def get_party_type(record):
    return record.get("partyType", "PERSON").upper()


# ---------------------------------------------------------------------------
# Data Fetching
# ---------------------------------------------------------------------------
def fetch_customers():
    table = get_dynamodb().Table(CUSTOMER_TABLE)
    items = []
    try:
        resp = table.scan()
        items.extend(resp.get("Items", []))
        while "LastEvaluatedKey" in resp:
            resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
            items.extend(resp.get("Items", []))
    except ClientError:
        pass
    return items


def fetch_reviews():
    table = get_dynamodb().Table(REVIEW_TABLE)
    items = []
    try:
        resp = table.scan()
        items.extend(resp.get("Items", []))
        while "LastEvaluatedKey" in resp:
            resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
            items.extend(resp.get("Items", []))
    except ClientError:
        pass
    return items


def _parse_sfn_output(text):
    result = {}
    text = text.strip().strip("{}")
    parts, depth, current = [], 0, ""
    for ch in text:
        if ch == "{": depth += 1; current += ch
        elif ch == "}": depth -= 1; current += ch
        elif ch == "," and depth == 0: parts.append(current.strip()); current = ""
        else: current += ch
    if current.strip():
        parts.append(current.strip())
    for part in parts:
        if "=" in part:
            key, _, value = part.partition("=")
            key, value = key.strip(), value.strip()
            if value == "null": value = None
            elif value.replace(".", "", 1).isdigit(): value = float(value)
            result[key] = value
    return result


def call_register(payload):
    try:
        resp = requests.post(f"{API_URL}/register", headers=API_HEADERS, json=payload, timeout=30)
        try:
            return resp.json()
        except Exception:
            return _parse_sfn_output(resp.text)
    except requests.exceptions.Timeout:
        return {"error": "Request timed out (agent processing may take up to 30s)"}
    except Exception as e:
        return {"error": str(e)}


def call_approve(review_id):
    try:
        resp = requests.post(f"{API_URL}/reviews/{review_id}/approve", headers=API_HEADERS, timeout=30)
        try:
            return resp.json()
        except Exception:
            return _parse_sfn_output(resp.text)
    except Exception as e:
        return {"error": str(e)}


def call_reject(review_id):
    try:
        resp = requests.post(f"{API_URL}/reviews/{review_id}/reject", headers=API_HEADERS, timeout=30)
        try:
            return resp.json()
        except Exception:
            return _parse_sfn_output(resp.text)
    except Exception as e:
        return {"error": str(e)}


def trigger_batch():
    try:
        client = get_sfn_client()
        resp = client.start_execution(
            stateMachineArn=BATCH_STATE_MACHINE_ARN,
            input=json.dumps({"bucket": BATCH_INPUT_BUCKET, "key": BATCH_INPUT_KEY}),
        )
        return {"executionArn": resp["executionArn"], "startDate": resp["startDate"].isoformat()}
    except ClientError as e:
        return {"error": e.response["Error"]["Message"]}


# ---------------------------------------------------------------------------
# Tab: Accounts
# ---------------------------------------------------------------------------
def load_accounts(search_term, party_type_filter):
    customers = fetch_customers()
    if not customers:
        return pd.DataFrame()
    rows = []
    for c in customers:
        pt = get_party_type(c)
        rows.append({
            "Customer ID": c.get("customerId", "")[:16] + "...",
            "Party Type": pt,
            "Name": format_record_name(c),
            "Email": c.get("email", "N/A") or "N/A",
            "Phone": c.get("phone", "N/A") or "N/A",
            "Source": c.get("sourceSystem", ""),
            "Status": c.get("status", ""),
            "Created": c.get("createdAt", "")[:10] if c.get("createdAt") else "",
        })
    df = pd.DataFrame(rows)
    if party_type_filter == "Person":
        df = df[df["Party Type"] == "PERSON"]
    elif party_type_filter == "Organization":
        df = df[df["Party Type"] == "ORGANIZATION"]
    if search_term:
        mask = df["Name"].str.contains(search_term, case=False, na=False) | df["Email"].str.contains(search_term, case=False, na=False)
        df = df[mask]
    return df.sort_values("Name").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Tab: Reviews
# ---------------------------------------------------------------------------
def load_reviews(status_filter, party_type_filter):
    reviews = fetch_reviews()
    if status_filter != "all":
        reviews = [r for r in reviews if r.get("status") == status_filter]
    if party_type_filter == "Person":
        reviews = [r for r in reviews if get_party_type(r.get("incomingRecord", {})) == "PERSON"]
    elif party_type_filter == "Organization":
        reviews = [r for r in reviews if get_party_type(r.get("incomingRecord", {})) == "ORGANIZATION"]

    if not reviews:
        return "No reviews found.", pd.DataFrame(), gr.update(choices=[], value=None)

    rows = []
    dropdown_choices = []
    for i, r in enumerate(reviews, 1):
        inc = r.get("incomingRecord", {})
        matched = r.get("matchedRecord", {})
        score = safe_float(r.get("confidenceScore"))
        rid = r.get("reviewId", "")
        status = r.get("status", "N/A")
        incoming_name = format_record_name(inc)
        matched_name = format_record_name(matched)
        pt_icon = "🏢" if get_party_type(inc) == "ORGANIZATION" else "👤"
        rows.append({
            "#": i,
            "Type": pt_icon,
            "Incoming": incoming_name,
            "Matched": matched_name,
            "Score": f"{score:.0%}",
            "Classification": r.get("confidenceClassification", "N/A"),
            "Agent": r.get("sourceAgent", "N/A"),
            "Status": status,
        })
        if status == "pending":
            dropdown_choices.append(f"#{i} {pt_icon} {incoming_name} ↔ {matched_name} ({score:.0%}) | {rid}")
    df = pd.DataFrame(rows)
    summary = f"Showing {len(df)} review(s) — {len(dropdown_choices)} pending"
    return summary, df, gr.update(choices=dropdown_choices, value=dropdown_choices[0] if dropdown_choices else None)


def _extract_review_id(selection):
    """Extract the review ID from dropdown selection format: 'Name ↔ Name (score) | review-id'"""
    if not selection:
        return None
    if "|" in selection:
        return selection.split("|")[-1].strip()
    return selection.strip()


def get_review_detail(selection):
    review_id = _extract_review_id(selection)
    if not review_id:
        return "Select a review from the dropdown above."
    reviews = fetch_reviews()
    review = next((r for r in reviews if r.get("reviewId") == review_id), None)
    if not review:
        return f"Review not found: {review_id}"

    inc = review.get("incomingRecord", {})
    matched = review.get("matchedRecord", {})
    score = safe_float(review.get("confidenceScore"))
    pt = get_party_type(inc)

    detail = f"## Review: {review.get('reviewId', 'N/A')}\n\n"
    detail += f"**Status:** {review.get('status', 'N/A').upper()} | **Score:** {score:.0%} | **Agent:** {review.get('sourceAgent', 'N/A')} | **Method:** {review.get('matchingMethod', 'N/A')}\n\n"

    if review.get("contributingFields"):
        fields = review["contributingFields"]
        if isinstance(fields, list):
            detail += f"**Contributing Fields:** {', '.join(str(f) for f in fields)}\n\n"

    detail += "---\n\n"
    if pt == "ORGANIZATION":
        detail += f"### 📥 Incoming Organization\n"
        detail += f"- **Party Name:** {inc.get('partyName', 'N/A')}\n"
        detail += f"- **Tax Reg:** {inc.get('taxRegistrationNum', 'N/A')}\n"
        detail += f"- **Taxpayer ID:** {inc.get('taxpayerId', 'N/A')}\n"
        detail += f"- **Address:** {format_address(inc.get('address'))}\n"
        detail += f"- **Source:** {inc.get('sourceSystem', 'N/A')}\n\n"
        detail += f"### 📄 Matched Organization\n"
        detail += f"- **Party Name:** {matched.get('partyName', 'N/A')}\n"
        detail += f"- **Tax Reg:** {matched.get('taxRegistrationNum', 'N/A')}\n"
        detail += f"- **Taxpayer ID:** {matched.get('taxpayerId', 'N/A')}\n"
        detail += f"- **Address:** {format_address(matched.get('address'))}\n"
        detail += f"- **Source:** {matched.get('sourceSystem', 'N/A')}\n"
    else:
        detail += f"### 📥 Incoming Record\n"
        detail += f"- **Name:** {format_record_name(inc)}\n"
        detail += f"- **Email:** {inc.get('email', 'N/A')}\n"
        detail += f"- **Phone:** {inc.get('phone', 'N/A')}\n"
        detail += f"- **DOB:** {inc.get('dateOfBirth', 'N/A')}\n"
        detail += f"- **Address:** {format_address(inc.get('address'))}\n"
        detail += f"- **Source:** {inc.get('sourceSystem', 'N/A')}\n\n"
        detail += f"### 📄 Matched Record\n"
        detail += f"- **Name:** {format_record_name(matched)}\n"
        detail += f"- **Email:** {matched.get('email', 'N/A')}\n"
        detail += f"- **Phone:** {matched.get('phone', 'N/A')}\n"
        detail += f"- **DOB:** {matched.get('dateOfBirth', 'N/A')}\n"
        detail += f"- **Address:** {format_address(matched.get('address'))}\n"
        detail += f"- **Source:** {matched.get('sourceSystem', 'N/A')}\n"

    return detail


def approve_review(selection):
    rid = _extract_review_id(selection)
    if not rid:
        return "Select a review from the dropdown first."
    result = call_approve(rid)
    if result.get("status") == "approved":
        return f"✅ Merge approved! Review {rid}"
    return f"Result: {json.dumps(result, default=decimal_default)}"


def reject_review(selection):
    rid = _extract_review_id(selection)
    if not rid:
        return "Select a review from the dropdown first."
    result = call_reject(rid)
    if result.get("status") == "rejected":
        return f"✅ Merge rejected. Review {rid}"
    return f"Result: {json.dumps(result, default=decimal_default)}"


# ---------------------------------------------------------------------------
# Tab: Register
# ---------------------------------------------------------------------------
def register_person(first_name, last_name, email, phone, dob, source, street, city, state, postal_code, country):
    if not first_name or not last_name:
        return "❌ First Name and Last Name are required."
    payload = {"firstName": first_name, "lastName": last_name, "sourceSystem": source, "partyType": "PERSON"}
    if email: payload["email"] = email
    if phone: payload["phone"] = phone
    if dob: payload["dateOfBirth"] = dob
    address = {}
    if street: address["street"] = street
    if city: address["city"] = city
    if state: address["state"] = state
    if postal_code: address["postalCode"] = postal_code
    if country: address["country"] = country
    if address: payload["address"] = address

    result = call_register(payload)
    status = result.get("status", "error")
    if status == "new_record":
        return f"✅ **New person record created!**\n- Customer ID: `{result.get('customerId', 'N/A')}`\n- Confidence: {safe_float(result.get('confidenceScore')):.0%}"
    elif status in ("review_pending", "duplicate_found"):
        score = safe_float(result.get("confidenceScore"))
        return f"⚠️ **Duplicate detected!**\n- Confidence: {score:.0%}\n- Classification: {result.get('confidenceClassification', 'N/A')}\n- Review ID: `{result.get('reviewId', 'N/A')}`\n- Check the Duplicate Reviews tab."
    return f"❌ Error: {result.get('error', json.dumps(result, default=decimal_default))}"


def register_org(party_name, tax_reg, taxpayer_id, mdr_pid, match_market, source, street, city, state, postal_code, country):
    if not party_name:
        return "❌ Party Name is required."
    payload = {"partyType": "ORGANIZATION", "partyName": party_name, "sourceSystem": source}
    if tax_reg: payload["taxRegistrationNum"] = tax_reg
    if taxpayer_id: payload["taxpayerId"] = taxpayer_id
    if mdr_pid: payload["mdrPidId"] = mdr_pid
    if match_market: payload["matchMarket"] = match_market
    address = {}
    if street: address["street"] = street
    if city: address["city"] = city
    if state: address["state"] = state
    if postal_code: address["postalCode"] = postal_code
    if country: address["country"] = country
    if address: payload["address"] = address

    result = call_register(payload)
    status = result.get("status", "error")
    if status == "new_record":
        return f"✅ **New organization record created!**\n- Customer ID: `{result.get('customerId', 'N/A')}`\n- Confidence: {safe_float(result.get('confidenceScore')):.0%}"
    elif status in ("review_pending", "duplicate_found"):
        score = safe_float(result.get("confidenceScore"))
        return f"⚠️ **Duplicate organization detected!**\n- Confidence: {score:.0%}\n- Classification: {result.get('confidenceClassification', 'N/A')}\n- Review ID: `{result.get('reviewId', 'N/A')}`\n- Check the Duplicate Reviews tab."
    return f"❌ Error: {result.get('error', json.dumps(result, default=decimal_default))}"


# ---------------------------------------------------------------------------
# Tab: Batch
# ---------------------------------------------------------------------------
def start_batch():
    result = trigger_batch()
    if "executionArn" in result:
        return f"🚀 **Batch scan started!**\n- Execution ARN: `{result['executionArn']}`\n- Check back in 30-60 seconds."
    return f"❌ Error: {result.get('error', 'Unknown error')}"


# ---------------------------------------------------------------------------
# Tab: Dashboard
# ---------------------------------------------------------------------------
def load_dashboard():
    customers = fetch_customers()
    reviews = fetch_reviews()

    active = len([c for c in customers if c.get("status") == "active"])
    merged = len([c for c in customers if c.get("status") == "merged"])
    persons = len([c for c in customers if get_party_type(c) == "PERSON"])
    orgs = len([c for c in customers if get_party_type(c) == "ORGANIZATION"])
    pending = len([r for r in reviews if r.get("status") == "pending"])
    approved = len([r for r in reviews if r.get("status") == "approved"])
    rejected = len([r for r in reviews if r.get("status") == "rejected"])

    summary = (
        f"**Total Records:** {len(customers)} ({active} active, {merged} merged)\n\n"
        f"**Person:** {persons} | **Organization:** {orgs}\n\n"
        f"**Reviews:** {pending} pending, {approved} approved, {rejected} rejected"
    )

    # Party type pie chart
    fig1 = go.Figure(data=[go.Pie(labels=["Person", "Organization"], values=[persons, orgs],
                                   marker_colors=["#007bff", "#17a2b8"], hole=0.4)])
    fig1.update_layout(title="Records by Party Type", height=350, margin=dict(t=40, b=20, l=20, r=20))

    # Status pie chart
    fig2 = go.Figure(data=[go.Pie(labels=["Active", "Merged"], values=[active, merged],
                                   marker_colors=["#28a745", "#ffc107"], hole=0.4)])
    fig2.update_layout(title="Customer Status", height=350, margin=dict(t=40, b=20, l=20, r=20))

    # Review status
    fig3 = go.Figure(data=[go.Pie(labels=["Pending", "Approved", "Rejected"], values=[pending, approved, rejected],
                                   marker_colors=["#007bff", "#28a745", "#dc3545"], hole=0.4)])
    fig3.update_layout(title="Review Status", height=350, margin=dict(t=40, b=20, l=20, r=20))

    # Source system bar
    src_counts = {}
    for c in customers:
        src = c.get("sourceSystem", "Unknown")
        src_counts[src] = src_counts.get(src, 0) + 1
    fig4 = go.Figure(data=[go.Bar(x=list(src_counts.keys()), y=list(src_counts.values()),
                                   marker_color=["#6f42c1", "#e83e8c"][:len(src_counts)])])
    fig4.update_layout(title="Records by Source System", height=350, margin=dict(t=40, b=20, l=20, r=20))

    return summary, fig1, fig2, fig3, fig4


# ---------------------------------------------------------------------------
# Chatbot
# ---------------------------------------------------------------------------
def chat_respond(message, history):
    msg = message.lower().strip()

    # Register command
    reg_match = re.search(r"register\s+(\w+)\s+(\w+)\s+from\s+(\w+)\s+with\s+email\s+([\w.@+-]+)", msg)
    if reg_match:
        result = call_register({
            "firstName": reg_match.group(1).title(), "lastName": reg_match.group(2).title(),
            "sourceSystem": reg_match.group(3), "email": reg_match.group(4),
        })
        status = result.get("status", "error")
        if status == "new_record":
            return f"✅ New record created! ID: {result.get('customerId', 'N/A')}"
        elif status in ("review_pending", "duplicate_found"):
            return f"⚠️ Duplicate detected! Score: {safe_float(result.get('confidenceScore')):.0%}. Review ID: {result.get('reviewId', 'N/A')}"
        return f"❌ Error: {result.get('error', str(result))}"

    # Approve
    approve_match = re.search(r"approve\s+(?:review\s+)?([a-zA-Z0-9-]+)", msg)
    if approve_match and "reject" not in msg:
        result = call_approve(approve_match.group(1))
        return f"✅ Approved!" if result.get("status") == "approved" else f"Result: {str(result)}"

    # Reject
    reject_match = re.search(r"reject\s+(?:review\s+)?([a-zA-Z0-9-]+)", msg)
    if reject_match:
        result = call_reject(reject_match.group(1))
        return f"✅ Rejected!" if result.get("status") == "rejected" else f"Result: {str(result)}"

    # Counts
    if any(w in msg for w in ["how many", "count"]):
        if any(w in msg for w in ["review", "duplicate", "pending"]):
            reviews = fetch_reviews()
            pending = [r for r in reviews if r.get("status") == "pending"]
            return f"📊 {len(pending)} pending reviews out of {len(reviews)} total."
        customers = fetch_customers()
        active = [c for c in customers if c.get("status") == "active"]
        return f"📊 {len(active)} active customers out of {len(customers)} total."

    # Batch
    if any(w in msg for w in ["scan", "batch"]):
        result = trigger_batch()
        if "executionArn" in result:
            return f"🚀 Batch scan started! ARN: {result['executionArn']}"
        return f"❌ Error: {result.get('error', 'Unknown')}"

    # Fallback — try Bedrock
    try:
        client = get_bedrock_client()
        body = json.dumps({
            "messages": [{"role": "user", "content": [{"text": f"You are the AgentDedup assistant. User said: {message}. Respond concisely in 2 sentences."}]}],
            "inferenceConfig": {"maxTokens": 200, "temperature": 0.1},
        })
        resp = client.invoke_model(modelId=BEDROCK_MODEL, body=body, contentType="application/json", accept="application/json")
        result = json.loads(resp["body"].read())
        return result["output"]["message"]["content"][0]["text"]
    except Exception:
        return "I can help with: registering customers, reviewing duplicates, running batch scans, and viewing stats. Try: 'how many customers?' or 'register John Smith from OneCRM with email john@test.com'"


# ---------------------------------------------------------------------------
# Build Gradio App
# ---------------------------------------------------------------------------

CSS = """
.gradio-container { max-width: 1400px !important; font-size: 13px !important; }
.gradio-container h1 { color: #FF6B35 !important; font-size: 24px !important; }
.gradio-container h2, .gradio-container h3 { font-size: 16px !important; }
.gradio-container .markdown-text { font-size: 13px !important; }
.gradio-container table { font-size: 12px !important; }
.gradio-container .label-wrap { font-size: 12px !important; }
.gradio-container input, .gradio-container select, .gradio-container textarea { font-size: 13px !important; }
.gradio-container button { font-size: 13px !important; }
.gradio-container .tab-nav button { font-size: 13px !important; }
"""

# Pre-load ALL data at container startup so pages render instantly
try:
    _initial_accounts = load_accounts("", "All")
except Exception:
    _initial_accounts = pd.DataFrame()

try:
    _initial_rev_summary, _initial_rev_table, _initial_rev_dropdown = load_reviews("pending", "All")
except Exception:
    _initial_rev_summary = "No reviews."
    _initial_rev_table = pd.DataFrame()
    _initial_rev_dropdown = {"choices": [], "value": None, "__type__": "update"}

try:
    _initial_dash = load_dashboard()
except Exception:
    _initial_dash = ("No data.", None, None, None, None)

with gr.Blocks(title="AgentDedup — Customer Data Deduplication", css=CSS) as app:
    gr.Markdown("# 🔍 AgentDedup — Customer Data Deduplication")
    gr.Markdown("*AI-powered duplicate detection with human-in-the-loop review — Person & Organization*")

    with gr.Tabs():
        # ============================================================
        # TAB 1: Accounts
        # ============================================================
        with gr.Tab("📇 Accounts"):
            with gr.Row():
                acct_search = gr.Textbox(label="🔎 Search", placeholder="e.g. Chris James or Pearson...", scale=3)
                acct_filter = gr.Dropdown(choices=["All", "Person", "Organization"], value="All", label="Party Type", scale=1)
                acct_refresh = gr.Button("🔄 Refresh", variant="secondary", scale=1)
            acct_table = gr.Dataframe(value=_initial_accounts, label="Customer Records", interactive=False, wrap=True, height=500)
            acct_refresh.click(fn=load_accounts, inputs=[acct_search, acct_filter], outputs=acct_table)
            acct_search.submit(fn=load_accounts, inputs=[acct_search, acct_filter], outputs=acct_table)
            acct_filter.change(fn=load_accounts, inputs=[acct_search, acct_filter], outputs=acct_table)

        # ============================================================
        # TAB 2: Duplicate Reviews
        # ============================================================
        with gr.Tab("🔀 Duplicate Reviews"):
            with gr.Row():
                rev_status = gr.Dropdown(choices=["pending", "all", "approved", "rejected"], value="pending", label="Status", scale=1)
                rev_pt = gr.Dropdown(choices=["All", "Person", "Organization"], value="All", label="Party Type", scale=1)
                rev_refresh = gr.Button("🔄 Refresh", variant="secondary", scale=1)
            rev_summary = gr.Markdown(value=_initial_rev_summary if isinstance(_initial_rev_summary, str) else "Click Refresh")
            rev_table = gr.Dataframe(value=_initial_rev_table if isinstance(_initial_rev_table, pd.DataFrame) else pd.DataFrame(), label="Reviews", interactive=False, wrap=True, height=250)

            gr.Markdown("---")
            gr.Markdown("### ⚡ Review Actions")
            _dd_choices = _initial_rev_dropdown.get("choices", []) if isinstance(_initial_rev_dropdown, dict) else []
            _dd_value = _initial_rev_dropdown.get("value") if isinstance(_initial_rev_dropdown, dict) else None
            rev_select = gr.Dropdown(label="Select a pending review", choices=_dd_choices, value=_dd_value, interactive=True)
            rev_detail = gr.Markdown("Select a review above to see side-by-side comparison.")
            rev_select.change(fn=get_review_detail, inputs=rev_select, outputs=rev_detail)
            with gr.Row():
                approve_btn = gr.Button("✅ Approve Merge", variant="primary", scale=1)
                reject_btn = gr.Button("❌ Reject Merge", variant="stop", scale=1)
            action_result = gr.Markdown("")
            approve_btn.click(fn=approve_review, inputs=rev_select, outputs=action_result)
            reject_btn.click(fn=reject_review, inputs=rev_select, outputs=action_result)

            rev_refresh.click(fn=load_reviews, inputs=[rev_status, rev_pt], outputs=[rev_summary, rev_table, rev_select])
            rev_status.change(fn=load_reviews, inputs=[rev_status, rev_pt], outputs=[rev_summary, rev_table, rev_select])
            rev_pt.change(fn=load_reviews, inputs=[rev_status, rev_pt], outputs=[rev_summary, rev_table, rev_select])

        # ============================================================
        # TAB 3: Register Customer
        # ============================================================
        with gr.Tab("➕ Register Customer"):
            reg_type = gr.Radio(choices=["Person", "Organization"], value="Person", label="Party Type")

            with gr.Group(visible=True) as person_group:
                gr.Markdown("### Register Person")
                with gr.Row():
                    with gr.Column():
                        p_fn = gr.Textbox(label="First Name *")
                        p_ln = gr.Textbox(label="Last Name *")
                        p_email = gr.Textbox(label="Email")
                        p_phone = gr.Textbox(label="Phone")
                        p_dob = gr.Textbox(label="Date of Birth (YYYY-MM-DD)")
                    with gr.Column():
                        p_src = gr.Dropdown(choices=["OneCRM", "NES"], value="OneCRM", label="Source System *")
                        p_street = gr.Textbox(label="Street")
                        p_city = gr.Textbox(label="City")
                        p_state = gr.Textbox(label="State")
                        p_pc = gr.Textbox(label="Postal Code")
                        p_country = gr.Textbox(label="Country", value="US")
                p_submit = gr.Button("🚀 Register Person", variant="primary")
                p_result = gr.Markdown("")
                p_submit.click(fn=register_person,
                               inputs=[p_fn, p_ln, p_email, p_phone, p_dob, p_src, p_street, p_city, p_state, p_pc, p_country],
                               outputs=p_result)

            with gr.Group(visible=False) as org_group:
                gr.Markdown("### Register Organization")
                with gr.Row():
                    with gr.Column():
                        o_name = gr.Textbox(label="Party Name *", placeholder="e.g. Pearson Education Inc.")
                        o_taxreg = gr.Textbox(label="Tax Registration Number")
                        o_tpid = gr.Textbox(label="Taxpayer ID")
                        o_mdr = gr.Textbox(label="MDR PID ID")
                        o_mm = gr.Textbox(label="Match Market", placeholder="e.g. US-EDUCATION")
                    with gr.Column():
                        o_src = gr.Dropdown(choices=["OneCRM", "NES"], value="OneCRM", label="Source System *")
                        o_street = gr.Textbox(label="Street")
                        o_city = gr.Textbox(label="City")
                        o_state = gr.Textbox(label="State")
                        o_pc = gr.Textbox(label="Postal Code")
                        o_country = gr.Textbox(label="Country", value="US")
                o_submit = gr.Button("🚀 Register Organization", variant="primary")
                o_result = gr.Markdown("")
                o_submit.click(fn=register_org,
                               inputs=[o_name, o_taxreg, o_tpid, o_mdr, o_mm, o_src, o_street, o_city, o_state, o_pc, o_country],
                               outputs=o_result)

            def toggle_form(party_type):
                return gr.update(visible=(party_type == "Person")), gr.update(visible=(party_type == "Organization"))
            reg_type.change(fn=toggle_form, inputs=reg_type, outputs=[person_group, org_group])

        # ============================================================
        # TAB 4: Batch Scan
        # ============================================================
        with gr.Tab("📦 Batch Scan"):
            gr.Markdown("### Batch Deduplication Scan")
            gr.Markdown(f"Trigger the Clean Agent to scan existing records.\n\n"
                        f"- **State Machine:** `{BATCH_STATE_MACHINE_ARN.split(':')[-1]}`\n"
                        f"- **Input Bucket:** `{BATCH_INPUT_BUCKET}`")
            batch_btn = gr.Button("🚀 Start Batch Scan", variant="primary")
            batch_result = gr.Markdown("")
            batch_btn.click(fn=start_batch, outputs=batch_result)

        # ============================================================
        # TAB 5: Dashboard (pre-loaded charts)
        # ============================================================
        with gr.Tab("📊 Dashboard"):
            dash_refresh = gr.Button("🔄 Refresh Dashboard", variant="secondary")
            dash_summary = gr.Markdown(value=_initial_dash[0])
            with gr.Row():
                dash_fig1 = gr.Plot(value=_initial_dash[1], label="Party Type")
                dash_fig2 = gr.Plot(value=_initial_dash[2], label="Status")
            with gr.Row():
                dash_fig3 = gr.Plot(value=_initial_dash[3], label="Reviews")
                dash_fig4 = gr.Plot(value=_initial_dash[4], label="Source System")
            dash_refresh.click(fn=load_dashboard, outputs=[dash_summary, dash_fig1, dash_fig2, dash_fig3, dash_fig4])

        # ============================================================
        # TAB 6: Chatbot
        # ============================================================
        with gr.Tab("🤖 Assistant"):
            gr.Markdown("### Dedup Assistant\nAsk questions or give commands in natural language.")
            gr.Markdown("**Try:** *How many customers?* | *How many pending reviews?* | *Register John Smith from OneCRM with email john@test.com*")
            chat_input = gr.Textbox(label="Your message", placeholder="Type a command or question...")
            chat_output = gr.Markdown("")
            chat_input.submit(fn=lambda msg: chat_respond(msg, []), inputs=chat_input, outputs=chat_output)
            chat_send = gr.Button("Send", variant="primary")
            chat_send.click(fn=lambda msg: chat_respond(msg, []), inputs=chat_input, outputs=chat_output)

    gr.Markdown(f"---\n🔗 API: `{API_URL}` | 📦 Region: `{AWS_REGION}`")


if __name__ == "__main__":
    port = int(os.getenv("PORT", os.getenv("GRADIO_SERVER_PORT", "8501")))
    app.launch(server_name="0.0.0.0", server_port=port)
