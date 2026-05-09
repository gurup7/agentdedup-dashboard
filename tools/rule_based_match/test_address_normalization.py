"""Unit tests for address_normalization module."""

import re
import sys
from pathlib import Path

# Ensure the module is importable
sys.path.insert(0, str(Path(__file__).parent))

from address_normalization import normalize_address


def test_uppercase_conversion():
    assert normalize_address("london") == "LONDON"
    assert normalize_address("London") == "LONDON"
    assert normalize_address("LONDON") == "LONDON"


def test_case_insensitivity():
    assert normalize_address("LONDON") == normalize_address("london")
    assert normalize_address("london") == normalize_address("London")


def test_strip_whitespace():
    assert normalize_address("  LONDON  ") == "LONDON"
    assert normalize_address("\tLONDON\n") == "LONDON"


def test_punctuation_removal_period():
    assert normalize_address("123 Main St.") == "123 MAIN STREET"


def test_punctuation_removal_comma():
    result = normalize_address("London, Greenwich")
    assert result == "LONDON GREENWICH", f"Got: {result}"


def test_abbreviation_expansion():
    assert normalize_address("123 Main St") == "123 MAIN STREET"
    assert normalize_address("Oak Rd") == "OAK ROAD"
    assert normalize_address("Park Ave") == "PARK AVENUE"
    assert normalize_address("Sunset Blvd") == "SUNSET BOULEVARD"
    assert normalize_address("Elm Ln") == "ELM LANE"
    assert normalize_address("Pine Dr") == "PINE DRIVE"
    assert normalize_address("Maple Ct") == "MAPLE COURT"
    assert normalize_address("Cedar Pl") == "CEDAR PLACE"


def test_collapse_multiple_spaces():
    assert normalize_address("123   Main    St") == "123 MAIN STREET"


def test_uk_postcode_normalization():
    assert normalize_address("SE95EE") == "SE9 5EE"
    assert normalize_address("SW1A1AA") == "SW1A 1AA"
    assert normalize_address("SE9 5EE") == "SE9 5EE"
    assert normalize_address("EC1A1BB") == "EC1A 1BB"


def test_spanish_address_patterns():
    result = normalize_address("C. DE LA RESINA, 35, NAVE 7")
    assert "C " in result, f"Got: {result}"
    assert "NAVE" in result, f"Got: {result}"


def test_idempotency():
    test_cases = [
        "ELTHAM HILL, LONDON, GREENWICH, SE9 5EE",
        "123 Main St.",
        "C. DE LA RESINA, 35, NAVE 7",
        "SE95EE",
        "  hello   world  ",
        "Eltham Hill School, Eltham Hill",
        "",
    ]
    for tc in test_cases:
        first = normalize_address(tc)
        second = normalize_address(first)
        assert first == second, f'Not idempotent for "{tc}": "{first}" != "{second}"'


def test_no_leading_trailing_whitespace():
    test_cases = ["  hello  ", "LONDON", "123 Main St.", "SE95EE"]
    for tc in test_cases:
        result = normalize_address(tc)
        assert result == result.strip(), f'Has whitespace: "{result}"'


def test_no_consecutive_spaces():
    test_cases = [
        "ELTHAM HILL, LONDON, GREENWICH, SE9 5EE",
        "123   Main    St.",
        "C. DE LA RESINA, 35, NAVE 7",
    ]
    for tc in test_cases:
        result = normalize_address(tc)
        assert not re.search(r"  ", result), f'Consecutive spaces in: "{result}"'


def test_empty_input():
    assert normalize_address("") == ""
    assert normalize_address("   ") == ""


def test_real_world_eltham_hill():
    """Test with actual client data patterns."""
    r1 = normalize_address("ELTHAM HILL")
    r2 = normalize_address("ELTHAM HILL SCHOOL, ELTHAM HILL")
    # Both should be normalized (uppercase, no punctuation)
    assert r1 == "ELTHAM HILL"
    assert r2 == "ELTHAM HILL SCHOOL ELTHAM HILL"


def test_real_world_merchanfactory():
    """Test with actual Spanish address pattern."""
    result = normalize_address("C. DE LA RESINA, 35, NAVE 7")
    assert result == "C DE LA RESINA 35 NAVE 7", f"Got: {result}"


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS: {t.__name__}")
    print(f"\nAll {len(tests)} tests passed!")
