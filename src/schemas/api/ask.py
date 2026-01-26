from typing import List, Optional

from pydantic import BaseModel, Field
from src.schemas.nvidia import ResponseMetadata


class AskRequest(BaseModel):
    """Request model for RAG question answering."""

    query: str = Field(..., description="User's question",
                       min_length=1, max_length=1000)
    top_k: int = Field(
        3, description="Number of top chunks to retrieve", ge=1, le=10)
    use_hybrid: bool = Field(
        True, description="Use hybrid search (BM25 + vector)")
    model: str = Field(
        "llama3.2:1b", description="Ollama model to use for generation")
    categories: Optional[List[str]] = Field(
        None, description="Filter by arXiv categories")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "What are transformers in machine learning?",
                "top_k": 3,
                "use_hybrid": True,
                "model": "meta/llama-3.3-70b-instruct",
                "categories": ["cs.AI"],
            }
        }


class AskResponse(BaseModel):
    """Response model for RAG question answering."""

    query: str = Field(..., description="Original user question")
    answer: str = Field(..., description="Generated answer from LLM")
    sources: List[str] = Field(..., description="PDF URLs of source papers")
    citations: List[str] = Field(default_factory=list,
                                 description="Cited arXiv identifiers referenced in the answer")
    chunks_used: int = Field(...,
                             description="Number of chunks used for generation")
    search_mode: str = Field(...,
                             description="Search mode used: bm25 or hybrid")
    metadata: ResponseMetadata = Field(
        default_factory=ResponseMetadata,
        description="Metadata describing response completeness and diagnostics",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "query": "What are transformers in machine learning?",
                "answer": "Transformers are a neural network architecture...",
                "sources": ["https://arxiv.org/pdf/1706.03762.pdf", "https://arxiv.org/pdf/1810.04805.pdf"],
                "citations": ["1706.03762", "1810.04805"],
                "chunks_used": 3,
                "search_mode": "hybrid",
                "metadata": {
                    "confidence": "medium",
                    "is_partial": False,
                    "is_unanswerable": False,
                    "diagnostics": [],
                },
            }
        }
