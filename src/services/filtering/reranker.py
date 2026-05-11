"""
Layer 3 — LLM relevance reranker.

Only invoked for papers in the ambiguous embedding score zone
(low_threshold < score < high_threshold). For all other papers the
embedding score alone is decisive and this layer is skipped entirely.

Uses NvidiaClient.generate() with a tight, structured prompt that
instructs the model to return a JSON verdict:
  {"relevant": bool, "confidence": 0.0-1.0, "reason": str}

The reason string is stored on PaperFilterDecision.llm_reason and is
the only human-readable explanation of why a borderline paper was
accepted or rejected — useful for threshold tuning.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import List, Optional

from src.exceptions import OllamaException
from src.models.scope_profile import ScopeProfile
from src.schemas.arxiv.paper import ArxivPaper
from src.services.nvidia.client import NvidiaClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_RERANK_SYSTEM = (
    "You are a precise academic relevance classifier. "
    "You will be given a research scope description and a paper's title and abstract. "
    "Decide whether the paper is directly relevant to the research scope. "
    "Respond ONLY with a valid JSON object. No explanation outside the JSON."
)

_RERANK_PROMPT = """Research scope:
{scope_description}

Paper title: {title}

Abstract:
{abstract}

Is this paper directly relevant to the research scope described above?

