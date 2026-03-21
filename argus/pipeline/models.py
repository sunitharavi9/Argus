"""Pydantic models — the shared schema between all fetchers and pipeline stages."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class RawItem(BaseModel):
    """Universal output schema for every fetcher."""

    id: str  # "{source}:{sha256_of_url_or_content}"
    title: str
    url: str
    source: str  # "arxiv" | "semantic_scholar" | "huggingface" | "reddit" | "rss"
    raw_text: str  # first ~500 chars of abstract/body; used for filtering
    authors: list[str] = Field(default_factory=list)
    published_at: Optional[datetime] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FilterResult(BaseModel):
    """LLM relevance assessment for a single RawItem."""

    item_id: str
    score: int  # 0-10
    tags: list[str] = Field(default_factory=list)  # e.g. ["evals", "safety"]
    reason: str = ""


class EnrichedItem(BaseModel):
    """RawItem + additional metadata fetched during enrichment."""

    id: str
    title: str
    url: str
    source: str
    abstract: str  # full abstract / body text (may be longer than raw_text)
    authors: list[str] = Field(default_factory=list)
    published_at: Optional[datetime] = None
    tags: list[str] = Field(default_factory=list)
    relevance_score: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class DigestSection(BaseModel):
    """A named group of items inside the digest (e.g. 'New Papers')."""

    title: str
    items: list[EnrichedItem]


class Digest(BaseModel):
    """The fully assembled daily digest ready for rendering."""

    date: str  # "2026-03-21"
    tldr: str
    body: str = ""  # full LLM-generated markdown digest body
    sections: list[DigestSection]
    total_items: int
    sources_used: list[str]
