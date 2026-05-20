"""Tests for hallucination detection."""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_contradiction_checker_detects_contradiction():
    """Test contradiction checker finds contradictions."""
    from app.hallucination.contradiction_checker import ContradictionChecker

    checker = ContradictionChecker()
    text = "The sky is blue. However, the sky is not blue. Although it appears blue, it is actually red."
    score = checker.check(text)
    assert score > 0.2


@pytest.mark.asyncio
async def test_contradiction_checker_clean_text():
    """Test contradiction checker passes clean text."""
    from app.hallucination.contradiction_checker import ContradictionChecker

    checker = ContradictionChecker()
    text = "Python is a programming language. It is widely used for data science."
    score = checker.check(text)
    assert score < 0.5


@pytest.mark.asyncio
async def test_unsupported_claim_detector_no_context():
    """Test unsupported claim detector with no context."""
    from app.hallucination.unsupported_claim_detector import UnsupportedClaimDetector

    detector = UnsupportedClaimDetector()
    result = await detector.detect("Paris is the capital of France.", [])
    assert "No context provided" in result["reason"]


@pytest.mark.asyncio
async def test_hallucination_validator_low_score_for_relevant():
    """Test validator gives low score for relevant response."""
    from app.hallucination.validator import HallucinationValidator
    from unittest.mock import patch, AsyncMock

    validator = HallucinationValidator()

    with patch("app.hallucination.validator.contradiction_checker") as mock_cc, \
         patch("app.hallucination.validator.confidence_scorer") as mock_cs, \
         patch("app.hallucination.validator.unsupported_claim_detector") as mock_ucd:

        mock_cc.check.return_value = 0.0
        mock_cc.check_against_context.return_value = 0.0
        mock_cs.score = AsyncMock(return_value=0.9)
        mock_ucd.detect = AsyncMock(return_value={"supported": True, "unsupported_ratio": 0.1, "reason": "ok"})

        result = await validator.validate(
            query="What is Python?",
            response="Python is a high-level programming language.",
            context=["Python is a programming language created by Guido van Rossum."],
        )

        assert result["hallucination_score"] < 50
        assert result["risk_level"] in ("minimal", "low")


@pytest.mark.asyncio
async def test_confidence_scorer_language_quality():
    """Test confidence scorer language quality assessment."""
    from app.hallucination.confidence_scorer import ConfidenceScorer

    scorer = ConfidenceScorer()

    # Overconfident text should score lower
    overconfident = "This will absolutely definitely always work perfectly."
    score_over = scorer._score_language(overconfident)

    # Balanced text should score higher
    balanced = "This approach may work well in most cases, though results could vary."
    score_balanced = scorer._score_language(balanced)

    assert score_balanced > score_over
