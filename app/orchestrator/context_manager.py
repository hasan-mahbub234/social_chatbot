"""Context manager — builds LLM message history with memory compression."""
import re
from typing import List, Dict, Any, Optional
from pathlib import Path
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_SYSTEM_PROMPT = """You are a helpful assistant for this store. Answer using ONLY the information provided in the context below.

CRITICAL RULES:

1. USE ONLY THE CONTEXT. Never add information not present in the context.
   This includes addresses, phone numbers, emails, office locations, policies, prices, and product details.
   If the context says the address is "Kamrangir char, dhaka" then say exactly that. Do not change or embellish it.

2. IF THE INFORMATION IS NOT IN THE CONTEXT:
   Say: I don't have that information. Please contact us directly for help.
   Do NOT guess, invent, or fill in details you don't have.
   Do NOT suggest or mention any other brands, websites, or stores (e.g. Uniqlo, H&M, Zara, Amazon).

3. ANSWER ONLY WHAT WAS ASKED. Do not add unrequested details.

4. NO FORMATTING. Plain text only. No asterisks, no bold, no bullet symbols, no markdown links, no numbered lists.
   Write in natural sentences.

5. MULTIPLE VARIANTS: For product queries, consolidate same-product variants into one answer.

6. PRODUCT LINKS: Each context block starts with "URL: <url>". When answering a product query,
   end your reply with that product URL. For website/store link queries, use the base domain from the URL.
   Only include URLs that appear in the context. Never invent URLs.

7. Reply in the same language the user used.
"""

# Loaded once at startup
_PRODUCT_INTELLIGENCE_PROMPT: Optional[str] = None


def _load_product_prompt() -> str:
    global _PRODUCT_INTELLIGENCE_PROMPT
    if _PRODUCT_INTELLIGENCE_PROMPT is None:
        try:
            p = Path(__file__).parent.parent / "prompts" / "rag" / "answer_generation.txt"
            _PRODUCT_INTELLIGENCE_PROMPT = p.read_text(encoding="utf-8")
        except Exception:
            _PRODUCT_INTELLIGENCE_PROMPT = DEFAULT_SYSTEM_PROMPT
    return _PRODUCT_INTELLIGENCE_PROMPT


# Keywords that indicate a product-detail query needing full structured output
_PRODUCT_DETAIL_KEYWORDS = {
    "tell me about", "show me", "details", "description", "spec", "specs",
    "all variants", "full details", "everything about",
}

# Simple field keywords — answered with DEFAULT_SYSTEM_PROMPT, not the full intelligence prompt
_SIMPLE_FIELD_RE = re.compile(
    r'\b(how much|price|cost|available|in stock|out of stock|availability|'
    r'material|fabric|sku|shipping|delivery|return|exchange|refund|'
    r'size|sizes|color|colour|colors|colours|weight|dimension|brand)\b',
    re.I
)


