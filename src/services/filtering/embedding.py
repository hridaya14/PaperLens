"""
Layer 2 — Embedding similarity filter.

Embeds each paper's title + abstract and computes cosine similarity
against the active scope profile's precomputed centroid vector.

Three-zone decision:
  score >= high_threshold  →  INGEST  (fast-track, skip LLM reranker)
  score <= low_threshold   →  REJECT  (fast-track, skip LLM reranker)
  low < score < high       →  AMBIGUOUS (forwarded to Layer 3 LLM reranker)

Also handles scope vector computation — called by the pipeline's
check_scope_vector task when the profile description or seed papers change.
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from src.models.scope_profile import ScopeProfile
from src.schemas.arxiv.paper import ArxivPaper
from src.services.embeddings.nvidia_client import NIMEmbeddingsClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class EmbeddingFilterResult:
    """Result for a single paper from the embedding filter."""

    paper: ArxivPaper
    embedding_score: float
    # "ingest" | "reject" | "ambiguous"
    zone: str

    @property
    def passed(self) -> bool:
        return self.zone in ("ingest", "ambiguous")

    @property
    def fast_tracked(self) -> bool:
        """True if the score was decisive enough to skip the LLM reranker."""
        return self.zone != "ambiguous"


@dataclass
class EmbeddingFilterBatchResult:
    """Aggregated result for a full batch of papers."""

    results: List[EmbeddingFilterResult]

    @property
    def fast_track_ingest(self) -> List[ArxivPaper]:
        return [r.paper for r in self.results if r.zone == "ingest"]

    @property
    def fast_track_reject(self) -> List[ArxivPaper]:
        return [r.paper for r in self.results if r.zone == "reject"]

    @property
    def ambiguous(self) -> List[ArxivPaper]:
        return [r.paper for r in self.results if r.zone == "ambiguous"]

    @property
    def scores_by_arxiv_id(self) -> Dict[str, float]:
        return {r.paper.arxiv_id: r.embedding_score for r in self.results}


# ---------------------------------------------------------------------------
# Cosine similarity (pure Python — no scipy dependency needed for one vector)
# ---------------------------------------------------------------------------


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """
    Compute cosine similarity between two vectors.

    :param a: First vector
    :param b: Second vector
    :returns: Similarity score in [-1, 1]; NIM models typically return [0, 1]
    :raises ValueError: If vectors have different dimensions
    """
    if len(a) != len(b):
        raise ValueError(
            f"Vector dimension mismatch: {len(a)} vs {len(b)}. "
            "Ensure papers are embedded with the same model as the scope vector."
        )
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# Scope vector computation
# ---------------------------------------------------------------------------


async def compute_scope_vector(
    profile: ScopeProfile,
    embeddings_client: NIMEmbeddingsClient,
    seed_paper_abstracts: Optional[List[str]] = None,
) -> List[float]:
    """
    Compute the embedding centroid for a scope profile.

    Embeds the profile description and any seed paper abstracts as passages,
    then averages all vectors into a single centroid. This centroid is the
    scope vector stored on the profile and used for per-paper similarity scoring.

    :param profile: ScopeProfile ORM instance
    :param embeddings_client: Initialised NIMEmbeddingsClient
    :param seed_paper_abstracts: Abstracts of seed papers fetched from DB.
                                 If None, only the description is embedded.
    :returns: Centroid vector as a list of floats
    """
    texts_to_embed = [profile.description]

    if seed_paper_abstracts:
        texts_to_embed.extend(seed_paper_abstracts)

    logger.info(
        f"Computing scope vector for profile '{profile.name}': "
        f"embedding {len(texts_to_embed)} texts "
        f"(1 description + {len(seed_paper_abstracts or [])} seed abstracts)"
    )

    # Embed as passages — consistent with how paper abstracts are embedded
    vectors = await embeddings_client.embed_passages(texts_to_embed)

    if not vectors:
        raise ValueError("Embedding service returned no vectors for scope profile")

    # Average all vectors into a centroid
    dims = len(vectors[0])
    centroid = [0.0] * dims
    for vec in vectors:
        for i, val in enumerate(vec):
            centroid[i] += val
    centroid = [v / len(vectors) for v in centroid]

    logger.info(f"Scope vector computed: {dims} dims, averaged from {len(vectors)} embeddings")
    return centroid


# ---------------------------------------------------------------------------
# Embedding filter
# ---------------------------------------------------------------------------


class EmbeddingFilter:
    """
    Evaluates papers against the scope profile's embedding centroid.

    Instantiate once per pipeline run. The scope vector is read from the
    profile at init time — it must already be computed and stored on the
    profile before this filter is used. Call compute_scope_vector() and
    persist it via ScopeProfileRepository.update_scope_vector() first.
    """

    def __init__(
        self,
        profile: ScopeProfile,
        embeddings_client: NIMEmbeddingsClient,
        batch_size: int = 32,
    ):
        """
        :param profile: Active ScopeProfile with a non-null scope_vector
        :param embeddings_client: Initialised NIMEmbeddingsClient
        :param batch_size: Papers to embed per API call
        :raises ValueError: If the profile has no scope vector
        """
        if not profile.scope_vector:
            raise ValueError(
                f"Scope profile '{profile.name}' has no scope vector. Run compute_scope_vector() and persist it before filtering."
            )

        self.profile = profile
        self.client = embeddings_client
        self.batch_size = batch_size

        self.scope_vector: List[float] = profile.scope_vector
        self.high_threshold: float = (profile.thresholds or {}).get("embedding_high", 0.82)
        self.low_threshold: float = (profile.thresholds or {}).get("embedding_low", 0.60)

        logger.debug(
            f"EmbeddingFilter initialised: "
            f"high={self.high_threshold}, low={self.low_threshold}, "
            f"scope_vector_dims={len(self.scope_vector)}"
        )

    def _build_embedding_text(self, paper: ArxivPaper) -> str:
        """
        Build the text to embed for a paper.

        Title is prepended twice to match the weighting used in
        LexicalFilter — a term in the title is a stronger signal.
        """
        return f"{paper.title}. {paper.title}. {paper.abstract}"

    def _classify_zone(self, score: float) -> str:
        """Assign a paper to a zone based on its similarity score."""
        if score >= self.high_threshold:
            return "ingest"
        if score <= self.low_threshold:
            return "reject"
        return "ambiguous"

    async def filter_batch(self, papers: List[ArxivPaper]) -> EmbeddingFilterBatchResult:
        """
        Embed all papers and assign each to a zone.

        Papers are embedded in batches to bound memory usage and API call size.
        Similarity is computed in Python — one dot product per paper, negligible.

        :param papers: Papers that passed Layer 1 (lexical filter)
        :returns: EmbeddingFilterBatchResult with zone assignments and scores
        """
        if not papers:
            return EmbeddingFilterBatchResult(results=[])

        # Build embedding texts
        texts = [self._build_embedding_text(p) for p in papers]

        logger.info(f"EmbeddingFilter: embedding {len(papers)} papers in batches of {self.batch_size}")

        # Embed all papers as passages
        all_embeddings = await self.client.embed_passages(texts, batch_size=self.batch_size)

        if len(all_embeddings) != len(papers):
            raise ValueError(f"Embedding count mismatch: expected {len(papers)}, got {len(all_embeddings)}")

        # Score and classify
        results: List[EmbeddingFilterResult] = []
        for paper, embedding in zip(papers, all_embeddings):
            score = cosine_similarity(embedding, self.scope_vector)
            zone = self._classify_zone(score)
            results.append(EmbeddingFilterResult(paper=paper, embedding_score=score, zone=zone))

            logger.debug(f"EmbeddingFilter {zone.upper()} {paper.arxiv_id}: score={score:.4f}")

        batch_result = EmbeddingFilterBatchResult(results=results)

        logger.info(
            f"EmbeddingFilter: {len(batch_result.fast_track_ingest)} fast-track ingest, "
            f"{len(batch_result.ambiguous)} ambiguous (→ LLM), "
            f"{len(batch_result.fast_track_reject)} fast-track reject"
        )

        return batch_result


def make_embedding_filter(
    profile: ScopeProfile,
    embeddings_client: NIMEmbeddingsClient,
    batch_size: int = 32,
) -> EmbeddingFilter:
    """Factory function matching the pattern used across the codebase.

    :param profile: Active ScopeProfile with a computed scope_vector
    :param embeddings_client: Initialised NIMEmbeddingsClient
    :param batch_size: Embedding batch size
    :returns: Configured EmbeddingFilter instance
    """
    return EmbeddingFilter(
        profile=profile,
        embeddings_client=embeddings_client,
        batch_size=batch_size,
    )
