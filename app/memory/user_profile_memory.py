"""
User Profile Memory — persists long-term user preferences and behavior patterns.

Stores per-user:
  - Preferred product categories
  - Price range preferences
  - Size/color preferences
  - Communication style (formal/casual)
  - Frequently asked topics
  - Last active products

Used to personalize RAG retrieval and response generation.
"""
import json
import time
from typing import Any, Dict, List, Optional
from app.core.logging import get_logger

logger = get_logger(__name__)

PROFILE_TTL = 86400 * 90    # 90 days
PROFILE_KEY = "user_profile:{user_id}:{org_id}"


class UserProfileMemory:
    """
    Persist and retrieve user preference profiles.

    Profiles are built incrementally from conversation signals:
    - Products viewed/asked about → category preferences
    - Price queries → price range preferences
    - Size/color mentions → attribute preferences
    - Query language → communication style
    """

    def _key(self, user_id: str, org_id: str) -> str:
        return PROFILE_KEY.format(user_id=user_id, org_id=org_id)

    async def get(self, user_id: str, org_id: str) -> Dict[str, Any]:
        """Get user profile. Returns empty profile if not found."""
        try:
            from app.core.redis_client import redis_client
            raw = await redis_client.get(self._key(user_id, org_id))
            if raw:
                return json.loads(raw)
        except Exception:
            pass
        return self._empty_profile(user_id, org_id)

    async def update_from_query(
        self,
        user_id: str,
        org_id: str,
        query: str,
        intent: str,
        entities: List[str],
        constraints: Dict[str, Any],
    ) -> None:
        """Update profile based on a query signal."""
        profile = await self.get(user_id, org_id)

        # Track intent frequency
        intent_counts = profile.setdefault("intent_counts", {})
        intent_counts[intent] = intent_counts.get(intent, 0) + 1

        # Track entity/product interest
        if entities:
            recent_entities = profile.setdefault("recent_entities", [])
            recent_entities.extend(entities)
            profile["recent_entities"] = list(dict.fromkeys(recent_entities))[-20:]

        # Track price preferences
        if "price_max" in constraints:
            price_history = profile.setdefault("price_max_history", [])
            price_history.append(constraints["price_max"])
            profile["price_max_history"] = price_history[-10:]
            profile["preferred_price_max"] = int(sum(price_history) / len(price_history))

        # Track size preference
        if "size" in constraints:
            profile["preferred_size"] = constraints["size"]

        # Track color preference
        if "color" in constraints:
            color_counts = profile.setdefault("color_counts", {})
            color_counts[constraints["color"]] = color_counts.get(constraints["color"], 0) + 1

        # Detect language preference
        if any(ord(c) > 0x0980 for c in query):
            profile["language_preference"] = "bengali"
        elif profile.get("language_preference") != "bengali":
            profile["language_preference"] = "english"

        profile["last_active"] = time.time()
        profile["query_count"] = profile.get("query_count", 0) + 1

        await self._save(user_id, org_id, profile)

    async def get_personalization_context(self, user_id: str, org_id: str) -> str:
        """
        Return a short personalization hint for the LLM system prompt.
        Only included when profile has meaningful signals.
        """
        profile = await self.get(user_id, org_id)
        hints = []

        if profile.get("preferred_size"):
            hints.append(f"User's preferred size: {profile['preferred_size']}")

        if profile.get("preferred_price_max"):
            hints.append(f"User typically looks for items under {profile['preferred_price_max']} BDT")

        color_counts = profile.get("color_counts", {})
        if color_counts:
            fav_color = max(color_counts, key=color_counts.get)
            if color_counts[fav_color] >= 2:
                hints.append(f"User frequently asks about {fav_color} items")

        if profile.get("language_preference") == "bengali":
            hints.append("User prefers Bengali/mixed language responses")

        return ". ".join(hints) if hints else ""

    async def _save(self, user_id: str, org_id: str, profile: Dict) -> None:
        try:
            from app.core.redis_client import redis_client
            await redis_client.set(
                self._key(user_id, org_id),
                json.dumps(profile),
                ex=PROFILE_TTL,
            )
        except Exception as e:
            logger.warning("user_profile_save_failed", error=str(e))

    def _empty_profile(self, user_id: str, org_id: str) -> Dict[str, Any]:
        return {
            "user_id": user_id,
            "org_id": org_id,
            "query_count": 0,
            "intent_counts": {},
            "recent_entities": [],
            "color_counts": {},
            "language_preference": "english",
            "last_active": None,
        }


user_profile_memory = UserProfileMemory()
