"""RuleBasedMatchTool Lambda — Stage 1 deterministic scoring for duplicate detection.

Supports both PERSON and ORGANIZATION party types with different scoring rules.

PERSON scoring (normalized 0-1):
    Email exact match:      +0.40
    Phone exact match:      +0.30
    Jaro-Winkler firstName: up to +0.15 (threshold 0.85)
    Jaro-Winkler lastName:  up to +0.15 (threshold 0.85)
    Soundex firstName:      +0.05
    Soundex lastName:       +0.05
    DOB exact match:        +0.20

ORGANIZATION scoring (cumulative, based on Oracle TCA "Pearson Organization Duplicates"):
    partyName Jaro-Winkler:     89 (if JW >= 0.85)
    partyName Soundex:          89
    address Jaro-Winkler:       31 (if JW >= 0.80)
    city Jaro-Winkler:          23 (if JW >= 0.85)
    postalCode exact:           55
    state exact:                15
    province Jaro-Winkler:      17 (if JW >= 0.85)
    taxRegistrationNum exact:  146
    taxpayerId exact:          147
    mdrPidId exact:            145
    matchMarket exact:         148
    Match threshold: 144 cumulative

No AWS resource access needed — pure compute.
"""

import json
import logging
import os
from pathlib import Path

import jellyfish

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Load scoring configuration
# ---------------------------------------------------------------------------
_CONFIG_PATH = Path(__file__).parent.parent / "scoring_config.json"
_CONFIG_PATH_ALT = Path(__file__).parent / "scoring_config.json"

def _load_config():
    """Load scoring_config.json — check multiple locations."""
    for path in [_CONFIG_PATH, _CONFIG_PATH_ALT]:
        try:
            with open(path) as f:
                return json.load(f)
        except FileNotFoundError:
            continue
    logger.warning("scoring_config.json not found, using defaults")
    return None

SCORING_CONFIG = _load_config()

# ---------------------------------------------------------------------------
# PERSON scoring weights (defaults / fallback)
# ---------------------------------------------------------------------------
WEIGHT_EMAIL = 0.40
WEIGHT_PHONE = 0.30
WEIGHT_FIRST_NAME_JW = 0.15
WEIGHT_LAST_NAME_JW = 0.15
WEIGHT_FIRST_NAME_SOUNDEX = 0.05
WEIGHT_LAST_NAME_SOUNDEX = 0.05
WEIGHT_DOB = 0.20

JW_THRESHOLD = 0.85

# ---------------------------------------------------------------------------
# ORGANIZATION scoring weights (Oracle TCA Pearson Organization Duplicates)
# ---------------------------------------------------------------------------
ORG_WEIGHT_PARTY_NAME_JW = 89
ORG_WEIGHT_PARTY_NAME_SOUNDEX = 89
ORG_WEIGHT_ADDRESS_JW = 31
ORG_WEIGHT_CITY_JW = 23
ORG_WEIGHT_POSTAL_CODE = 55
ORG_WEIGHT_STATE = 15
ORG_WEIGHT_PROVINCE_JW = 17
ORG_WEIGHT_TAX_REG = 146
ORG_WEIGHT_TAXPAYER_ID = 147
ORG_WEIGHT_MDR_PID_ID = 145
ORG_WEIGHT_MATCH_MARKET = 148

ORG_JW_THRESHOLD = 0.85
ORG_ADDRESS_JW_THRESHOLD = 0.80
ORG_MATCH_THRESHOLD = 144
ORG_HIGH_CONFIDENCE = 200

# Max possible cumulative score (sum of all weights)
ORG_MAX_POSSIBLE = (
    ORG_WEIGHT_PARTY_NAME_JW
    + ORG_WEIGHT_PARTY_NAME_SOUNDEX
    + ORG_WEIGHT_ADDRESS_JW
    + ORG_WEIGHT_CITY_JW
    + ORG_WEIGHT_POSTAL_CODE
    + ORG_WEIGHT_STATE
    + ORG_WEIGHT_PROVINCE_JW
    + ORG_WEIGHT_TAX_REG
    + ORG_WEIGHT_TAXPAYER_ID
    + ORG_WEIGHT_MDR_PID_ID
    + ORG_WEIGHT_MATCH_MARKET
)


def _safe_lower(value):
    """Return lowercased string or empty string if None/missing."""
    if value is None:
        return ""
    return str(value).strip().lower()


