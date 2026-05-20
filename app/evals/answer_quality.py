"""
Answer Quality Evaluator — scores AI response quality using LLM-as-judge.

Dimensions scored (0-10 each):
  - Relevance: does the answer address the question?
  - Accuracy: is the answer factually consistent with the context?
  - Completeness: does the answer cover all aspects of the question?
  - Conciseness: is the answer appropriately brief?
  - Groundedness: is every claim supported by the provided context?
"""
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from app.core.logging import get_logger

logger = get_logger(__name__)

_JUDGE_PROMPT = """You are an AI quality evaluator. Score the following AI response on 5 dimensions.

Question: {query}

Context provided to AI:
{context}

AI Response:
{response}

Score each dimension from 0-10 (10 = perfect). Reply ONLY with valid JSON:
{{
  "relevance": <0-10>,
  "accuracy": <0-10>,
  "completeness": <0-10>,
  "conciseness": <0-10>,
  "groundedness": <0-10>,
  "reasoning": "<one sentence>"
}}"""


@dataclass
class AnswerQualityScore:
    query: str
    relevance: float
    accuracy: float
    completeness: float
    conciseness: float
    groundedness: float
    overall: float
    reasoning: str
    latency_ms: float


@dataclass
class AnswerQualitySummary:
    total: int
    avg_relevance: float
    avg_accuracy: float
    avg_completeness: float
    avg_conciseness: float
    avg_groundedness: float
    avg_overall: float
    low_quality_queries: List[str] = field(default_factory=list)  # overall < 5


class AnswerQualityEvaluator:
    """LLM-as-judge answer quality evaluator."""

    async def evaluate(
        self,
        test_cases: List[Dict[str, Any]],
        judge_model: Optional[str] = None,
    ) -> AnswerQualitySummary:
        """
        Evaluate answer quality using LLM judge.

        Each test case: {"query": str, "response": str, "context": [str]}
        """
        from app.services.llm import llm_service
        from app.core.constants import GPT4O_MINI

        model = judge_model or GPT4O_MINI
        scores: List[AnswerQualityScore] = []

        for case in test_cases:
            t0 = time.monotonic()
            context_text = "\n\n".join(case.get("context", []))[:2000]
            prompt = _JUDGE_PROMPT.format(
                query=case["query"],
                context=context_text or "(no context provided)",
                response=case["response"],
            )
            try:
                raw = await llm_service.generate_response(
                    messages=[{"role": "user", "content": prompt}],
                    model=model,
                )
                parsed = json.loads(raw)
                dims = ["relevance", "accuracy", "completeness", "conciseness", "groundedness"]
                overall = sum(parsed.get(d, 5) for d in dims) / len(dims)
                scores.append(AnswerQualityScore(
                    query=case["query"],
                    relevance=float(parsed.get("relevance", 5)),
                    accuracy=float(parsed.get("accuracy", 5)),
                    completeness=float(parsed.get("completeness", 5)),
                    conciseness=float(parsed.get("conciseness", 5)),
                    groundedness=float(parsed.get("groundedness", 5)),
                    overall=round(overall, 2),
                    reasoning=parsed.get("reasoning", ""),
                    latency_ms=(time.monotonic() - t0) * 1000,
                ))
            except Exception as e:
                logger.warning("answer_quality_eval_failed", query=case["query"][:60], error=str(e))

        return self._summarize(scores)

    def _summarize(self, scores: List[AnswerQualityScore]) -> AnswerQualitySummary:
        total = len(scores)
        if total == 0:
            return AnswerQualitySummary(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

        def avg(attr: str) -> float:
            return round(sum(getattr(s, attr) for s in scores) / total, 2)

        low_quality = [s.query for s in scores if s.overall < 5.0]

        return AnswerQualitySummary(
            total=total,
            avg_relevance=avg("relevance"),
            avg_accuracy=avg("accuracy"),
            avg_completeness=avg("completeness"),
            avg_conciseness=avg("conciseness"),
            avg_groundedness=avg("groundedness"),
            avg_overall=avg("overall"),
            low_quality_queries=low_quality,
        )


answer_quality_evaluator = AnswerQualityEvaluator()
