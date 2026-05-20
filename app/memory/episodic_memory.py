"""
Episodic Memory — stores significant conversation episodes for long-term recall.

An "episode" is a meaningful interaction unit: a resolved support issue,
a completed product inquiry, a successful recommendation.

Unlike raw message history, episodes are compressed summaries of what happened
and what was resolved — enabling the AI to recall past interactions across sessions.
"""
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from app.core.logging import get_logger

logger = get_logger(__name__)

EPISODE_TTL = 86400 * 60    # 60 days
EPISODE_KEY = "episodic_memory:{user_id}:{org_id}"
MAX_EPISODES = 50


@dataclass
class Episode:
    episode_id: str
    user_id: str
    org_id: str
    summary: str                    # what happened in this episode
    intent: str                     # what the user was trying to do
    resolved: bool                  # was the issue/query resolved?
    entities_involved: List[str]    # products, policies mentioned
    timestamp: float = field(default_factory=time.time)
    conversation_id: str = ""


class EpisodicMemory:
    """
    Store and retrieve significant conversation episodes.

    Episodes are created when:
    - A conversation ends (session timeout)
    - A support issue is resolved
    - A product purchase intent is detected
    - Human escalation occurs
    """

    def _key(self, user_id: str, org_id: str) -> str:
        return EPISODE_KEY.format(user_id=user_id, org_id=org_id)

    async def store_episode(self, episode: Episode) -> None:
        """Store a conversation episode."""
        try:
            from app.core.redis_client import redis_client
            raw = await redis_client.get(self._key(episode.user_id, episode.org_id))
            episodes: List[Dict] = json.loads(raw) if raw else []

            episodes.append({
                "id":           episode.episode_id,
                "summary":      episode.summary,
                "intent":       episode.intent,
                "resolved":     episode.resolved,
                "entities":     episode.entities_involved,
                "timestamp":    episode.timestamp,
                "conv_id":      episode.conversation_id,
            })
            episodes = episodes[-MAX_EPISODES:]
            await redis_client.set(
                self._key(episode.user_id, episode.org_id),
                json.dumps(episodes),
                ex=EPISODE_TTL,
            )
            logger.info("episode_stored", user=episode.user_id, intent=episode.intent)
        except Exception as e:
            logger.warning("episode_store_failed", error=str(e))

    async def get_recent_episodes(
        self,
        user_id: str,
        org_id: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Get most recent episodes for a user."""
        try:
            from app.core.redis_client import redis_client
            raw = await redis_client.get(self._key(user_id, org_id))
            if not raw:
                return []
            episodes = json.loads(raw)
            return episodes[-limit:]
        except Exception:
            return []

    async def get_relevant_episodes(
        self,
        user_id: str,
        org_id: str,
        query: str,
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        """Get episodes relevant to the current query."""
        episodes = await self.get_recent_episodes(user_id, org_id, limit=20)
        if not episodes:
            return []

        query_words = set(query.lower().split())
        scored = []
        for ep in episodes:
            summary_words = set(ep.get("summary", "").lower().split())
            entity_words = set(" ".join(ep.get("entities", [])).lower().split())
            overlap = len(query_words & (summary_words | entity_words))
            scored.append((overlap, ep))

        scored.sort(reverse=True)
        return [ep for _, ep in scored[:limit] if _ > 0]

    async def format_for_prompt(
        self,
        user_id: str,
        org_id: str,
        query: str,
    ) -> str:
        """Return relevant episode summaries for system prompt injection."""
        episodes = await self.get_relevant_episodes(user_id, org_id, query)
        if not episodes:
            return ""
        summaries = [ep["summary"] for ep in episodes]
        return "Previous interactions: " + "; ".join(summaries)

    async def create_episode_from_conversation(
        self,
        user_id: str,
        org_id: str,
        conversation_id: str,
        messages: List[Dict[str, str]],
        intent: str,
        resolved: bool = True,
    ) -> Optional[Episode]:
        """
        Create an episode from a conversation's messages.
        Summarizes the conversation into a single episode record.
        """
        if not messages:
            return None

        # Build a simple summary from the last user message and assistant response
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        last_assistant = next((m["content"] for m in reversed(messages) if m["role"] == "assistant"), "")

        summary = f"User asked: {last_user[:100]}. Response: {last_assistant[:150]}"

        # Extract entities (capitalized words)
        import re
        entities = list(set(re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', last_user + " " + last_assistant)))[:5]

        episode = Episode(
            episode_id=f"{conversation_id}_{int(time.time())}",
            user_id=user_id,
            org_id=org_id,
            summary=summary,
            intent=intent,
            resolved=resolved,
            entities_involved=entities,
            conversation_id=conversation_id,
        )
        await self.store_episode(episode)
        return episode


episodic_memory = EpisodicMemory()
