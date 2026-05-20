"""Request router — normalizes and classifies incoming requests."""
from typing import Dict, Any
from app.core.logging import get_logger

logger = get_logger(__name__)

GREETING_PATTERNS = {"hi", "hello", "hey", "good morning", "good evening", "howdy", "greetings", "sup", "yo"}
SMALL_TALK_PATTERNS = {"love you", "i love you", "how are you", "who are you", "what are you", "are you there", "you there", "thank you", "thanks", "ok", "okay", "cool", "nice", "great", "awesome"}
FAQ_KEYWORDS = {"what", "how", "why", "when", "where", "who", "which", "explain", "define", "tell me", "describe", "capital", "meaning"}
SUMMARY_KEYWORDS = {"summarize", "summary", "tldr", "brief", "overview", "recap", "shorten"}
REASONING_KEYWORDS = {"analyze", "reason", "compare", "evaluate", "assess", "pros and cons", "difference", "versus", "vs", "better", "recommend", "should i"}
SUPPORT_KEYWORDS = {"error", "issue", "problem", "not working", "broken", "fix", "bug", "fail", "crash", "trouble"}
PRICING_KEYWORDS = {"price", "cost", "pricing", "plan", "subscription", "fee", "charge", "billing", "pay", "discount"}
BUSINESS_KEYWORDS = {"product", "service", "policy", "return", "refund", "delivery", "order", "account", "feature", "document", "report", "data", "company", "our", "we offer", "you offer"}

# Intents that skip heavy pipeline (no RAG, no hallucination, no cache lookup)
FAST_PATH_INTENTS = {"greeting", "small_talk", "identity"}


class RequestRouter:
    """Normalize and classify incoming requests."""

    async def normalize(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize query, detect intent, and set pipeline flags."""
        clean_query = query.strip()
        intent = self._classify_intent(clean_query)
        is_fast_path = intent in FAST_PATH_INTENTS

        return {
            "original_query": query,
            "normalized_query": clean_query,
            "intent": intent,
            "is_fast_path": is_fast_path,
            "needs_rag": not is_fast_path,
            "needs_cache": not is_fast_path,
            "needs_hallucination": not is_fast_path,
            "needs_risk": not is_fast_path,
            "context": context,
        }

    def _classify_intent(self, query: str) -> str:
        """Rule-based intent classification."""
        lower = query.lower().strip()

        # Greeting
        if any(lower.startswith(g) for g in GREETING_PATTERNS) and len(query) < 40:
            return "greeting"

        # Small talk / identity
        if any(p in lower for p in SMALL_TALK_PATTERNS) and len(query) < 60:
            return "small_talk"

        if any(p in lower for p in {"your name", "who are you", "what are you", "are you a bot", "are you ai", "are you human"}):
            return "identity"

        # Business / knowledge (full pipeline)
        if any(k in lower for k in BUSINESS_KEYWORDS):
            return "business"

        # Support
        if any(k in lower for k in SUPPORT_KEYWORDS):
            return "support"

        # Pricing
        if any(k in lower for k in PRICING_KEYWORDS):
            return "pricing"

        # Summarization
        if any(k in lower for k in SUMMARY_KEYWORDS):
            return "summarization"

        # Reasoning
        if any(k in lower for k in REASONING_KEYWORDS):
            return "reasoning"

        # FAQ
        if any(k in lower for k in FAQ_KEYWORDS) or lower.endswith("?"):
            return "faq"

        return "general"


request_router = RequestRouter()
