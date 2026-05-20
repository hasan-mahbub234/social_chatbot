"""
Hallucination Evaluator — measures hallucination rate across a test set.

Runs the hallucination validator against known (query, context, expected_answer)
triples and reports:
  - Hallucination rate
  - False positive rate (flagged as hallucination when answer was correct)
  - Average hallucination score
  - Risk level distribution
"""
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class HallucinationEvalResult:
    query: str
    hallucination_score: float
    risk_level: str
    is_hallucination: bool
    expected_hallucination: bool    # ground truth label
    correct_classification: bool
    latency_ms: float


@dataclass
class HallucinationEvalSummary:
    total: int
    hallucination_rate: float
    avg_score: float
    accuracy: float                 # correct classifications / total
    risk_distribution: Dict[str, int] = field(default_factory=dict)
    false_positives: int = 0        # flagged as hallucination but was correct
    false_negatives: int = 0        # missed actual hallucinations


class HallucinationEvaluator:
    """Evaluate hallucination detection accuracy."""

    async def evaluate(
        self,
        test_cases: List[Dict[str, Any]],
    ) -> HallucinationEvalSummary:
        """
        Run hallucination evaluation.

        Each test case:
        {
          "query": str,
          "response": str,
          "context": [str],           # RAG context used
          "is_hallucination": bool,   # ground truth
        }
        """
        from app.hallucination.validator import hallucination_validator

        results: List[HallucinationEvalResult] = []

        for case in test_cases:
            t0 = time.monotonic()
            try:
                result = await hallucination_validator.validate(
                    query=case["query"],
                    response=case["response"],
                    context=case.get("context", []),
                )
            except Exception as e:
                logger.warning("hallucination_eval_failed", error=str(e))
                continue
            latency_ms = (time.monotonic() - t0) * 1000

            expected = case.get("is_hallucination", False)
            detected = result["is_hallucination_likely"]
            correct = detected == expected

            results.append(HallucinationEvalResult(
                query=case["query"],
                hallucination_score=result["hallucination_score"],
                risk_level=result["risk_level"],
                is_hallucination=detected,
                expected_hallucination=expected,
                correct_classification=correct,
                latency_ms=latency_ms,
            ))

        return self._summarize(results)

    def _summarize(self, results: List[HallucinationEvalResult]) -> HallucinationEvalSummary:
        total = len(results)
        if total == 0:
            return HallucinationEvalSummary(0, 0.0, 0.0, 0.0)

        hallucination_count = sum(1 for r in results if r.is_hallucination)
        avg_score = sum(r.hallucination_score for r in results) / total
        accuracy = sum(1 for r in results if r.correct_classification) / total
        fp = sum(1 for r in results if r.is_hallucination and not r.expected_hallucination)
        fn = sum(1 for r in results if not r.is_hallucination and r.expected_hallucination)

        risk_dist: Dict[str, int] = {}
        for r in results:
            risk_dist[r.risk_level] = risk_dist.get(r.risk_level, 0) + 1

        return HallucinationEvalSummary(
            total=total,
            hallucination_rate=round(hallucination_count / total, 3),
            avg_score=round(avg_score, 2),
            accuracy=round(accuracy, 3),
            risk_distribution=risk_dist,
            false_positives=fp,
            false_negatives=fn,
        )


hallucination_evaluator = HallucinationEvaluator()
