"""
Unit tests for CodeSentinel Agent
Run with: pytest tests/ -v
"""

import pytest
from unittest.mock import patch, MagicMock
import sys
import os

# Make sure src is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ─── Mock the Anthropic client for unit tests ──────────────────────────────────
@pytest.fixture(autouse=True)
def mock_anthropic():
    """Mock Anthropic API calls so tests don't need a real API key."""
    with patch("src.agent.client") as mock_client:
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Mocked response: no bugs found. ✅ SCORE: 95/100")]
        mock_client.messages.create.return_value = mock_response
        yield mock_client


# ─── Agent Logic Tests ─────────────────────────────────────────────────────────
class TestAgentCore:
    def test_chat_returns_string(self):
        from src.agent import chat, reset_session
        reset_session()
        result = chat("Review this code: x = 1 + 1")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_conversation_history_grows(self):
        from src.agent import chat, reset_session, conversation_history
        reset_session()
        assert len(conversation_history) == 0
        chat("Hello")
        assert len(conversation_history) == 2  # user + assistant

    def test_reset_clears_history(self):
        from src.agent import chat, reset_session, conversation_history
        reset_session()
        chat("Test message")
        assert len(conversation_history) > 0
        reset_session()
        assert len(conversation_history) == 0

    def test_chat_with_code_context(self):
        from src.agent import chat, reset_session
        reset_session()
        result = chat("Review this:", code_context="def foo(): pass")
        assert isinstance(result, str)

    def test_review_file_missing(self):
        from src.agent import review_file
        result = review_file("/nonexistent/path.py")
        assert "not found" in result.lower() or "❌" in result

    def test_review_file_existing(self, tmp_path):
        from src.agent import review_file
        f = tmp_path / "test_code.py"
        f.write_text("def add(a, b): return a + b\n")
        result = review_file(str(f))
        assert isinstance(result, str)


# ─── Evaluator Tests ───────────────────────────────────────────────────────────
class TestEvaluator:
    def test_speed_factor_excellent(self):
        from eval.evaluate import speed_factor
        assert speed_factor(2.0) == 1.0

    def test_speed_factor_good(self):
        from eval.evaluate import speed_factor
        assert speed_factor(8.0) == 0.9

    def test_speed_factor_fair(self):
        from eval.evaluate import speed_factor
        assert speed_factor(18.0) == 0.75

    def test_speed_factor_slow(self):
        from eval.evaluate import speed_factor
        assert speed_factor(30.0) == 0.6

    def test_grade_s(self):
        from eval.evaluate import grade
        assert "S" in grade(9500)

    def test_grade_a(self):
        from eval.evaluate import grade
        assert "A" in grade(8000)

    def test_grade_f(self):
        from eval.evaluate import grade
        assert "F" in grade(1000)

    def test_score_response_expected_keywords(self):
        from eval.evaluate import score_response
        tc = {
            "expected_keywords": ["bug", "injection", "fix"],
            "forbidden_keywords": [],
        }
        response = "This code has a SQL injection bug. Here is the fix."
        result = score_response(response, tc)
        assert result["correctness"] > 0.9

    def test_score_response_false_positive_penalty(self):
        from eval.evaluate import score_response
        tc = {
            "expected_keywords": ["clean", "correct"],
            "forbidden_keywords": ["bug", "vulnerability"],
        }
        response = "This code looks clean and correct. No bugs or vulnerabilities."
        result = score_response(response, tc)
        # Should be penalized for false positives
        assert result["correctness"] < 1.0
        assert len(result["false_positives"]) > 0
