"""
Composite scorer — combines all filter signals into a final decision.

Aggregates the outputs of all filter layers:
  - Layer 1 (lexical): pass/fail flag — papers that failed never reach here
  - Layer 2 (embedding): cosine similarity score
  - Layer 3 (LLM): relevant bool + confidence (only for ambiguous papers)
  - Enrichment: venue boost + citation score (when Semantic Scholar enabled)

Produces:
  - A composite score in [0, 1]
  - A final decision: "ingested" or "rejected"
  - A FilterDecisionCreate ready to be written to the DB

Also handles graceful degradation:
  - Citation signal absent → weight redistributed to relevance
  - Venue data absent → venue_boost = 0.0 (no penalty)
  - LLM not invoked → embedding score alone determines outcome vs threshold
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID

from src.models.scope_profile import ScopeProfile
from src.schemas.arxiv.paper import ArxivPaper
from src.schemas.scope.profile import FilterDecisionCreate
from src.services.filtering.embedding import EmbeddingFilterBatchResult
from src.services.filtering.lexical import LexicalFilterBatchResult
from src.services.filtering.reranker import RerankerBatchResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-paper signal container
# ---------------------------------------------------------------------------


@dataclass
class PaperSignals:
    """
    All signal values collected for one paper across all filter layers.
    Populated incrementally as each layer runs.
    """

    paper: ArxivPaper
    paper_id: Optional[UUID] = None  # Set after DB lookup/insert

    # Layer 1
    lexical_passed: bool = False

    # Layer 2
    embedding_score: Optional[float] = None

    # Layer 3 (None if not invoked)
    llm_relevant: Optional[bool] = None
    llm_confidence: Optional[float] = None
    llm_reason: Optional[str] = None

    # Semantic Scholar enrichment (None until enabled)
    venue: Optional[str] = None
    venue_type: Optional[str] = None
    venue_boost_applied: float = 0.0
    citation_count: Optional[int] = None
    influential_citation_count: Optional[int] = None
    citation_score: Optional[float] = None  # Normalised 0-1 percentile


# ---------------------------------------------------------------------------
# Composite scorer
# ---------------------------------------------------------------------------


class CompositeScorer:
    """
    Combines all filter signals into a single composite score and decision.

    Instantiate once per pipeline run with the active scope profile.
    The scoring weights and ingest threshold are read from the profile's
    configuration, falling back to FilteringSettings defaults.
    """

    def __init__(self, profile: ScopeProfile, ingest_threshold: float = 0.72):
        """
        :param profile: Active ScopeProfile ORM instance
        :param ingest_threshold: From settings.filtering.composite_ingest_threshold
        """
        self.profile = profile
        self.ingest_threshold = ingest_threshold
        self.version_hash = profile.version_hash

        weights = profile.scoring_weights or {}
        self.weight_relevance: float = float(weights.get("relevance", 0.70))
        self.weight_venue: float = float(weights.get("venue", 0.15))
        self.weight_citation: float = float(weights.get("citation", 0.15))

        journal_cfg = profile.journal_filter or {}
        self.journal_enabled: bool = bool(journal_cfg.get("enabled", False))
        self.journal_mode: str = journal_cfg.get("mode", "boost")
        self.journal_venues: List[str] = [v.lower() for v in journal_cfg.get("venues", [])]
        self.journal_boost_factor: float = float(journal_cfg.get("boost_factor", 0.10))
        self.journal_fallback_on_unknown: bool = bool(journal_cfg.get("fallback_on_unknown", True))

        logger.debug(
            f"CompositeScorer initialised: threshold={ingest_threshold}, "
            f"weights=(relevance={self.weight_relevance}, "
            f"venue={self.weight_venue}, citation={self.weight_citation})"
        )

    # -------------------------------------------------------------------------
    # Venue boost
    # -------------------------------------------------------------------------

    def _compute_venue_boost(self, signals: PaperSignals) -> float:
        """
        Compute the venue signal contribution for a paper.

        Returns 0.0 when:
        - Journal filter is disabled
        - No venue data is available AND fallback_on_unknown=True
        - mode="exclude" and venue matches (handled at decision time)

        :param signals: PaperSignals for the paper
        :returns: Boost value (0.0 to boost_factor)
        """
        if not self.journal_enabled or not self.journal_venues:
            return 0.0

        venue = signals.venue
        if not venue:
            # Unknown venue — no boost, but also no penalty (fallback_on_unknown)
            return 0.0

        venue_lower = venue.lower()
        matched = any(v in venue_lower for v in self.journal_venues)

        if self.journal_mode == "boost" and matched:
            return self.journal_boost_factor

        return 0.0

    def _venue_hard_reject(self, signals: PaperSignals) -> bool:
        """
        Returns True if venue config requires a hard rejection.

        Only applies when:
        - mode="require" AND venue unknown AND fallback_on_unknown=False
        - mode="exclude" AND venue matches
        """
        if not self.journal_enabled or not self.journal_venues:
            return False

        venue = signals.venue
        if not venue:
            if self.journal_mode == "require" and not self.journal_fallback_on_unknown:
                return True  # Unknown venue, require mode, no fallback → reject
            return False

        venue_lower = venue.lower()
        matched = any(v in venue_lower for v in self.journal_venues)

        if self.journal_mode == "require" and not matched:
            return True
        if self.journal_mode == "exclude" and matched:
            return True

        return False

    # -------------------------------------------------------------------------
    # Composite score computation
    # -------------------------------------------------------------------------

    def _compute_composite_score(self, signals: PaperSignals) -> float:
        """
        Compute the weighted composite score.

        When citation data is unavailable the citation weight is redistributed
        to relevance so the score remains in [0, 1] and the threshold is
        not inadvertently relaxed.

        Embedding score is used as the relevance signal in all cases.
        The LLM confidence modulates it slightly when the reranker ran.

        :param signals: PaperSignals with all available signal values
        :returns: Composite score in [0, 1]
        """
        embedding_score = signals.embedding_score or 0.0

        # If LLM ran, blend embedding score with LLM confidence
        # LLM confidence confirms or tempers the embedding score
        if signals.llm_relevant is not None and signals.llm_confidence is not None:
            # If LLM agrees with embedding direction, boost; if disagrees, temper
            if signals.llm_relevant:
                relevance_signal = (embedding_score + signals.llm_confidence) / 2
            else:
                # LLM rejected — weight its confidence more heavily
                relevance_signal = embedding_score * (1 - signals.llm_confidence * 0.5)
        else:
            relevance_signal = embedding_score

        # Venue boost
        venue_boost = signals.venue_boost_applied

        # Citation score
        citation_available = signals.citation_score is not None
        citation_signal = signals.citation_score or 0.0

        if citation_available:
            score = (
                self.weight_relevance * relevance_signal
                + self.weight_venue * venue_boost
                + self.weight_citation * citation_signal
            )
        else:
            # Redistribute citation weight to relevance
            effective_relevance_weight = self.weight_relevance + self.weight_citation
            score = effective_relevance_weight * relevance_signal + self.weight_venue * venue_boost

        return round(min(max(score, 0.0), 1.0), 6)

    # -------------------------------------------------------------------------
    # Decision
    # -------------------------------------------------------------------------

    def decide(self, signals: PaperSignals) -> tuple[float, str]:
        """
        Compute composite score and make the final ingest/reject decision.

        :param signals: PaperSignals with all available signal values
        :returns: Tuple of (composite_score, decision)
                  where decision is "ingested" or "rejected"
        """
        # Hard reject via venue config overrides everything
        if self._venue_hard_reject(signals):
            return 0.0, "rejected"

        # Hard reject if LLM explicitly rejected with high confidence
        if signals.llm_relevant is False and signals.llm_confidence is not None and signals.llm_confidence >= 0.85:
            return 0.0, "rejected"

        composite = self._compute_composite_score(signals)
        signals.venue_boost_applied = self._compute_venue_boost(signals)

        decision = "ingested" if composite >= self.ingest_threshold else "rejected"
        return composite, decision

    # -------------------------------------------------------------------------
    # Filter decision record builder
    # -------------------------------------------------------------------------

    def build_filter_decision(
        self,
        signals: PaperSignals,
        scope_profile_id: UUID,
    ) -> FilterDecisionCreate:
        """
        Convert a PaperSignals object into a FilterDecisionCreate ready for the DB.

        :param signals: Fully populated PaperSignals
        :param scope_profile_id: UUID of the active scope profile
        :returns: FilterDecisionCreate schema
        """
        composite_score, decision = self.decide(signals)

        return FilterDecisionCreate(
            paper_id=signals.paper_id,
            scope_profile_id=scope_profile_id,
            scope_version_hash=self.version_hash,
            lexical_passed=signals.lexical_passed,
            embedding_score=signals.embedding_score,
            llm_relevant=signals.llm_relevant,
            llm_confidence=signals.llm_confidence,
            llm_reason=signals.llm_reason,
            venue=signals.venue,
            venue_type=signals.venue_type,
            venue_boost_applied=signals.venue_boost_applied,
            citation_count=signals.citation_count,
            influential_citation_count=signals.influential_citation_count,
            citation_score=signals.citation_score,
            composite_score=composite_score,
            decision=decision,
            decided_at=datetime.now(timezone.utc),
        )

    # -------------------------------------------------------------------------
    # Batch assembly — combines all layer outputs into signals
    # -------------------------------------------------------------------------

    def assemble_signals(
        self,
        lexical_results: LexicalFilterBatchResult,
        embedding_results: EmbeddingFilterBatchResult,
        reranker_results: RerankerBatchResult,
        paper_id_map: Dict[str, UUID],
    ) -> List[PaperSignals]:
        """
        Assemble PaperSignals for every paper that went through the pipeline.

        Merges outputs from all three layers by arxiv_id. Lexical rejects
        are included (with no embedding/LLM data) so every paper has a
        decision record — this makes the audit log complete.

        :param lexical_results: Output of LexicalFilter.filter_batch()
        :param embedding_results: Output of EmbeddingFilter.filter_batch()
        :param reranker_results: Output of LLMReranker.rerank_batch()
        :param paper_id_map: Dict mapping arxiv_id → DB UUID (from store step)
        :returns: List of fully populated PaperSignals
        """
        # Index results by arxiv_id for O(1) lookup
        embedding_by_id = {r.paper.arxiv_id: r for r in embedding_results.results}
        reranker_by_id = {r.paper.arxiv_id: r for r in reranker_results.results}

        all_signals: List[PaperSignals] = []

        for lexical_result in lexical_results.results:
            paper = lexical_result.paper
            arxiv_id = paper.arxiv_id

            signals = PaperSignals(
                paper=paper,
                paper_id=paper_id_map.get(arxiv_id),
                lexical_passed=lexical_result.passed,
            )

            if arxiv_id in embedding_by_id:
                emb = embedding_by_id[arxiv_id]
                signals.embedding_score = emb.embedding_score

            if arxiv_id in reranker_by_id:
                rer = reranker_by_id[arxiv_id]
                signals.llm_relevant = rer.relevant
                signals.llm_confidence = rer.confidence
                signals.llm_reason = rer.reason

            # Venue boost computed at decide() time — set here for completeness
            signals.venue_boost_applied = self._compute_venue_boost(signals)

            all_signals.append(signals)

        return all_signals


def make_composite_scorer(
    profile: ScopeProfile,
    ingest_threshold: float = 0.72,
) -> CompositeScorer:
    """Factory function matching the pattern used across the codebase.

    :param profile: Active ScopeProfile ORM instance
    :param ingest_threshold: Composite score gate (from settings.filtering)
    :returns: Configured CompositeScorer instance
    """
    return CompositeScorer(profile=profile, ingest_threshold=ingest_threshold)