Respond with ONLY this JSON object, no other text:
{{
  "relevant": <true or false>,
  "confidence": <float between 0.0 and 1.0>,
  "reason": "<one sentence explaining the decision>"
}}"""

# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class RerankerResult:
    """Result for a single paper from the LLM reranker."""

    paper: ArxivPaper
    relevant: bool
    confidence: float
    reason: str
    # False if the LLM call failed and we fell back to a default decision
    llm_succeeded: bool = True


@dataclass
class RerankerBatchResult:
    """Aggregated result for a batch sent to the LLM reranker."""

    results: List[RerankerResult]

    @property
    def accepted(self) -> List[ArxivPaper]:
        return [r.paper for r in self.results if r.relevant]

    @property
    def rejected(self) -> List[ArxivPaper]:
        return [r.paper for r in self.results if not r.relevant]

    @property
    def failed(self) -> List[RerankerResult]:
        """Results where the LLM call failed — decided by fallback."""
        return [r for r in self.results if not r.llm_succeeded]


# ---------------------------------------------------------------------------
# JSON extraction helper
# ---------------------------------------------------------------------------


def _extract_json_from_response(raw: str) -> dict:
    """
    Extract a JSON object from LLM output that may contain surrounding text.

    Tries strict parse first. Falls back to regex extraction for models that
    add a preamble or postamble despite being instructed not to.

    :param raw: Raw LLM response string
    :returns: Parsed dict
    :raises ValueError: If no valid JSON object can be extracted
    """
    # 1. Try direct parse (model obeyed the prompt)
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        pass

    # 2. Extract first {...} block via regex
    match = re.search(r"\{[^{}]+\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract JSON from LLM response: {raw[:200]!r}")


def _validate_verdict(verdict: dict) -> tuple[bool, float, str]:
    """
    Validate and normalise the parsed verdict dict.

    :param verdict: Parsed JSON dict from LLM
    :returns: Tuple of (relevant, confidence, reason)
    :raises ValueError: If required fields are missing or invalid
    """
    if "relevant" not in verdict:
        raise ValueError("Missing 'relevant' field in LLM verdict")

    relevant = bool(verdict["relevant"])
    confidence = float(verdict.get("confidence", 0.5))
    confidence = max(0.0, min(1.0, confidence))  # Clamp to [0, 1]
    reason = str(verdict.get("reason", "No reason provided"))[:500]  # Truncate

    return relevant, confidence, reason


# ---------------------------------------------------------------------------
# LLM Reranker
# ---------------------------------------------------------------------------


class LLMReranker:
    """
    Calls the LLM to make relevance decisions for ambiguous papers.

    Instantiate once per pipeline run with the active scope profile.
    Each paper gets an independent LLM call — no batching at the prompt
    level, since mixing papers in one prompt reduces decision quality.

    Failures for individual papers fall back to a conservative default
    (reject with low confidence) and are logged — they do not abort the
    batch.
    """

    def __init__(
        self,
        profile: ScopeProfile,
        llm_client: NvidiaClient,
        max_papers: int = 50,
        fallback_on_error: bool = True,
    ):
        """
        :param profile: Active ScopeProfile (description used in prompt)
        :param llm_client: Initialised NvidiaClient
        :param max_papers: Hard cap on papers sent to LLM per run (cost guard)
        :param fallback_on_error: If True, LLM failures produce a reject result
                                  rather than raising. Recommended for production.
        """
        self.profile = profile
        self.client = llm_client
        self.max_papers = max_papers
        self.fallback_on_error = fallback_on_error
        self.scope_description = profile.description

        logger.debug(
            f"LLMReranker initialised: max_papers={max_papers}, "
            f"fallback_on_error={fallback_on_error}, "
            f"model={llm_client.default_model}"
        )

    def _build_prompt(self, paper: ArxivPaper) -> str:
        return _RERANK_PROMPT.format(
            scope_description=self.scope_description,
            title=paper.title,
            abstract=paper.abstract[:2000],  # Truncate very long abstracts
        )

    def _call_llm(self, paper: ArxivPaper) -> RerankerResult:
        """
        Make a single LLM call for one paper and parse the verdict.

        Uses generate() (non-streaming) since we need the full response
        before we can parse the JSON verdict.
        """
        prompt = _RERANK_PROMPT.format(
            scope_description=self.scope_description,
            title=paper.title,
            abstract=paper.abstract[:2000],
        )

        full_prompt = f"{_RERANK_SYSTEM}\n\n{prompt}"

        try:
            response = self.client.generate(
                prompt=full_prompt,
                temperature=0.1,  # Low temperature for consistent classification
                top_p=0.9,
                max_tokens=150,  # Verdict is short — cap tokens for speed
            )

            raw_text = response.get("response", "")

            if not raw_text:
                raise ValueError("Empty response from LLM reranker")

            verdict = _extract_json_from_response(raw_text)
            relevant, confidence, reason = _validate_verdict(verdict)

            logger.debug(
                f"LLMReranker {'ACCEPT' if relevant else 'REJECT'} "
                f"{paper.arxiv_id}: confidence={confidence:.2f}, reason='{reason}'"
            )

            return RerankerResult(
                paper=paper,
                relevant=relevant,
                confidence=confidence,
                reason=reason,
                llm_succeeded=True,
            )

        except (OllamaException, ValueError, KeyError) as e:
            logger.warning(
                f"LLMReranker failed for {paper.arxiv_id}: {e}. "
                f"{'Falling back to reject.' if self.fallback_on_error else 'Raising.'}"
            )
            if not self.fallback_on_error:
                raise

            # Conservative fallback: reject with low confidence
            return RerankerResult(
                paper=paper,
                relevant=False,
                confidence=0.0,
                reason=f"LLM call failed: {str(e)[:100]}",
                llm_succeeded=False,
            )

    def rerank_batch(self, papers: List[ArxivPaper]) -> RerankerBatchResult:
        """
        Rerank a batch of ambiguous papers.

        Papers beyond max_papers are rejected conservatively to bound cost.
        LLM calls are sequential — the ambiguous band is expected to be small
        (typically 5-15% of the daily batch) so parallelism adds complexity
        without meaningful latency benefit at this scale.

        :param papers: Papers from the ambiguous embedding zone
        :returns: RerankerBatchResult with accept/reject decisions
        """
        if not papers:
            return RerankerBatchResult(results=[])

        # Apply cost guard
        if len(papers) > self.max_papers:
            logger.warning(
                f"LLMReranker: {len(papers)} papers exceeds max_papers={self.max_papers}. "
                f"Excess {len(papers) - self.max_papers} papers will be rejected."
            )
            capped = papers[: self.max_papers]
            overflow = papers[self.max_papers :]
        else:
            capped = papers
            overflow = []

        results: List[RerankerResult] = []

        for i, paper in enumerate(capped, 1):
            logger.debug(f"LLMReranker: processing {i}/{len(capped)} — {paper.arxiv_id}")
            result = self._call_llm(paper)
            results.append(result)

        # Overflow papers → conservative reject
        for paper in overflow:
            results.append(
                RerankerResult(
                    paper=paper,
                    relevant=False,
                    confidence=0.0,
                    reason="Rejected: exceeded max_papers cost cap",
                    llm_succeeded=False,
                )
            )

        batch_result = RerankerBatchResult(results=results)
        failed_count = len(batch_result.failed)

        logger.info(
            f"LLMReranker: {len(batch_result.accepted)} accepted, "
            f"{len(batch_result.rejected)} rejected "
            f"({failed_count} LLM failures)"
        )

        return batch_result


def make_llm_reranker(
    profile: ScopeProfile,
    llm_client: NvidiaClient,
    max_papers: int = 50,
) -> LLMReranker:
    """Factory function matching the pattern used across the codebase.

    :param profile: Active ScopeProfile ORM instance
    :param llm_client: Initialised NvidiaClient
    :param max_papers: Hard cap from settings.filtering.llm_rerank_max_papers
    :returns: Configured LLMReranker instance
    """
    return LLMReranker(
        profile=profile,
        llm_client=llm_client,
        max_papers=max_papers,
    )
