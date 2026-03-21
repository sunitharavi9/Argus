"""Tests for Pydantic model validation."""

from datetime import datetime, timezone

from argus.pipeline.models import Digest, DigestSection, EnrichedItem, RawItem


def test_raw_item_defaults():
    item = RawItem(
        id="arxiv:abc123",
        title="Test Paper",
        url="https://arxiv.org/abs/2301.00001",
        source="arxiv",
        raw_text="An abstract about AI safety.",
    )
    assert item.authors == []
    assert item.metadata == {}
    assert item.published_at is None


def test_enriched_item():
    item = EnrichedItem(
        id="arxiv:abc123",
        title="Test Paper",
        url="https://arxiv.org/abs/2301.00001",
        source="arxiv",
        abstract="Full abstract text.",
        tags=["safety", "alignment"],
        relevance_score=8,
    )
    assert item.relevance_score == 8
    assert "safety" in item.tags


def test_digest_construction():
    item = EnrichedItem(
        id="test:1",
        title="Item",
        url="https://example.com",
        source="rss",
        abstract="body",
    )
    section = DigestSection(title="New Papers", items=[item])
    digest = Digest(
        date="2026-03-21",
        tldr="Today in AI safety …",
        sections=[section],
        total_items=1,
        sources_used=["rss"],
    )
    assert digest.total_items == 1
    assert digest.sections[0].title == "New Papers"
