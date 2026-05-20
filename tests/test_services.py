"""Tests for services."""
import pytest
import asyncio
from app.services.risk_assessment import risk_assessment_service
from app.services.hallucination_validator import hallucination_validator


@pytest.mark.asyncio
async def test_pii_detection():
    """Test PII detection."""
    text = "My email is john@example.com and SSN is 123-45-6789"
    result = await risk_assessment_service.detect_pii(text)

    assert "email" in result
    assert "ssn" in result


@pytest.mark.asyncio
async def test_pii_risk_assessment():
    """Test PII risk assessment."""
    text = "Contact me at john@example.com"
    result = await risk_assessment_service.assess_pii_risk(text)

    assert result["risk_level"] in ["low", "medium", "high"]
    assert "pii_detected" in result
    assert len(result["findings"]) > 0


@pytest.mark.asyncio
async def test_data_leakage_detection():
    """Test data leakage detection."""
    text = "Here is my API key: sk-abc123def456"
    result = await risk_assessment_service.assess_data_leakage_risk(text)

    assert result["risk_level"] == "high"
    assert result["is_escalated"]


@pytest.mark.asyncio
async def test_cost_risk_assessment():
    """Test cost risk assessment."""
    result = await risk_assessment_service.assess_cost_risk(
        organization_id="test-org",
        tokens_used=1000,
        cost=5.0,
        model="gpt-4-turbo",
    )

    assert "risk_level" in result
    assert "score" in result
    assert result["score"] >= 0 and result["score"] <= 100


@pytest.mark.asyncio
async def test_hallucination_detection():
    """Test hallucination detection."""
    query = "What is the capital of France?"
    response = "The capital of France is Paris, located in the heart of Europe."

    result = await hallucination_validator.validate_response(query, response)

    assert "hallucination_score" in result
    assert "risk_level" in result
    assert result["hallucination_score"] >= 0 and result["hallucination_score"] <= 100


@pytest.mark.asyncio
async def test_contradiction_detection():
    """Test self-contradiction detection."""
    text = "The cat is black. However, the cat is white."

    score = await hallucination_validator._check_self_contradiction(text)

    assert score > 0.3  # Should detect contradiction


@pytest.mark.asyncio
async def test_overconfident_language_detection():
    """Test overconfident language detection."""
    text = "This will absolutely never fail. It is definitely the best solution."

    score = await hallucination_validator._check_factual_patterns(text)

    assert score < 0.8  # Should penalize overconfidence
