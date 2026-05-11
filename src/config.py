import os
from pathlib import Path
from typing import List, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).parent.parent
ENV_FILE_PATH = PROJECT_ROOT / ".env"


class BaseConfigSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)], extra="ignore", frozen=True, env_nested_delimiter="__", case_sensitive=False
    )


class ArxivSettings(BaseConfigSettings):
    """arXiv API client settings."""

    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="ARXIV__",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    base_url: str = "https://export.arxiv.org/api/query"
    namespaces: dict = Field(
        default={
            "atom": "http://www.w3.org/2005/Atom",
            "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
            "arxiv": "http://arxiv.org/schemas/atom",
        }
    )
    pdf_cache_dir: str = "./data/arxiv_pdfs"
    rate_limit_delay: float = 3.0  # seconds between requests
    timeout_seconds: int = 30
    max_results: int = 15
    search_categories: list[str] = ["cs.AI"]  # Default category to search

    download_max_retries: int = 3
    download_retry_delay_base: float = 5.0
    max_concurrent_downloads: int = 5
    max_concurrent_parsing: int = 1

    @field_validator("pdf_cache_dir")
    @classmethod
    def validate_cache_dir(cls, v: str) -> str:
        os.makedirs(v, exist_ok=True)
        return v


class PDFParserSettings(BaseConfigSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="PDF_PARSER__",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    max_pages: int = 30
    max_file_size_mb: int = 20
    do_ocr: bool = False
    do_table_structure: bool = True


class ChunkingSettings(BaseConfigSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="CHUNKING__",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    chunk_size: int = 600  # Target words per chunk
    overlap_size: int = 100  # Words to overlap between chunks
    min_chunk_size: int = 100  # Minimum words for a valid chunk
    section_based: bool = True  # Use section-based chunking when available


class OpenSearchSettings(BaseConfigSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="OPENSEARCH__",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    host: str = "http://localhost:9200"
    index_name: str = "arxiv-papers"
    chunk_index_suffix: str = "chunks"
    max_text_size: int = 1000000

    vector_dimension: int = 1024  # Jina embeddings dimension
    vector_space_type: str = "cosinesimil"  # cosinesimil, l2, innerproduct

    rrf_pipeline_name: str = "hybrid-rrf-pipeline"
    hybrid_search_size_multiplier: int = 2


class FilteringSettings(BaseConfigSettings):
    """Settings for the personalized paper ingestion filtering pipeline."""

    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="FILTERING__",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    # Master switch — set False to bypass all filtering and ingest everything
    enabled: bool = True

    # -------------------------------------------------------------------------
    # Layer 1 — Lexical pre-filter
    # -------------------------------------------------------------------------
    # "any": at least one required_term must appear in title+abstract
    # "all": every required_term must appear
    lexical_match_mode: Literal["any", "all"] = "any"

    # -------------------------------------------------------------------------
    # Layer 2 — Embedding similarity
    # -------------------------------------------------------------------------
    # Papers above high_threshold skip the LLM reranker (fast-track ingest)
    embedding_high_threshold: float = 0.82
    # Papers below low_threshold are rejected without LLM call (fast-track reject)
    embedding_low_threshold: float = 0.60

    # -------------------------------------------------------------------------
    # Layer 3 — LLM reranker (ambiguous zone only)
    # -------------------------------------------------------------------------
    llm_reranking_enabled: bool = True
    # Max papers to send to LLM reranker per pipeline run (cost guard)
    llm_rerank_max_papers: int = 50

    # -------------------------------------------------------------------------
    # Semantic Scholar enrichment
    # -------------------------------------------------------------------------
    # Disabled until API key is available
    semantic_scholar_enabled: bool = False
    semantic_scholar_api_key: str = ""
    semantic_scholar_base_url: str = "https://api.semanticscholar.org/graph/v1"
    # Rate limit: 100 requests per 5 minutes on free tier
    semantic_scholar_requests_per_minute: int = 18

    # -------------------------------------------------------------------------
    # Composite score weights (must sum to 1.0)
    # -------------------------------------------------------------------------
    weight_relevance: float = 0.70
    weight_venue: float = 0.15
    weight_citation: float = 0.15

    # Final gate: papers below this composite score are rejected
    composite_ingest_threshold: float = 0.72

    # -------------------------------------------------------------------------
    # Citation scoring
    # -------------------------------------------------------------------------
    # Papers newer than this many days skip citation scoring (not enough time
    # to accumulate citations — rely on relevance score only)
    citation_min_paper_age_days: int = 14
    # Hard floor — papers with fewer influential citations than this are
    # penalised regardless of other signals (0 = disabled)
    min_influential_citations: int = 0

    @field_validator("weight_relevance", "weight_venue", "weight_citation")
    @classmethod
    def validate_weights(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("Scoring weights must be between 0.0 and 1.0")
        return v


class Settings(BaseConfigSettings):
    """Application settings."""

    app_version: str = "0.1.0"
    debug: bool = True
    environment: str = "development"
    service_name: str = "rag-api"

    # PostgreSQL configuration
    postgres_database_url: str = "postgresql://rag_user:rag_password@localhost:5432/rag_db"
    postgres_echo_sql: bool = False
    postgres_pool_size: int = 20
    postgres_max_overflow: int = 0

    # OpenSearch configuration
    opensearch_host: str = "http://localhost:9200"

    # Redis configuration
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_mindmap_ttl_seconds: int = 604800
    redis_mindmap_cache_version: int = 1

    # Nvidia configuration
    nvidia_api_key: str = ""
    nvidia_base_url: str = ""
    nvidia_timeout: int = 300
    llm_mode: str = "local"
    local_llm_server: str = "http://localhost:1234/v1"
    local_llm_api_key: str = ""

    # Embeddings config (JinaAI)
    jina_api_key: str = ""

    # Langfuse configuration
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = ""

    # arXiv settings
    arxiv: ArxivSettings = Field(default_factory=ArxivSettings)

    # PDF parser settings
    pdf_parser: PDFParserSettings = Field(default_factory=PDFParserSettings)

    # Opensearch Settings
    opensearch: OpenSearchSettings = Field(default_factory=OpenSearchSettings)

    # Chunking settings
    chunking: ChunkingSettings = Field(default_factory=ChunkingSettings)

    # Filtering Settings
    filtering: FilteringSettings = Field(default_factory=FilteringSettings)

    @field_validator("postgres_database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not (v.startswith("postgresql://") or v.startswith("postgresql+psycopg2://")):
            raise ValueError("Database URL must start with 'postgresql://' or 'postgresql+psycopg2://'")
        return v


def get_settings() -> Settings:
    """Get application settings."""
    return Settings()