# ---------------------------------------------------------------------------
# PERSON scoring (existing logic, unchanged)
# ---------------------------------------------------------------------------
def _score_person_pair(incoming: dict, candidate: dict) -> dict:
    """Compute normalized (0-1) match score for PERSON records."""
    score = 0.0
    contributing = []

    # Email exact match
    inc_email = _safe_lower(incoming.get("email"))
    cand_email = _safe_lower(candidate.get("email"))
    if inc_email and cand_email and inc_email == cand_email:
        score += WEIGHT_EMAIL
        contributing.append("email")

    # Phone exact match
    inc_phone = _safe_lower(incoming.get("phone"))
    cand_phone = _safe_lower(candidate.get("phone"))
    if inc_phone and cand_phone and inc_phone == cand_phone:
        score += WEIGHT_PHONE
        contributing.append("phone")

    # Jaro-Winkler on firstName
    inc_fn = _safe_lower(incoming.get("firstName"))
    cand_fn = _safe_lower(candidate.get("firstName"))
    if inc_fn and cand_fn:
        jw_fn = jellyfish.jaro_winkler_similarity(inc_fn, cand_fn)
        if jw_fn >= JW_THRESHOLD:
            score += WEIGHT_FIRST_NAME_JW * jw_fn
            contributing.append("firstName_jw")

    # Jaro-Winkler on lastName
    inc_ln = _safe_lower(incoming.get("lastName"))
    cand_ln = _safe_lower(candidate.get("lastName"))
    if inc_ln and cand_ln:
        jw_ln = jellyfish.jaro_winkler_similarity(inc_ln, cand_ln)
        if jw_ln >= JW_THRESHOLD:
            score += WEIGHT_LAST_NAME_JW * jw_ln
            contributing.append("lastName_jw")

    # Soundex on firstName
    if inc_fn and cand_fn:
        if jellyfish.soundex(inc_fn) == jellyfish.soundex(cand_fn):
            score += WEIGHT_FIRST_NAME_SOUNDEX
            contributing.append("firstName_soundex")

    # Soundex on lastName
    if inc_ln and cand_ln:
        if jellyfish.soundex(inc_ln) == jellyfish.soundex(cand_ln):
            score += WEIGHT_LAST_NAME_SOUNDEX
            contributing.append("lastName_soundex")

    # Date of birth exact match
    inc_dob = _safe_lower(incoming.get("dateOfBirth"))
    cand_dob = _safe_lower(candidate.get("dateOfBirth"))
    if inc_dob and cand_dob and inc_dob == cand_dob:
        score += WEIGHT_DOB
        contributing.append("dateOfBirth")

    # Normalize and cap
    score = min(round(score, 4), 1.0)

    return {
        "candidateId": candidate.get("customerId", ""),
        "ruleBasedScore": score,
        "contributingFields": contributing,
        "isDefinitive": score >= 0.9 or score < 0.4,
        "partyType": "PERSON",
        "scoreType": "normalized",
    }


