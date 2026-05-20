"""Tests for risk engine."""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_fraud_detector_finds_patterns():
    """Test fraud detector identifies fraud patterns."""
    from app.risk.fraud_detection import FraudDetector

    detector = FraudDetector()
    result = detector.detect("Please send a wire transfer to this account urgently")
    assert result["is_fraud_risk"] is True
    assert result["score"] > 0


@pytest.mark.asyncio
async def test_fraud_detector_clean_text():
    """Test fraud detector passes clean text."""
    from app.risk.fraud_detection import FraudDetector

    detector = FraudDetector()
    result = detector.detect("How do I configure a database connection?")
    assert result["is_fraud_risk"] is False
    assert result["score"] == 0.0


@pytest.mark.asyncio
async def test_scoring_level_conversion():
    """Test score to risk level conversion."""
    from app.risk.scoring import score_to_level

    assert score_to_level(10) == "low"
    assert score_to_level(40) == "medium"
    assert score_to_level(65) == "high"
    assert score_to_level(85) == "critical"


@pytest.mark.asyncio
async def test_escalation_rules_high_score():
    """Test escalation rules trigger on high risk score."""
    from app.risk.escalation_rules import EscalationRules

    rules = EscalationRules()
    result = rules.should_escalate({"risk_score": 80, "fraud_score": 0})
    assert result["escalate"] is True
    assert "high_risk_score" in result["triggered_rules"]


@pytest.mark.asyncio
async def test_escalation_rules_jailbreak():
    """Test escalation rules trigger on jailbreak."""
    from app.risk.escalation_rules import EscalationRules

    rules = EscalationRules()
    result = rules.should_escalate({"risk_score": 10, "jailbreak_detected": True})
    assert result["escalate"] is True
    assert result["severity"] == "critical"


@pytest.mark.asyncio
async def test_risk_engine_pii_detection():
    """Test risk engine detects PII in text."""
    from app.risk.risk_engine import RiskEngine
    from unittest.mock import patch, AsyncMock

    engine = RiskEngine()

    with patch("app.risk.risk_engine.abuse_detector") as mock_abuse:
        mock_abuse.check = AsyncMock(return_value={"score": 0.0, "is_abuse": False, "risk_level": "low"})

        result = await engine.score(
            text="My email is user@example.com and SSN is 123-45-6789",
            user_id="test-user",
            organization_id="test-org",
        )

        assert result["risk_score"] > 0
        assert "pii" in result["reason"] or "PII" in result["reason"]


@pytest.mark.asyncio
async def test_risk_engine_clean_text():
    """Test risk engine gives low score for clean text."""
    from app.risk.risk_engine import RiskEngine
    from unittest.mock import patch, AsyncMock

    engine = RiskEngine()

    with patch("app.risk.risk_engine.abuse_detector") as mock_abuse:
        mock_abuse.check = AsyncMock(return_value={"score": 0.0, "is_abuse": False, "risk_level": "low"})

        result = await engine.score(
            text="How do I write a Python function?",
            user_id="test-user",
            organization_id="test-org",
        )

        assert result["risk_score"] < 30
        assert result["escalate"] is False
