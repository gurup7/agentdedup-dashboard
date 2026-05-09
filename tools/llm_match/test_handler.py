"""Unit tests for LLMMatchTool Lambda handler."""

import json
import unittest
from unittest.mock import patch, MagicMock

from tools.llm_match.handler import handler, _mask_pii, _parse_llm_response, _build_prompt


# --- Test fixtures ---

INCOMING = {
    "firstName": "Chris",
    "lastName": "James",
    "email": "chris.james@fakecorp.com",
    "phone": "+15551234001",
    "dateOfBirth": "1985-03-15",
}

CANDIDATE = {
    "customerId": "c007",
    "firstName": "Chrish",
    "lastName": "James",
    "email": "chrish.james@fakecorp.com",
    "phone": "+15551234050",
    "dateOfBirth": "1985-03-15",
}


def _mock_bedrock_response(confidence: float, reasoning: str):
    """Build a mock Bedrock invoke_model response."""
    body_payload = {
        "content": [{"text": json.dumps({
            "confidence": confidence,
            "reasoning": reasoning,
        })}],
    }
    mock_body = MagicMock()
    mock_body.read.return_value = json.dumps(body_payload).encode()
    return {"body": mock_body}


class TestMaskPii(unittest.TestCase):
    """Tests for PII masking utility."""

    def test_masks_email_and_phone(self):
        masked = _mask_pii(INCOMING)
        self.assertEqual(masked["email"], "***")
        self.assertEqual(masked["phone"], "***")
        self.assertEqual(masked["firstName"], "Chris")

    def test_masks_nested_address(self):
        record = {"firstName": "A", "address": {"street": "123 Main", "city": "NY"}}
        masked = _mask_pii(record)
        self.assertEqual(masked["address"]["street"], "***")
        self.assertEqual(masked["address"]["city"], "***")


class TestParseLlmResponse(unittest.TestCase):
    """Tests for LLM response parsing."""

    def test_valid_json(self):
        text = json.dumps({"confidence": 0.85, "reasoning": "Names match closely"})
        result = _parse_llm_response(text)
        self.assertAlmostEqual(result["confidence"], 0.85)
        self.assertEqual(result["reasoning"], "Names match closely")

    def test_regex_fallback(self):
        text = 'Some preamble {"confidence": 0.72, "reasoning": "likely same"} trailing'
        result = _parse_llm_response(text)
        self.assertAlmostEqual(result["confidence"], 0.72)

    def test_clamps_confidence(self):
        text = json.dumps({"confidence": 1.5, "reasoning": "over"})
        result = _parse_llm_response(text)
        self.assertLessEqual(result["confidence"], 1.0)

    def test_unparseable_returns_default(self):
        result = _parse_llm_response("totally unparseable garbage")
        self.assertAlmostEqual(result["confidence"], 0.5)


class TestBuildPrompt(unittest.TestCase):
    """Tests for prompt construction."""

    def test_contains_both_records(self):
        prompt = _build_prompt(INCOMING, CANDIDATE)
        self.assertIn("Chris", prompt)
        self.assertIn("Chrish", prompt)
        self.assertIn("Record A", prompt)
        self.assertIn("Record B", prompt)


