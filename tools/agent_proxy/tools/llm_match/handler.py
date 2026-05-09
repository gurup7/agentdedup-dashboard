"""LLMMatchTool Lambda — Stage 2 LLM-based fuzzy matching for ambiguous cases.

Accepts an incoming record, a candidate record, and a rule-based score.
Only processes when the rule-based score is between 0.4 and 0.9 (ambiguous zone).
Calls Amazon Bedrock (Claude 3 Sonnet by default) to assess match likelihood,
then combines scores: 60% rule-based + 40% LLM.

If Bedrock is unavailable, falls back to rule-based score only.

Environment variables:
    BEDROCK_MODEL_ID: Bedrock model identifier
        (default: anthropic.claude-3-sonnet-20240229-v1:0)
"""

import json
import logging
import os
import re

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DEFAULT_MODEL_ID = "anthropic.claude-3-sonnet-20240229-v1:0"

# Fields that contain PII and should be masked in logs
_PII_FIELDS = {"email", "phone", "dateOfBirth", "street", "city",
               "state", "postalCode", "country"}


def _mask_pii(record: dict) -> dict:
    """Return a copy of *record* with PII fields masked for safe logging."""
    masked = {}
    for key, value in record.items():
        if key in _PII_FIELDS:
            masked[key] = "***"
        elif isinstance(value, dict):
            masked[key] = _mask_pii(value)
        else:
            masked[key] = value
    return masked


def _build_prompt(incoming: dict, candidate: dict) -> str:
    """Construct the Bedrock prompt with both records side-by-side."""
    return (
        "You are a data-matching expert. Compare the two customer records below "
        "and assess the likelihood they refer to the same real-world person.\n\n"
        "Record A (incoming):\n"
        f"{json.dumps(incoming, indent=2)}\n\n"
        "Record B (existing):\n"
        f"{json.dumps(candidate, indent=2)}\n\n"
        "Return your answer as JSON with exactly two keys:\n"
        '  "confidence": a float between 0.0 and 1.0\n'
        '  "reasoning": a short explanation\n'
        "Return ONLY the JSON object, no other text."
    )


def _parse_llm_response(response_body: str) -> dict:
    """Extract confidence and reasoning from the LLM response text.

    Tries JSON parsing first, then falls back to regex extraction.
    Returns dict with 'confidence' (float) and 'reasoning' (str).
    """
    # Try direct JSON parse
    try:
        data = json.loads(response_body)
        conf = max(0.0, min(1.0, float(data["confidence"])))
        return {
            "confidence": conf,
            "reasoning": str(data.get("reasoning", "")),
        }
    except (json.JSONDecodeError, KeyError, ValueError):
        pass

    # Fallback: extract from text with regex
    conf_match = re.search(r'"confidence"\s*:\s*([\d.]+)', response_body)
    reason_match = re.search(r'"reasoning"\s*:\s*"([^"]*)"', response_body)

    confidence = float(conf_match.group(1)) if conf_match else 0.5
    reasoning = reason_match.group(1) if reason_match else "Unable to parse LLM reasoning"

    # Clamp confidence to [0.0, 1.0]
    confidence = max(0.0, min(1.0, confidence))

    return {"confidence": confidence, "reasoning": reasoning}


def _invoke_bedrock(prompt: str, model_id: str) -> dict:
    """Call Bedrock InvokeModel and return parsed confidence + reasoning."""
    client = boto3.client("bedrock-runtime")

    request_body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 300,
        "messages": [{"role": "user", "content": prompt}],
    })

    response = client.invoke_model(
        modelId=model_id,
        contentType="application/json",
        accept="application/json",
        body=request_body,
    )

    response_payload = json.loads(response["body"].read())
    # Claude messages API returns content as a list of blocks
    text = response_payload["content"][0]["text"]
    return _parse_llm_response(text)


def handler(event, context):
    """Lambda entry point.

    Args:
        event: dict with keys incomingRecord, candidateRecord, ruleBasedScore.
        context: Lambda context (unused).

    Returns:
        dict with finalScore, llmScore, ruleBasedScore, reasoning, matchingMethod.
    """
    if isinstance(event, str):
        event = json.loads(event)
    body = event.get("body", event)
    if isinstance(body, str):
        body = json.loads(body)

    incoming = body.get("incomingRecord", {})
    candidate = body.get("candidateRecord", {})
    rule_score = float(body.get("ruleBasedScore", 0.0))

    logger.info(
        "LLMMatchTool invoked: ruleBasedScore=%.4f, incoming=%s, candidate=%s",
        rule_score,
        _mask_pii(incoming),
        _mask_pii(candidate),
    )

    # Only process ambiguous scores (0.4–0.9)
    if rule_score < 0.4 or rule_score >= 0.9:
        logger.info("Score %.4f outside ambiguous range [0.4, 0.9) — returning early", rule_score)
        return {
            "finalScore": rule_score,
            "ruleBasedScore": rule_score,
            "matchingMethod": "rule_based_only",
            "reasoning": "Score outside ambiguous range; LLM not invoked",
        }

    model_id = os.environ.get("BEDROCK_MODEL_ID", DEFAULT_MODEL_ID)

    try:
        prompt = _build_prompt(incoming, candidate)
        llm_result = _invoke_bedrock(prompt, model_id)
        llm_score = llm_result["confidence"]
        reasoning = llm_result["reasoning"]

        final_score = round(0.6 * rule_score + 0.4 * llm_score, 4)

        logger.info(
            "LLM matching complete: llmScore=%.4f, finalScore=%.4f",
            llm_score,
            final_score,
        )

        return {
            "finalScore": final_score,
            "llmScore": llm_score,
            "ruleBasedScore": rule_score,
            "reasoning": reasoning,
            "matchingMethod": "rule+llm",
        }

    except Exception as exc:
        logger.error("Bedrock invocation failed: %s", exc)
        return {
            "finalScore": rule_score,
            "ruleBasedScore": rule_score,
            "matchingMethod": "rule_based_only",
            "fallbackReason": f"LLM unavailable: {exc}",
        }
