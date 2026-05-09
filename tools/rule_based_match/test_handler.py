"""Unit tests for RuleBasedMatchTool Lambda handler."""

import unittest

from tools.rule_based_match.handler import handler, _score_pair


# --- Test fixtures ---

INCOMING_CHRIS = {
    "firstName": "Chris",
    "lastName": "James",
    "email": "chris.james@fakecorp.com",
    "phone": "+15551234001",
    "dateOfBirth": "1985-03-15",
}

CANDIDATE_EXACT = {
    "customerId": "c001",
    "firstName": "Chris",
    "lastName": "James",
    "email": "chris.james@fakecorp.com",
    "phone": "+15551234001",
    "dateOfBirth": "1985-03-15",
}

CANDIDATE_SAME_EMAIL_DIFF_PHONE = {
    "customerId": "c002",
    "firstName": "Chris",
    "lastName": "James",
    "email": "chris.james@fakecorp.com",
    "phone": "+15551234099",
    "dateOfBirth": "1985-03-15",
}

CANDIDATE_SAME_PHONE = {
    "customerId": "c003",
    "firstName": "Maria",
    "lastName": "Garcia",
    "email": "maria.garcia@testmail.net",
    "phone": "+15551234001",
    "dateOfBirth": "1990-07-22",
}

CANDIDATE_TYPO_NAME = {
    "customerId": "c007",
    "firstName": "Chrish",
    "lastName": "James",
    "email": "chrish.james@fakecorp.com",
    "phone": "+15551234050",
    "dateOfBirth": "1985-03-15",
}

CANDIDATE_COMPLETELY_DIFFERENT = {
    "customerId": "c099",
    "firstName": "Emily",
    "lastName": "Nguyen",
    "email": "emily.nguyen@testcorp.com",
    "phone": "+15557778001",
    "dateOfBirth": "1983-12-01",
}

INCOMING_MISSING_FIELDS = {
    "firstName": "Linda",
    "lastName": "Taylor",
    "email": None,
    "phone": None,
    "dateOfBirth": "1970-02-14",
}

CANDIDATE_MISSING_FIELDS = {
    "customerId": "c018",
    "firstName": "Linda",
    "lastName": "Taylor",
    "email": None,
    "phone": "+15553210001",
    "dateOfBirth": "1970-02-14",
}


class TestScorePair(unittest.TestCase):
    """Tests for the _score_pair helper."""

    def test_exact_match_scores_high(self):
        """Exact match on all fields should produce score >= 0.9."""
        result = _score_pair(INCOMING_CHRIS, CANDIDATE_EXACT)
        self.assertGreaterEqual(result["ruleBasedScore"], 0.9)
        self.assertTrue(result["isDefinitive"])
        self.assertIn("email", result["contributingFields"])
        self.assertIn("phone", result["contributingFields"])
        self.assertIn("dateOfBirth", result["contributingFields"])

    def test_email_match_contributes(self):
        """Same email, different phone — email should contribute ~0.4."""
        result = _score_pair(INCOMING_CHRIS, CANDIDATE_SAME_EMAIL_DIFF_PHONE)
        self.assertIn("email", result["contributingFields"])
        self.assertNotIn("phone", result["contributingFields"])
        self.assertGreaterEqual(result["ruleBasedScore"], 0.4)

    def test_phone_match_contributes(self):
        """Same phone, different person — phone should contribute +0.3."""
        result = _score_pair(INCOMING_CHRIS, CANDIDATE_SAME_PHONE)
        self.assertIn("phone", result["contributingFields"])
        self.assertNotIn("email", result["contributingFields"])
        self.assertGreaterEqual(result["ruleBasedScore"], 0.3)

    def test_name_typo_jaro_winkler(self):
        """'Chris' vs 'Chrish' — Jaro-Winkler should catch the typo."""
        result = _score_pair(INCOMING_CHRIS, CANDIDATE_TYPO_NAME)
        self.assertIn("firstName_jw", result["contributingFields"])
        # Soundex should also match (C620 for both)
        self.assertIn("firstName_soundex", result["contributingFields"])
        # DOB matches too
        self.assertIn("dateOfBirth", result["contributingFields"])
        self.assertGreater(result["ruleBasedScore"], 0.3)

    def test_completely_different_scores_low(self):
        """Completely different records should score below 0.4."""
        result = _score_pair(INCOMING_CHRIS, CANDIDATE_COMPLETELY_DIFFERENT)
        self.assertLess(result["ruleBasedScore"], 0.4)
        self.assertTrue(result["isDefinitive"])

    def test_missing_optional_fields(self):
        """Missing email/phone should not crash; name + DOB still score."""
        result = _score_pair(INCOMING_MISSING_FIELDS, CANDIDATE_MISSING_FIELDS)
        self.assertIn("dateOfBirth", result["contributingFields"])
        self.assertIn("firstName_jw", result["contributingFields"])
        self.assertNotIn("email", result["contributingFields"])
        self.assertNotIn("phone", result["contributingFields"])

    def test_score_capped_at_one(self):
        """Score should never exceed 1.0 even with all fields matching."""
        result = _score_pair(INCOMING_CHRIS, CANDIDATE_EXACT)
        self.assertLessEqual(result["ruleBasedScore"], 1.0)

    def test_is_definitive_high(self):
        """Score >= 0.9 should be definitive."""
        result = _score_pair(INCOMING_CHRIS, CANDIDATE_EXACT)
        self.assertTrue(result["isDefinitive"])

    def test_is_definitive_low(self):
        """Score < 0.4 should be definitive."""
        result = _score_pair(INCOMING_CHRIS, CANDIDATE_COMPLETELY_DIFFERENT)
        self.assertTrue(result["isDefinitive"])


class TestHandler(unittest.TestCase):
    """Tests for the Lambda handler function."""

    def test_handler_returns_results(self):
        event = {
            "incomingRecord": INCOMING_CHRIS,
            "candidates": [CANDIDATE_EXACT, CANDIDATE_COMPLETELY_DIFFERENT],
        }
        result = handler(event, None)
        self.assertIn("results", result)
        self.assertEqual(len(result["results"]), 2)

    def test_handler_empty_candidates(self):
        event = {"incomingRecord": INCOMING_CHRIS, "candidates": []}
        result = handler(event, None)
        self.assertEqual(result["results"], [])

    def test_handler_json_body(self):
        """Handler supports event with JSON string body."""
        import json
        event = {"body": json.dumps({
            "incomingRecord": INCOMING_CHRIS,
            "candidates": [CANDIDATE_EXACT],
        })}
        result = handler(event, None)
        self.assertEqual(len(result["results"]), 1)
        self.assertGreaterEqual(result["results"][0]["ruleBasedScore"], 0.9)


if __name__ == "__main__":
    unittest.main()
