"""Tests for the deduplication module."""

from argus.pipeline.dedup import deduplicate
from argus.pipeline.models import RawItem


def _item(id_: str) -> RawItem:
    return RawItem(
        id=id_,
        title=f"Test {id_}",
        url=f"https://example.com/{id_}",
        source="arxiv",
        raw_text="test abstract",
    )


def test_all_new():
    items = [_item("a"), _item("b"), _item("c")]
    new, updated = deduplicate(items, set())
    assert len(new) == 3
    assert updated == {"a", "b", "c"}


def test_partial_seen():
    items = [_item("a"), _item("b"), _item("c")]
    new, updated = deduplicate(items, {"a"})
    assert len(new) == 2
    assert {i.id for i in new} == {"b", "c"}
    assert "a" in updated


def test_all_seen():
    items = [_item("a"), _item("b")]
    new, updated = deduplicate(items, {"a", "b"})
    assert new == []


def test_empty_input():
    new, updated = deduplicate([], {"a"})
    assert new == []
    assert updated == {"a"}
