"""Unified OpenSearch client supporting both simple BM25 and hybrid search."""

import logging
from typing import Any, Dict, List, Optional

from opensearchpy import OpenSearch
from src.config import Settings

from .index_config_hybrid import ARXIV_PAPERS_CHUNKS_MAPPING, HYBRID_RRF_PIPELINE
from .query_builder import QueryBuilder

logger = logging.getLogger(__name__)


class OpenSearchClient:
    """OpenSearch client supporting BM25 and hybrid search with native RRF."""

    def __init__(self, host: str, settings: Settings):
        self.host = host
        self.settings = settings
        self.index_name = f"{settings.opensearch.index_name}-{settings.opensearch.chunk_index_suffix}"

        self.client = OpenSearch(
            hosts=[host],
            use_ssl=False,
            verify_certs=False,
            ssl_show_warn=False,
        )

        logger.info(f"OpenSearch client initialized with host: {host}")

    def health_check(self) -> bool:
        try:
            health = self.client.cluster.health()
            return health["status"] in ["green", "yellow"]
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    def get_index_stats(self) -> Dict[str, Any]:
        try:
            if not self.client.indices.exists(index=self.index_name):
                return {"index_name": self.index_name, "exists": False, "document_count": 0}

            stats_response = self.client.indices.stats(index=self.index_name)
            index_stats = stats_response["indices"][self.index_name]["total"]

            return {
                "index_name": self.index_name,
                "exists": True,
                "document_count": index_stats["docs"]["count"],
                "deleted_count": index_stats["docs"]["deleted"],
                "size_in_bytes": index_stats["store"]["size_in_bytes"],
            }

        except Exception as e:
            logger.error(f"Error getting index stats: {e}")
            return {"index_name": self.index_name, "exists": False, "document_count": 0, "error": str(e)}

    def setup_indices(self, force: bool = False) -> Dict[str, bool]:
        results = {}
        results["hybrid_index"] = self._create_hybrid_index(force)
        results["rrf_pipeline"] = self._create_rrf_pipeline(force)
        return results

    def _create_hybrid_index(self, force: bool = False) -> bool:
        try:
            if force and self.client.indices.exists(index=self.index_name):
                self.client.indices.delete(index=self.index_name)
                logger.info(f"Deleted existing hybrid index: {self.index_name}")

            if not self.client.indices.exists(index=self.index_name):
                self.client.indices.create(index=self.index_name, body=ARXIV_PAPERS_CHUNKS_MAPPING)
                logger.info(f"Created hybrid index: {self.index_name}")
                return True

            logger.info(f"Hybrid index already exists: {self.index_name}")
            return False

        except Exception as e:
            logger.error(f"Error creating hybrid index: {e}")
            raise

    def _create_rrf_pipeline(self, force: bool = False) -> bool:
        try:
            pipeline_id = HYBRID_RRF_PIPELINE["id"]

            if force:
                try:
                    self.client.ingest.get_pipeline(id=pipeline_id)
                    self.client.ingest.delete_pipeline(id=pipeline_id)
                    logger.info(f"Deleted existing RRF pipeline: {pipeline_id}")
                except Exception:
                    pass

            try:
                self.client.ingest.get_pipeline(id=pipeline_id)
                logger.info(f"RRF pipeline already exists: {pipeline_id}")
                return False
            except Exception:
                pass

            pipeline_body = {
                "description": HYBRID_RRF_PIPELINE["description"],
                "phase_results_processors": HYBRID_RRF_PIPELINE["phase_results_processors"],
            }

            self.client.transport.perform_request("PUT", f"/_search/pipeline/{pipeline_id}", body=pipeline_body)
            logger.info(f"Created RRF search pipeline: {pipeline_id}")
            return True

        except Exception as e:
            logger.error(f"Error creating RRF pipeline: {e}")
            raise

    def search_papers(
        self, query: str, size: int = 10, from_: int = 0, categories: Optional[List[str]] = None, latest: bool = True
    ) -> Dict[str, Any]:
        """BM25 search for papers."""
        return self._search_bm25_only(query=query, size=size, from_=from_, categories=categories, latest=latest)

    def search_chunks_vector(
        self, query_embedding: List[float], size: int = 10, categories: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Pure vector search on chunks."""
        try:
            filter_clause = []
            if categories:
                filter_clause.append({"terms": {"categories": categories}})

            search_body = {
                "size": size,
                "query": {"knn": {"embedding": {"vector": query_embedding, "k": size}}},
                "_source": {"excludes": ["embedding"]},
            }

            if filter_clause:
                search_body["query"] = {"bool": {"must": [search_body["query"]], "filter": filter_clause}}

            response = self.client.search(index=self.index_name, body=search_body)

            results = {"total": response["hits"]["total"]["value"], "hits": []}
            for hit in response["hits"]["hits"]:
                chunk = hit["_source"]
                chunk["score"] = hit["_score"]
                chunk["chunk_id"] = hit["_id"]
                results["hits"].append(chunk)

            return results

        except Exception as e:
            logger.error(f"Vector search error: {e}")
            return {"total": 0, "hits": []}

    def search_unified(
        self,
        query: str,
        query_embedding: Optional[List[float]] = None,
        size: int = 10,
        from_: int = 0,
        categories: Optional[List[str]] = None,
        latest: bool = False,
        use_hybrid: bool = True,
        min_score: float = 0.0,
        paper_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Unified search method supporting BM25, vector, and hybrid modes.

        :param paper_ids: When provided, restricts retrieval to only these paper UUIDs.
                          Used for project-scoped RAG. When None, searches the full index.
        """
        try:
            if not query_embedding or not use_hybrid:
                return self._search_bm25_only(
                    query=query, size=size, from_=from_, categories=categories, latest=latest, paper_ids=paper_ids
                )

            return self._search_hybrid_native(
                query=query,
                query_embedding=query_embedding,
                size=size,
                categories=categories,
                min_score=min_score,
                paper_ids=paper_ids,
            )

        except Exception as e:
            logger.error(f"Unified search error: {e}")
            return {"total": 0, "hits": []}

    def _search_bm25_only(
        self,
        query: str,
        size: int,
        from_: int,
        categories: Optional[List[str]],
        latest: bool,
        paper_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Pure BM25 search implementation."""
        builder = QueryBuilder(
            query=query,
            size=size,
            from_=from_,
            categories=categories,
            latest_papers=latest,
            search_chunks=True,
            paper_ids=paper_ids,
        )
        search_body = builder.build()

        response = self.client.search(index=self.index_name, body=search_body)

        results = {"total": response["hits"]["total"]["value"], "hits": []}
        for hit in response["hits"]["hits"]:
            chunk = hit["_source"]
            chunk["score"] = hit["_score"]
            chunk["chunk_id"] = hit["_id"]
            if "highlight" in hit:
                chunk["highlights"] = hit["highlight"]
            results["hits"].append(chunk)

        logger.info(f"BM25 search for '{query[:50]}' returned {results['total']} results (paper_ids filter: {bool(paper_ids)})")
        return results

    def _search_hybrid_native(
        self,
        query: str,
        query_embedding: List[float],
        size: int,
        categories: Optional[List[str]],
        min_score: float,
        paper_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Native OpenSearch hybrid search with RRF pipeline."""
        builder = QueryBuilder(
            query=query,
            size=size * 2,
            from_=0,
            categories=categories,
            latest_papers=False,
            search_chunks=True,
            paper_ids=paper_ids,
        )
        bm25_search_body = builder.build()
        bm25_query = bm25_search_body["query"]

        knn_query: Dict[str, Any] = {"knn": {"embedding": {"vector": query_embedding, "k": size * 2}}}
        if paper_ids:
            knn_query = {
                "bool": {
                    "must": [knn_query],
                    "filter": [{"terms": {"paper_id": paper_ids}}],
                }
            }

        hybrid_query = {"hybrid": {"queries": [bm25_query, knn_query]}}

        search_body = {
            "size": size,
            "query": hybrid_query,
            "_source": bm25_search_body["_source"],
            "highlight": bm25_search_body["highlight"],
        }

        response = self.client.search(
            index=self.index_name, body=search_body, params={"search_pipeline": HYBRID_RRF_PIPELINE["id"]}
        )

        results = {"total": response["hits"]["total"]["value"], "hits": []}
        for hit in response["hits"]["hits"]:
            if hit["_score"] < min_score:
                continue
            chunk = hit["_source"]
            chunk["score"] = hit["_score"]
            chunk["chunk_id"] = hit["_id"]
            if "highlight" in hit:
                chunk["highlights"] = hit["highlight"]
            results["hits"].append(chunk)

        results["total"] = len(results["hits"])
        logger.info(f"Hybrid search for '{query[:50]}' returned {results['total']} results (paper_ids filter: {bool(paper_ids)})")
        return results

    def search_chunks_hybrid(
        self,
        query: str,
        query_embedding: List[float],
        size: int = 10,
        categories: Optional[List[str]] = None,
        min_score: float = 0.0,
    ) -> Dict[str, Any]:
        """Hybrid search combining BM25 and vector similarity using native RRF."""
        return self._search_hybrid_native(
            query=query, query_embedding=query_embedding, size=size, categories=categories, min_score=min_score
        )

    def index_chunk(self, chunk_data: Dict[str, Any], embedding: List[float]) -> bool:
        try:
            chunk_data["embedding"] = embedding
            response = self.client.index(index=self.index_name, body=chunk_data, refresh=True)
            return response["result"] in ["created", "updated"]
        except Exception as e:
            logger.error(f"Error indexing chunk: {e}")
            return False

    def bulk_index_chunks(self, chunks: List[Dict[str, Any]]) -> Dict[str, int]:
        from opensearchpy import helpers

        try:
            actions = []
            for chunk in chunks:
                chunk_data = chunk["chunk_data"].copy()
                chunk_data["embedding"] = chunk["embedding"]
                actions.append({"_index": self.index_name, "_source": chunk_data})

            success, failed = helpers.bulk(self.client, actions, refresh=True)
            logger.info(f"Bulk indexed {success} chunks, {len(failed)} failed")
            return {"success": success, "failed": len(failed)}

        except Exception as e:
            logger.error(f"Bulk chunk indexing error: {e}")
            raise

    def delete_paper_chunks(self, arxiv_id: str) -> bool:
        try:
            response = self.client.delete_by_query(
                index=self.index_name, body={"query": {"term": {"arxiv_id": arxiv_id}}}, refresh=True
            )
            deleted = response.get("deleted", 0)
            logger.info(f"Deleted {deleted} chunks for paper {arxiv_id}")
            return deleted > 0
        except Exception as e:
            logger.error(f"Error deleting chunks: {e}")
            return False

    def get_chunks_by_paper(self, arxiv_id: str) -> List[Dict[str, Any]]:
        """Retrieve all chunks for an arXiv-ingested paper, ordered by chunk_index.

        For user-uploaded papers (no arXiv ID), use :meth:`get_chunks_by_paper_uuid` instead.

        Args:
            arxiv_id: The arXiv paper identifier (e.g. ``"2401.00001"``).

        Returns:
            Ordered list of chunk dicts with ``chunk_id`` injected.
        """
        try:
            search_body = {
                "query": {"term": {"arxiv_id": arxiv_id}},
                "size": 1000,
                "sort": [{"chunk_index": "asc"}],
                "_source": {"excludes": ["embedding"]},
            }

            response = self.client.search(index=self.index_name, body=search_body)

            chunks = []
            for hit in response["hits"]["hits"]:
                chunk = hit["_source"]
                chunk["chunk_id"] = hit["_id"]
                chunks.append(chunk)

            return chunks

        except Exception as e:
            logger.error(f"Error getting chunks by arxiv_id '{arxiv_id}': {e}")
            return []

    def get_chunks_by_paper_uuid(self, paper_uuid: str) -> List[Dict[str, Any]]:
        """Retrieve all chunks for a user-uploaded paper identified by its UUID.

        User-uploaded papers are indexed without an ``arxiv_id``; their chunks
        carry the Postgres ``paper_id`` (UUID) in the ``paper_id`` field instead.

        Args:
            paper_uuid: String representation of the paper's UUID primary key.

        Returns:
            Ordered list of chunk dicts with ``chunk_id`` injected.
        """
        try:
            search_body = {
                "query": {"term": {"paper_id": paper_uuid}},
                "size": 1000,
                "sort": [{"chunk_index": "asc"}],
                "_source": {"excludes": ["embedding"]},
            }

            response = self.client.search(index=self.index_name, body=search_body)

            chunks = []
            for hit in response["hits"]["hits"]:
                chunk = hit["_source"]
                chunk["chunk_id"] = hit["_id"]
                chunks.append(chunk)

            logger.info(f"UUID chunk lookup for '{paper_uuid}' returned {len(chunks)} chunks")
            return chunks

        except Exception as e:
            logger.error(f"Error getting chunks by paper_uuid '{paper_uuid}': {e}")
            return []

    def get_chunks_for_paper(self, paper_uuid: str, arxiv_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Unified chunk retrieval that works for both arXiv and user-uploaded papers.

        Routing logic:
        - If *arxiv_id* is provided → query the ``arxiv_id`` field (arXiv-ingested paper).
        - Otherwise → query the ``paper_id`` field using *paper_uuid* (user upload).

        This is the preferred method to call from routers and services so that
        the routing decision lives in one place.

        Args:
            paper_uuid: String UUID of the paper (always available from the DB record).
            arxiv_id:   arXiv ID of the paper, or ``None`` for user uploads.

        Returns:
            Ordered list of chunk dicts with ``chunk_id`` injected.
        """
        if arxiv_id:
            return self.get_chunks_by_paper(arxiv_id)
        return self.get_chunks_by_paper_uuid(paper_uuid)
