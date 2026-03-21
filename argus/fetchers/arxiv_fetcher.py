"""arXiv fetcher — searches recent papers on AI safety, alignment, and evals."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree

import httpx

from argus.fetchers.base import BaseFetcher
from argus.pipeline.models import RawItem

logger = logging.getLogger(__name__)

ARXIV_API = "https://export.arxiv.org/api/query"
ARXIV_DELAY = 3.0  # seconds between requests (arXiv asks for this)

SEARCH_QUERIES = [
    "AI safety",
    "AI alignment",
    "LLM evaluation",
    "red teaming language model",
    "interpretability neural network",
    "AI governance",
    "benchmark language model",
    "RLHF reward model",
    "jailbreak language model",
    "AI risk",
]

CATEGORIES = ["cs.AI", "cs.LG", "cs.CL", "stat.ML"]

NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


class ArxivFetcher(BaseFetcher):
    source_name = "arxiv"

    def __init__(self, max_results_per_query: int = 15, days_back: int = 2):
        self.max_results = max_results_per_query
        self.days_back = days_back

    async def fetch(self) -> list[RawItem]:
        items: dict[str, RawItem] = {}
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.days_back)

        async with httpx.AsyncClient(timeout=30) as client:
            for query in SEARCH_QUERIES:
                try:
                    results = await self._search(client, query, cutoff)
                    for item in results:
                        if item.id not in items:
                            items[item.id] = item
                    await asyncio.sleep(ARXIV_DELAY)
                except Exception as e:
                    logger.warning("arXiv query '%s' failed: %s", query, e)

        logger.info("arXiv: fetched %d unique items", len(items))
        return list(items.values())

    async def _search(
        self, client: httpx.AsyncClient, query: str, cutoff: datetime
    ) -> list[RawItem]:
        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": self.max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        resp = await client.get(ARXIV_API, params=params)
        resp.raise_for_status()

        root = ElementTree.fromstring(resp.text)
        items = []

        for entry in root.findall("atom:entry", NS):
            try:
                item = self._parse_entry(entry, cutoff)
                if item:
                    items.append(item)
            except Exception as e:
                logger.debug("Failed to parse arXiv entry: %s", e)

        return items

    def _parse_entry(
        self, entry: ElementTree.Element, cutoff: datetime
    ) -> RawItem | None:
        title_el = entry.find("atom:title", NS)
        summary_el = entry.find("atom:summary", NS)
        published_el = entry.find("atom:published", NS)
        id_el = entry.find("atom:id", NS)

        if not all([title_el is not None, id_el is not None]):
            return None

        url = id_el.text.strip()  # type: ignore[union-attr]
        # Convert arxiv.org/abs/ URL to abs URL
        url = url.replace("http://", "https://")

        published_str = published_el.text.strip() if published_el is not None else ""
        published_at = None
        if published_str:
            try:
                published_at = datetime.fromisoformat(
                    published_str.replace("Z", "+00:00")
                )
            except ValueError:
                pass

        # Skip old papers
        if published_at and published_at < cutoff:
            return None

        authors = [
            a.find("atom:name", NS).text.strip()  # type: ignore[union-attr]
            for a in entry.findall("atom:author", NS)
            if a.find("atom:name", NS) is not None
        ]

        abstract = (summary_el.text or "").strip() if summary_el is not None else ""
        title = (title_el.text or "").strip()  # type: ignore[union-attr]

        return RawItem(
            id=self.make_id("arxiv", url),
            title=title,
            url=url,
            source="arxiv",
            raw_text=abstract[:600],
            authors=authors[:5],
            published_at=published_at,
            metadata={"arxiv_id": url.split("/")[-1]},
        )
