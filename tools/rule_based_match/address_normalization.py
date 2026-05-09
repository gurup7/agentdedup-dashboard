"""Address normalization for site-level deduplication.

Pure function module — no AWS resource access, no side effects.
Used by RuleBasedMatchTool during comparison only; never alters stored data.

Normalization steps:
1. Convert to uppercase
2. Strip leading/trailing whitespace
3. Remove punctuation (periods → space, commas → space)
4. Expand abbreviations (ST→STREET, RD→ROAD, etc.)
5. Collapse multiple spaces to single space
6. Normalize UK postcode spacing (e.g., "SE95EE" → "SE9 5EE")
7. Preserve Spanish address patterns ("C." → "C ", "NAVE" kept as-is)

Properties:
- Idempotent: normalize(normalize(s)) == normalize(s)
- Case-insensitive: normalize("LONDON") == normalize("london")
- No leading/trailing whitespace in output
- No consecutive internal spaces in output
"""

import re

# ---------------------------------------------------------------------------
# Abbreviation expansions (applied as whole-word replacements)
# ---------------------------------------------------------------------------
_ABBREVIATIONS = {
    "ST": "STREET",
    "RD": "ROAD",
    "AVE": "AVENUE",
    "BLVD": "BOULEVARD",
    "LN": "LANE",
    "DR": "DRIVE",
    "CT": "COURT",
    "PL": "PLACE",
}

# UK postcode pattern: 1-2 letters, 1-2 digits (optionally a letter), then 1 digit + 2 letters
# Matches postcodes that may be missing the internal space.
# Examples: "SE95EE" → "SE9 5EE", "SW1A1AA" → "SW1A 1AA", "EC1A1BB" → "EC1A 1BB"
_UK_POSTCODE_RE = re.compile(
    r"\b([A-Z]{1,2}[0-9][0-9A-Z]?)\s*([0-9][A-Z]{2})\b"
)


def normalize_address(text: str) -> str:
    """Normalize an address string for comparison purposes.

    Args:
        text: Raw address string (any casing, may contain punctuation).

    Returns:
        Normalized uppercase string with expanded abbreviations,
        collapsed whitespace, and normalized UK postcode spacing.
    """
    if not text:
        return ""

    # 1. Convert to uppercase
    result = text.upper()

    # 2. Strip leading/trailing whitespace
    result = result.strip()

    # 3. Remove punctuation — periods and commas become spaces
    #    (preserves word boundaries)
    result = result.replace(".", " ").replace(",", " ")

    # 4. Collapse multiple spaces to single space
    result = re.sub(r"\s+", " ", result).strip()

    # 5. Expand abbreviations (whole-word only)
    #    We split, replace tokens, and rejoin to ensure whole-word matching.
    tokens = result.split()
    expanded_tokens = [
        _ABBREVIATIONS.get(token, token) for token in tokens
    ]
    result = " ".join(expanded_tokens)

    # 6. Normalize UK postcode spacing
    #    Insert space between outward and inward parts if missing.
    result = _UK_POSTCODE_RE.sub(r"\1 \2", result)

    # 7. Final cleanup — collapse any remaining multiple spaces and strip
    result = re.sub(r"\s+", " ", result).strip()

    return result