# ---------------------------------------------------------------------------
# ORGANIZATION scoring (Oracle TCA cumulative)
# ---------------------------------------------------------------------------
def _score_org_pair(incoming: dict, candidate: dict) -> dict:
    """Compute cumulative match score for ORGANIZATION records.

    Based on Oracle TCA match rule 'Pearson Organization Duplicates'.
    Returns both the cumulative score and a normalized score for display.
    """
    cumulative = 0
    contributing = []

    # partyName — Jaro-Winkler (score 89 if JW >= 0.85)
    inc_name = _safe_lower(incoming.get("partyName"))
    cand_name = _safe_lower(candidate.get("partyName"))
    if inc_name and cand_name:
        jw = jellyfish.jaro_winkler_similarity(inc_name, cand_name)
        if jw >= ORG_JW_THRESHOLD:
            cumulative += ORG_WEIGHT_PARTY_NAME_JW
            contributing.append(f"partyName_jw({jw:.3f})")

        # partyName — Soundex
        if jellyfish.soundex(inc_name) == jellyfish.soundex(cand_name):
            cumulative += ORG_WEIGHT_PARTY_NAME_SOUNDEX
            contributing.append("partyName_soundex")

    # address — Jaro-Winkler on street (score 31 if JW >= 0.80)
    inc_addr = incoming.get("address", {})
    cand_addr = candidate.get("address", {})
    if isinstance(inc_addr, str):
        inc_street = _safe_lower(inc_addr)
    else:
        inc_street = _safe_lower(inc_addr.get("street") if isinstance(inc_addr, dict) else None)
    if isinstance(cand_addr, str):
        cand_street = _safe_lower(cand_addr)
    else:
        cand_street = _safe_lower(cand_addr.get("street") if isinstance(cand_addr, dict) else None)
    if inc_street and cand_street:
        jw = jellyfish.jaro_winkler_similarity(inc_street, cand_street)
        if jw >= ORG_ADDRESS_JW_THRESHOLD:
            cumulative += ORG_WEIGHT_ADDRESS_JW
            contributing.append(f"address_jw({jw:.3f})")

    # city — Jaro-Winkler (score 23 if JW >= 0.85)
    inc_city = _safe_lower(inc_addr.get("city") if isinstance(inc_addr, dict) else None)
    cand_city = _safe_lower(cand_addr.get("city") if isinstance(cand_addr, dict) else None)
    if inc_city and cand_city:
        jw = jellyfish.jaro_winkler_similarity(inc_city, cand_city)
        if jw >= ORG_JW_THRESHOLD:
            cumulative += ORG_WEIGHT_CITY_JW
            contributing.append(f"city_jw({jw:.3f})")

    # postalCode — exact match (score 55)
    inc_pc = _safe_lower(inc_addr.get("postalCode") if isinstance(inc_addr, dict) else None)
    cand_pc = _safe_lower(cand_addr.get("postalCode") if isinstance(cand_addr, dict) else None)
    if inc_pc and cand_pc and inc_pc == cand_pc:
        cumulative += ORG_WEIGHT_POSTAL_CODE
        contributing.append("postalCode_exact")

    # state — exact match (score 15)
    inc_state = _safe_lower(inc_addr.get("state") if isinstance(inc_addr, dict) else None)
    cand_state = _safe_lower(cand_addr.get("state") if isinstance(cand_addr, dict) else None)
    if inc_state and cand_state and inc_state == cand_state:
        cumulative += ORG_WEIGHT_STATE
        contributing.append("state_exact")

    # province — Jaro-Winkler (score 17 if JW >= 0.85)
    inc_prov = _safe_lower(incoming.get("province"))
    cand_prov = _safe_lower(candidate.get("province"))
    if inc_prov and cand_prov:
        jw = jellyfish.jaro_winkler_similarity(inc_prov, cand_prov)
        if jw >= ORG_JW_THRESHOLD:
            cumulative += ORG_WEIGHT_PROVINCE_JW
            contributing.append(f"province_jw({jw:.3f})")

    # taxRegistrationNum — exact match (score 146)
    inc_tax = _safe_lower(incoming.get("taxRegistrationNum"))
    cand_tax = _safe_lower(candidate.get("taxRegistrationNum"))
    if inc_tax and cand_tax and inc_tax == cand_tax:
        cumulative += ORG_WEIGHT_TAX_REG
        contributing.append("taxRegistrationNum_exact")

    # taxpayerId — exact match (score 147)
    inc_tp = _safe_lower(incoming.get("taxpayerId"))
    cand_tp = _safe_lower(candidate.get("taxpayerId"))
    if inc_tp and cand_tp and inc_tp == cand_tp:
        cumulative += ORG_WEIGHT_TAXPAYER_ID
        contributing.append("taxpayerId_exact")

    # mdrPidId — exact match (score 145)
    inc_mdr = _safe_lower(incoming.get("mdrPidId"))
    cand_mdr = _safe_lower(candidate.get("mdrPidId"))
    if inc_mdr and cand_mdr and inc_mdr == cand_mdr:
        cumulative += ORG_WEIGHT_MDR_PID_ID
        contributing.append("mdrPidId_exact")

    # matchMarket — exact match (score 148)
    inc_mm = _safe_lower(incoming.get("matchMarket"))
    cand_mm = _safe_lower(candidate.get("matchMarket"))
    if inc_mm and cand_mm and inc_mm == cand_mm:
        cumulative += ORG_WEIGHT_MATCH_MARKET
        contributing.append("matchMarket_exact")

    # Normalized score for display (cumulative / max_possible)
    normalized = round(cumulative / ORG_MAX_POSSIBLE, 4) if ORG_MAX_POSSIBLE > 0 else 0.0

    # isDefinitive: high confidence (>= 200) or clearly not a match (< 100)
    is_definitive = cumulative >= ORG_HIGH_CONFIDENCE or cumulative < 100

    return {
        "candidateId": candidate.get("customerId", ""),
        "ruleBasedScore": normalized,
        "cumulativeScore": cumulative,
        "maxPossibleScore": ORG_MAX_POSSIBLE,
        "contributingFields": contributing,
        "isDefinitive": is_definitive,
        "partyType": "ORGANIZATION",
        "scoreType": "cumulative",
    }


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------
def handler(event, context):
    """Lambda entry point.

    Args:
        event: dict with keys incomingRecord (dict) and candidates (list of dicts).
               incomingRecord may contain partyType ("PERSON" or "ORGANIZATION").
        context: Lambda context (unused).

    Returns:
        dict with results array of scored candidates.
    """
    if isinstance(event, str):
        event = json.loads(event)
    body = event.get("body", event)
    if isinstance(body, str):
        body = json.loads(body)

    incoming = body.get("incomingRecord", {})
    candidates = body.get("candidates", [])

    # Determine party type — default to PERSON for backward compatibility
    party_type = incoming.get("partyType", "PERSON").upper()

    logger.info(
        "RuleBasedMatchTool invoked: partyType=%s, scoring %d candidates",
        party_type,
        len(candidates),
    )

    if party_type == "ORGANIZATION":
        results = [_score_org_pair(incoming, c) for c in candidates]
    else:
        results = [_score_person_pair(incoming, c) for c in candidates]

    logger.info(
        "Scoring complete (%s): %s",
        party_type,
        [(r["candidateId"], r["ruleBasedScore"], r.get("cumulativeScore", "N/A")) for r in results],
    )

    return {"results": results, "partyType": party_type}
