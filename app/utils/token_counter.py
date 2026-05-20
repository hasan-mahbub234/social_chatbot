"""Token counter utilities."""
from typing import List, Dict
from app.core.constants import MODEL_PRICING


def count_tokens_approx(text: str) -> int:
    """Approximate token count (1 token ≈ 4 chars)."""
    return max(1, len(text) // 4)


def count_messages_tokens(messages: List[Dict[str, str]]) -> int:
    """Count tokens across a list of messages."""
    return sum(count_tokens_approx(m.get("content", "")) for m in messages)


def estimate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """Estimate cost in USD for a model call."""
    pricing = MODEL_PRICING.get(model, MODEL_PRICING.get("gpt-4o-mini"))
    return (
        (input_tokens / 1_000_000) * pricing["input"]
        + (output_tokens / 1_000_000) * pricing["output"]
    )


def tokens_to_chars(tokens: int) -> int:
    return tokens * 4


def chars_to_tokens(chars: int) -> int:
    return max(1, chars // 4)
