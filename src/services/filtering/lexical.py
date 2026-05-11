"""
Layer 1 — Lexical pre-filter.

Operates purely on title + abstract text with no external dependencies.
Runs in microseconds per paper and eliminates obvious mismatches before
any embedding or LLM inference is invoked.

Two checks, applied in order:
  1. Excluded terms  — any match → hard reject immediately
  2. Required terms  — checked per match_mode ("any" or "all")
                       failure → hard reject

Papers passing both checks are forwarded to Layer 2 (embedding similarity).
"""

import logging
import re
from dataclasses import dataclass, field
from typing import List, Tuple

from src.models.scope_profile import ScopeProfile
from src.schemas.arxiv.paper import ArxivPaper

logger = logging.getLogger(__name__)


@dataclass
class LexicalFilterResult:
    """Result for a single paper from the lexical filter."""

    paper: ArxivPaper
    passed: bool
    # Which excluded term triggered a rejection (None if passed or rejected by required_terms)
    matched_excluded_term: str | None = None
    # Which required terms were matched (empty if rejected or no required terms)
    matched_required_terms: List[str] = field(default_factory=list)
    # Human-readable reason for rejection (None if passed)
    rejection_reason: str | None = None


@dataclass
class LexicalFilterBatchResult:
    """Aggregated result for a full batch of papers."""

    passed: List[ArxivPaper]
    results: List[LexicalFilterResult]

    @property
    def rejected(self) -> List[ArxivPaper]:
        return [r.paper for r in self.results if not r.passed]

    @property
    def passed_count(self) -> int:
        return len(self.passed)

    @property
    def rejected_count(self) -> int:
        return len(self.results) - len(self.passed)

    @property
    def excluded_term_rejections(self) -> int:
        return sum(1 for r in self.results if r.matched_excluded_term is not None)

    @property
    def required_term_rejections(self) -> int:
        return sum(1 for r in self.results if not r.passed and r.matched_excluded_term is None)


class LexicalFilter:
    """
    Applies lexical pre-filtering against a scope profile's term lists.

    Instantiate once per pipeline run with the active scope profile.
    Pre-compiles regex patterns at init time so per-paper matching is fast.
    """

    def __init__(self, profile: ScopeProfile):
        """
        :param profile: Active ScopeProfile ORM instance. Term lists and
                        match_mode are read from the profile at init time.
        """
        self.profile = profile
        self.match_mode: str = profile.lexical_match_mode or "any"

        required_terms: List[str] = profile.required_terms or []
        excluded_terms: List[str] = profile.excluded_terms or []

        # Pre-compile patterns — case-insensitive word-boundary match
        # so "LLM" doesn't match "LLMS" and "RAG" doesn't match "fragment"
        self._required_patterns: List[Tuple[str, re.Pattern]] = [
            (term, re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)) for term in required_terms if term.strip()
        ]
        self._excluded_patterns: List[Tuple[str, re.Pattern]] = [
            (term, re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)) for term in excluded_terms if term.strip()
        ]

        logger.debug(
            f"LexicalFilter initialised: {len(self._required_patterns)} required terms, "
            f"{len(self._excluded_patterns)} excluded terms, mode='{self.match_mode}'"
        )

    def _build_search_text(self, paper: ArxivPaper) -> str:
        """Concatenate title and abstract as the search surface.

        Title is included twice to give it slightly more weight —
        a term in the title is a stronger signal than one buried in
        the abstract.
        """
        return f"{paper.title} {paper.title} {paper.abstract}"

    def filter_one(self, paper: ArxivPaper) -> LexicalFilterResult:
        """
        Evaluate a single paper against the scope profile term lists.

        :param paper: ArxivPaper to evaluate
        :returns: LexicalFilterResult with pass/fail and match details
        """
        text = self._build_search_text(paper)

        # --- Check 1: Excluded terms (hard reject on any match) ---
        for term, pattern in self._excluded_patterns:
            if pattern.search(text):
                return LexicalFilterResult(
                    paper=paper,
                    passed=False,
                    matched_excluded_term=term,
                    rejection_reason=f"Matched excluded term: '{term}'",
                )

        # --- Check 2: Required terms ---
        # Short-circuit if no required terms are configured — pass through
        if not self._required_patterns:
            return LexicalFilterResult(paper=paper, passed=True)

        matched_required = [term for term, pattern in self._required_patterns if pattern.search(text)]

        if self.match_mode == "all":
            required_count = len(self._required_patterns)
            if len(matched_required) < required_count:
                missing = [term for term, _ in self._required_patterns if term not in matched_required]
                return LexicalFilterResult(
                    paper=paper,
                    passed=False,
                    matched_required_terms=matched_required,
                    rejection_reason=(f"Required terms not found (mode='all'): {', '.join(repr(t) for t in missing)}"),
                )
        else:
            # match_mode == "any"
            if not matched_required:
                return LexicalFilterResult(
                    paper=paper,
                    passed=False,
                    matched_required_terms=[],
                    rejection_reason=(
                        f"No required terms matched (mode='any'): {', '.join(repr(t) for t, _ in self._required_patterns)}"
                    ),
                )

        return LexicalFilterResult(
            paper=paper,
            passed=True,
            matched_required_terms=matched_required,
        )

    def filter_batch(self, papers: List[ArxivPaper]) -> LexicalFilterBatchResult:
        """
        Evaluate a batch of papers.

        Logs a summary at INFO level — individual rejections at DEBUG.

        :param papers: List of ArxivPaper candidates
        :returns: LexicalFilterBatchResult with passed papers and full result list
        """
        if not papers:
            return LexicalFilterBatchResult(passed=[], results=[])

        # Short-circuit: if no term lists are configured, pass everything
        if not self._required_patterns and not self._excluded_patterns:
            logger.info("LexicalFilter: no term lists configured — all papers pass through")
            results = [LexicalFilterResult(paper=p, passed=True) for p in papers]
            return LexicalFilterBatchResult(passed=papers, results=results)

        results: List[LexicalFilterResult] = []
        passed: List[ArxivPaper] = []

        for paper in papers:
            result = self.filter_one(paper)
            results.append(result)
            if result.passed:
                passed.append(paper)
            else:
                logger.debug(f"LexicalFilter REJECT {paper.arxiv_id}: {result.rejection_reason}")

        batch_result = LexicalFilterBatchResult(passed=passed, results=results)

        logger.info(
            f"LexicalFilter: {batch_result.passed_count}/{len(papers)} passed "
            f"({batch_result.excluded_term_rejections} excluded-term rejections, "
            f"{batch_result.required_term_rejections} required-term rejections)"
        )

        return batch_result


def make_lexical_filter(profile: ScopeProfile) -> LexicalFilter:
    """Factory function — matches the factory pattern used elsewhere in the codebase.

    :param profile: Active ScopeProfile ORM instance
    :returns: Configured LexicalFilter instance
    """
    return LexicalFilter(profile=profile)