class TestHandlerEarlyReturn(unittest.TestCase):
    """Tests for score-range gating (no Bedrock call)."""

    def test_low_score_returns_early(self):
        event = {
            "incomingRecord": INCOMING,
            "candidateRecord": CANDIDATE,
            "ruleBasedScore": 0.2,
        }
        result = handler(event, None)
        self.assertEqual(result["matchingMethod"], "rule_based_only")
        self.assertAlmostEqual(result["finalScore"], 0.2)

    def test_high_score_returns_early(self):
        event = {
            "incomingRecord": INCOMING,
            "candidateRecord": CANDIDATE,
            "ruleBasedScore": 0.95,
        }
        result = handler(event, None)
        self.assertEqual(result["matchingMethod"], "rule_based_only")
        self.assertAlmostEqual(result["finalScore"], 0.95)

    def test_boundary_0_4_is_processed(self):
        """Score exactly 0.4 should trigger LLM (inside ambiguous range)."""
        with patch("tools.llm_match.handler.boto3") as mock_boto:
            mock_client = MagicMock()
            mock_boto.client.return_value = mock_client
            mock_client.invoke_model.return_value = _mock_bedrock_response(0.8, "match")

            event = {
                "incomingRecord": INCOMING,
                "candidateRecord": CANDIDATE,
                "ruleBasedScore": 0.4,
            }
            result = handler(event, None)
            self.assertEqual(result["matchingMethod"], "rule+llm")

    def test_boundary_0_9_returns_early(self):
        """Score exactly 0.9 should NOT trigger LLM (outside range)."""
        event = {
            "incomingRecord": INCOMING,
            "candidateRecord": CANDIDATE,
            "ruleBasedScore": 0.9,
        }
        result = handler(event, None)
        self.assertEqual(result["matchingMethod"], "rule_based_only")


class TestHandlerWithBedrock(unittest.TestCase):
    """Tests with mocked Bedrock responses."""

    @patch("tools.llm_match.handler.boto3")
    def test_successful_llm_match(self, mock_boto):
        mock_client = MagicMock()
        mock_boto.client.return_value = mock_client
        mock_client.invoke_model.return_value = _mock_bedrock_response(
            0.85, "Names are very similar, DOB matches"
        )

        event = {
            "incomingRecord": INCOMING,
            "candidateRecord": CANDIDATE,
            "ruleBasedScore": 0.65,
        }
        result = handler(event, None)

        self.assertEqual(result["matchingMethod"], "rule+llm")
        self.assertAlmostEqual(result["llmScore"], 0.85)
        self.assertAlmostEqual(result["ruleBasedScore"], 0.65)
        # finalScore = 0.6 * 0.65 + 0.4 * 0.85 = 0.39 + 0.34 = 0.73
        self.assertAlmostEqual(result["finalScore"], 0.73, places=2)
        self.assertIn("Names are very similar", result["reasoning"])

    @patch("tools.llm_match.handler.boto3")
    def test_bedrock_failure_fallback(self, mock_boto):
        mock_client = MagicMock()
        mock_boto.client.return_value = mock_client
        mock_client.invoke_model.side_effect = Exception("Service unavailable")

        event = {
            "incomingRecord": INCOMING,
            "candidateRecord": CANDIDATE,
            "ruleBasedScore": 0.65,
        }
        result = handler(event, None)

        self.assertEqual(result["matchingMethod"], "rule_based_only")
        self.assertAlmostEqual(result["finalScore"], 0.65)
        self.assertIn("LLM unavailable", result["fallbackReason"])

    @patch("tools.llm_match.handler.boto3")
    def test_score_combination_weights(self, mock_boto):
        """Verify 60/40 weighting: finalScore = 0.6 * rule + 0.4 * llm."""
        mock_client = MagicMock()
        mock_boto.client.return_value = mock_client
        mock_client.invoke_model.return_value = _mock_bedrock_response(1.0, "perfect match")

        event = {
            "incomingRecord": INCOMING,
            "candidateRecord": CANDIDATE,
            "ruleBasedScore": 0.5,
        }
        result = handler(event, None)

        # 0.6 * 0.5 + 0.4 * 1.0 = 0.30 + 0.40 = 0.70
        self.assertAlmostEqual(result["finalScore"], 0.70, places=2)

    @patch("tools.llm_match.handler.boto3")
    def test_json_body_event(self, mock_boto):
        """Handler supports event with JSON string body."""
        mock_client = MagicMock()
        mock_boto.client.return_value = mock_client
        mock_client.invoke_model.return_value = _mock_bedrock_response(0.7, "likely")

        event = {"body": json.dumps({
            "incomingRecord": INCOMING,
            "candidateRecord": CANDIDATE,
            "ruleBasedScore": 0.6,
        })}
        result = handler(event, None)
        self.assertEqual(result["matchingMethod"], "rule+llm")


if __name__ == "__main__":
    unittest.main()
