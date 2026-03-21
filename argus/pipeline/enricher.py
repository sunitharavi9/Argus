"""Enricher — fetches full abstracts and metadata for filtered items."""

from __future__ import annotations

import asyncio
import logging
import re
from xml.etree import ElementTree

import httpx

from argus.pipeline.models import EnrichedItem, FilterResult, RawItem

logger = logging.getLogger(__name__)

ARXIV_API = "https://export.arxiv.org/api/query"
NS = {"atom": "http://www.w3.org/2005/Atom"}


async def enrich_items(
    items: list[RawItem],
    filter_results: dict[str, FilterResult],
) -> list[EnrichedItem]:
    """Enrich each item with full text and attach relevance metadata."""
    async with httpx.AsyncClient(
        timeout=20,
        headers={"User-Agent": "Argus-Digest/1.0"},
        follow_redirects=True,
    ) as client:
        tasks = [_enrich_one(client, item, filter_results.get(item.id)) for item in items]
        enriched = await asyncio.gather(*tasks, return_exceptions=True)

    results = []
    for item, result in zip(items, enriched):
        if isinstance(result, Exception):
            logger.debug("Enrichment failed for %s: %s", item.id, result)
            # Fall back to basic enrichment
            results.append(_to_enriched(item, filter_results.get(item.id)))
        else:
            results.append(result)  # type: ignore[arg-type]

    return results


async def _enrich_one(
    client: httpx.AsyncClient,
    item: RawItem,
    filter_result: FilterResult | None,
) -> EnrichedItem:
    abstract = item.raw_text

    # For arXiv items, fetch the full abstract via the API
    if item.source in ("arxiv", "huggingface", "semantic_scholar"):
        arxiv_id = _extract_arxiv_id(item.url)
        if arxiv_id:
            try:
                full_abstract = await _fetch_arxiv_abstract(client, arxiv_id)
                if full_abstract:
                    abstract = full_abstract
            except Exception:
                pass  # Use raw_text as fallback

    return _to_enriched(item, filter_result, abstract=abstract)


def _to_enriched(
    item: RawItem,
    filter_result: FilterResult | None,
    abstract: str = "",
) -> EnrichedItem:
    return EnrichedItem(
        id=item.id,
        title=item.title,
        url=item.url,
        source=item.source,
        abstract=abstract or item.raw_text,
        authors=item.authors,
        published_at=item.published_at,
        tags=filter_result.tags if filter_result else [],
        relevance_score=filter_result.score if filter_result else 0,
        metadata=item.metadata,
    )


async def _fetch_arxiv_abstract(
    client: httpx.AsyncClient, arxiv_id: str
) -> str:
    params = {"id_list": arxiv_id, "max_results": 1}
    resp = await client.get(ARXIV_API, params=params)
    resp.raise_for_status()

    root = ElementTree.fromstring(resp.text)
    entry = root.find("atom:entry", NS)
    if entry is None:
        return ""
    summary_el = entry.find("atom:summary", NS)
    return (summary_el.text or "").strip() if summary_el is not None else ""


def _extract_arxiv_id(url: str) -> str:
    """Extract arXiv ID from an abs URL like https://arxiv.org/abs/2301.00001."""
    match = re.search(r"arxiv\.org/(?:abs|pdf)/([^\s?#]+)", url)
    return match.group(1) if match else ""
