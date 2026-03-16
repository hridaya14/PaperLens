from __future__ import annotations
from pydantic import BaseModel
from typing import Literal
from datetime import datetime

class MindMapNode(BaseModel):
    id: str
    label: str
    description: str | None = None
    node_type: Literal[
        "root",
        "problem",
        "approach",
        "concept",
        "finding",
        "limitation",
        "contribution",
    ]
    importance: Literal["primary", "secondary", "tertiary"]
    source_section: str | None = None    # populated from chunk section_title
    children: list[MindMapNode] = []

    model_config = {"arbitrary_types_allowed": True}


MindMapNode.model_rebuild()


class MindMap(BaseModel):
    paper_id: str
    arxiv_id: str
    paper_title: str
    root: MindMapNode
    sections_covered: list[str]          # which section_titles were present in chunks
    generated_at: datetime
    model_used: str


class MindMapCacheEntry(BaseModel):
    mindmap: MindMap
    cache_version: int = 1
    hit_count: int = 0
    cached_at: datetime
    expires_at: datetime


class MindMapCacheStatus(BaseModel):
    paper_id: str
    is_cached: bool
    hit_count: int | None = None
    cached_at: datetime | None = None
    expires_at: datetime | None = None
    ttl_seconds: int | None = None