class ContextManager:
    """Build and compress conversation context for LLM calls."""

    async def build_messages(
        self,
        query: str,
        conversation_id: str,
        rag_context: List[str],
        db: Session,
        system_prompt: str = None,
        agent_id: str = None,
        personalization_hint: str = "",
        memory_facts: str = "",
        skip_history: bool = False,
    ) -> List[Dict[str, str]]:
        """Build message list for LLM including history and RAG context."""

        # 1. Resolve system prompt
        resolved_prompt = system_prompt

        if not resolved_prompt and agent_id:
            resolved_prompt = await self._load_agent_prompt(agent_id, db)

        is_product_query = self._is_product_query(query)
        is_simple_field = bool(_SIMPLE_FIELD_RE.search(query))

        if not resolved_prompt:
            if rag_context and is_product_query and not is_simple_field:
                resolved_prompt = _load_product_prompt()
            else:
                resolved_prompt = DEFAULT_SYSTEM_PROMPT

        messages = [{"role": "system", "content": resolved_prompt}]

        # Inject personalization and semantic memory (skip for structured path)
        if not skip_history and (personalization_hint or memory_facts):
            memory_context = "\n".join(filter(None, [personalization_hint, memory_facts]))
            messages.append({"role": "system", "content": memory_context})

        # 2. Adaptive RAG context size
        # Structured path: context is already minimal (metadata fields only)
        # RAG path: limit by query complexity
        if skip_history:
            # Structured execution — context is already pre-minimized
            max_chunks, chunk_limit = 1, 600
        elif is_simple_field:
            max_chunks, chunk_limit = 2, 800
        elif is_product_query:
            max_chunks, chunk_limit = 4, 1500
        else:
            words = len(query.split())
            if words <= 3:
                max_chunks, chunk_limit = 2, 500
            elif words <= 8:
                max_chunks, chunk_limit = 3, 800
            else:
                max_chunks, chunk_limit = 4, 1000

        if rag_context:
            truncated = [c[:chunk_limit] for c in rag_context[:max_chunks]]
            context_text = "\n\n---\n\n".join(truncated)
            # For product intelligence prompt, inject context as {context} placeholder
            if "{context}" in resolved_prompt:
                messages[0]["content"] = resolved_prompt.replace(
                    "{context}", context_text
                ).replace("{question}", "").rstrip()
            else:
                messages.append({
                    "role": "system",
                    "content": f"Product context:\n{context_text}",
                })

        # 3. Load recent conversation history (skipped for structured path)
        if not skip_history:
            history = await self._load_history(conversation_id, db)
            trimmed_history = []
            for m in history[-4:]:
                if m["role"] == "assistant":
                    trimmed_history.append({"role": m["role"], "content": m["content"][:300]})
                else:
                    trimmed_history.append({"role": m["role"], "content": m["content"][:100]})
            messages.extend(trimmed_history)

        # 4. Current query
        messages.append({"role": "user", "content": query})

        messages = self._compress(messages)
        return messages

    def _is_product_query(self, query: str) -> bool:
        """Detect if the query needs the full product intelligence prompt."""
        q = query.lower()
        # Only use the full prompt for explicit detail requests
        return any(kw in q for kw in _PRODUCT_DETAIL_KEYWORDS)

    async def _load_agent_prompt(self, agent_id: str, db: Session) -> Optional[str]:
        """Load agent's custom system_prompt from DB if set."""
        try:
            from app.models.agent import Agent
            import uuid
            agent = db.query(Agent).filter(
                Agent.id == uuid.UUID(str(agent_id)),
                Agent.is_active == True,
            ).first()
            if agent and agent.system_prompt and len(agent.system_prompt.strip()) > 20:
                return agent.system_prompt.strip()
        except Exception as e:
            logger.debug("agent_prompt_load_failed", agent_id=agent_id, error=str(e))
        return None

    async def _load_history(self, conversation_id: str, db: Session) -> List[Dict[str, str]]:
        """Load recent messages — Redis first, DB fallback for persistence across restarts."""
        try:
            from app.memory.conversation_memory import conversation_memory
            messages = await conversation_memory.get(conversation_id, limit=10)
            if messages:
                return messages
            # Fallback: load from DB messages table
            from app.models.message import Message
            rows = (
                db.query(Message)
                .filter(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.desc())
                .limit(10)
                .all()
            )
            return [{"role": m.role, "content": m.content} for m in reversed(rows)]
        except Exception as e:
            logger.warning("history_load_failed", error=str(e))
            return []

    def _compress(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Trim messages to stay within token budget."""
        total = sum(len(m["content"]) // 4 for m in messages)
        while total > settings.MAX_CONTEXT_TOKENS and len(messages) > 2:
            # Remove oldest non-system message
            for i, m in enumerate(messages):
                if m["role"] != "system":
                    total -= len(m["content"]) // 4
                    messages.pop(i)
                    break
        return messages


context_manager = ContextManager()
