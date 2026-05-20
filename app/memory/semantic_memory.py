"""
Semantic Memory — stores and retrieves important facts extracted from conversations.

Unlike conversation_memory (raw message history), semantic memory stores
distilled facts: "User's name is Ahmed", "User ordered item X last week",
"User prefers cash on delivery".

These facts persist across sessions and are injected into the system prompt
when relevant to the current query.
"""
import json
import time
from typing import Any, Dict, List, Optional
from app.core.logging import get_logger

logger = get_logger(__name__)

SEMANTIC_MEMORY_TTL = 86400 * 30    # 30 days
SEMANTIC_MEMORY_KEY = "semantic_memory:{conversation_id}"
MAX_FACTS = 20


class SemanticMemory:
    """
    Store distilled facts from conversations for long-term recall.

    Facts are extracted from assistant responses and user statements
    that contain persistent information (names, preferences, orders).
    """

    def _key(self, conversation_id: str) -> str:
        return SEMANTIC_MEMORY_KEY.format(conversation_id=conversation_id)

    async def store_fact(
        self,
        conversation_id: str,
        fact: str,
        fact_type: str = "general",     # preference | order | identity | general
        confidence: float = 0.8,
    ) -> None:
        """Store a distilled fact."""
        try:
            from app.core.redis_client import redis_client
            raw = await redis_client.get(self._key(conversation_id))
            facts: List[Dict] = json.loads(raw) if raw else []

            # Avoid duplicate facts
            if not any(f["fact"].lower() == fact.lower() for f in facts):
                facts.append({
                    "fact": fact,
                    "type": fact_type,
                    "confidence": confidence,
                    "timestamp": time.time(),
                })
                facts = facts[-MAX_FACTS:]
                await redis_client.set(self._key(conversation_id), json.dumps(facts), ex=SEMANTIC_MEMORY_TTL)
        except Exception as e:
            logger.warning("semantic_memory_store_failed", error=str(e))

    async def get_relevant_facts(
        self,
        conversation_id: str,
        query: str,
        max_facts: int = 5,
    ) -> List[str]:
        """Retrieve facts relevant to the current query."""
        try:
            from app.core.redis_client import redis_client
            raw = await redis_client.get(self._key(conversation_id))
            if not raw:
                return []
            facts: List[Dict] = json.loads(raw)

            # Simple keyword relevance: return facts whose keywords appear in query
            query_words = set(query.lower().split())
            scored = []
            for f in facts:
                fact_words = set(f["fact"].lower().split())
                overlap = len(query_words & fact_words)
                scored.append((overlap, f["fact"]))

            scored.sort(reverse=True)
            return [fact for _, fact in scored[:max_facts] if _ > 0] or [
                f["fact"] for f in facts[-max_facts:]  # fallback: most recent
            ]
        except Exception:
            return []

    async def extract_and_store(
        self,
        conversation_id: str,
        user_message: str,
        assistant_response: str,
    ) -> None:
        """
        Extract facts from a conversation turn and store them.
        Uses simple pattern matching — no LLM call needed.
        """
        import re

        # Extract user name
        name_m = re.search(r"(?:my name is|i am|i'm|call me)\s+([A-Z][a-z]+)", user_message, re.I)
        if name_m:
            await self.store_fact(conversation_id, f"User's name is {name_m.group(1)}", "identity", 0.9)

        # Extract order references
        order_m = re.search(r'\b(ORD-?\d{4,}|order\s+#?\d{4,})\b', user_message, re.I)
        if order_m:
            await self.store_fact(conversation_id, f"User referenced order {order_m.group(1)}", "order", 0.85)

        # Extract payment preference
        if "cash on delivery" in user_message.lower() or "cod" in user_message.lower():
            await self.store_fact(conversation_id, "User prefers cash on delivery", "preference", 0.8)

        # Extract location
        location_m = re.search(
            r'\b(dhaka|chittagong|ctg|sylhet|khulna|rajshahi|gulshan|dhanmondi|mirpur)\b',
            user_message, re.I
        )
        if location_m:
            await self.store_fact(
                conversation_id,
                f"User is located in {location_m.group(1).title()}",
                "identity", 0.75,
            )

    async def format_for_prompt(self, conversation_id: str, query: str) -> str:
        """Return facts formatted for injection into system prompt."""
        facts = await self.get_relevant_facts(conversation_id, query)
        if not facts:
            return ""
        return "Known facts about this user: " + "; ".join(facts)


semantic_memory = SemanticMemory()
