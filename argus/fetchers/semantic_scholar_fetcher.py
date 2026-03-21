"""Semantic Scholar fetcher — searches recent and highly-cited papers."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from argus.fetchers.base import BaseFetcher
from argus.pipeline.models import RawItem

logger = logging.getLogger(__name__)

S2_SEARCH = "https://api.semanticscholar.org/graph/v1/paper/search"

FIELDS = "title,abstract,authors,year,publicationDate,externalIds,citationCount,url"

# Targeted queries for the "recent papers" mode (14-day window)
RECENT_QUERIES = [
    "AI safety alignment",
    "LLM evaluation benchmark",
    "red teaming language model",
    "mechanistic interpretability",
    "AI governance regulation",
    "jailbreak adversarial LLM",
    "RLHF reward model",
]

# Broader queries for the "influential older papers" mode (90-day window, min citations)
INFLUENTIAL_QUERIES = [
    "AI alignment corrigibility",
    "language model evaluation safety",
    "mechanistic interpretability transformer",
    "red teaming large language models",
    "AI risk governance",
]


class SemanticScholarFetcher(BaseFetcher):
    source_name = "semantic_scholar"

    def __init__(
        self,
        api_key: str | None = None,
        max_results_per_query: int = 10,
        days_back: int = 14,
    ):
        self.api_key = api_key
        self.max_results = max_results_per_query
        self.days_back = days_back

    async def fetch(self) -> list[RawItem]:
        items: dict[str, RawItem] = {}
        headers = {}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            # Mode 1: recent papers (days_back window)
            recent_cutoff = datetime.now(timezone.utc) - timedelta(days=self.days_back)
            for query in RECENT_QUERIES:
                try:
                    results = await self._search(client, query, cutoff=recent_cutoff)
                    for item in results:
                        if item.id not in items:
                            items[item.id] = item
                except Exception as e:
                    logger.warning("S2 query '%s' failed: %s", query, e)

            # Mode 2: influential papers from the last 90 days (min 5 citations)
            # Surfaces high-quality work you might have missed
            influential_cutoff = datetime.now(timezone.utc) - timedelta(days=90)
            for query in INFLUENTIAL_QUERIES:
                try:
                    results = await self._search(
                        client, query,
                        cutoff=influential_cutoff,
                        min_citation_count=5,
                    )
                    for item in results:
                        if item.id not in items:
                            items[item.id] = item
                except Exception as e:
                    logger.warning("S2 influential query '%s' failed: %s", query, e)

        logger.info("Semantic Scholar: fetched %d unique items", len(items))
        return list(items.values())

    async def _search(
        self,
        client: httpx.AsyncClient,
        query: str,
        cutoff: datetime,
        min_citation_count: int = 0,
    ) -> list[RawItem]:
        params: dict = {
            "query": query,
            "limit": self.max_results,
            "fields": FIELDS,
        }
        if min_citation_count > 0:
            params["minCitationCount"] = min_citation_count

        resp = await client.get(S2_SEARCH, params=params)
        if resp.status_code == 429:
            logger.warning("Semantic Scholar rate limited; skipping query '%s'", query)
            return []
        resp.raise_for_status()

        data = resp.json()
        items = []

        for paper in data.get("data", []):
            try:
                item = self._parse_paper(paper, cutoff)
                if item:
                    items.append(item)
            except Exception as e:
                logger.debug("Failed to parse S2 paper: %s", e)

        return items

    def _parse_paper(
        self, paper: dict, cutoff: datetime
    ) -> RawItem | None:
        title = paper.get("title", "").strip()
        if not title:
            return None

        ext = paper.get("externalIds") or {}
        arxiv_id = ext.get("ArXiv")
        doi = ext.get("DOI")
        url = paper.get("url") or ""

        if arxiv_id:
            url = f"https://arxiv.org/abs/{arxiv_id}"
        elif doi:
            url = f"https://doi.org/{doi}"
        elif not url:
            url = f"https://www.semanticscholar.org/paper/{paper.get('paperId', '')}"

        pub_date_str = paper.get("publicationDate") or ""
        published_at = None
        if pub_date_str:
            try:
                published_at = datetime.fromisoformat(pub_date_str).replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                pass

        if published_at and published_at < cutoff:
            return None

        authors = [
            a.get("name", "") for a in (paper.get("authors") or []) if a.get("name")
        ]
        abstract = (paper.get("abstract") or "").strip()
        citation_count = paper.get("citationCount", 0)

        return RawItem(
            id=self.make_id("semantic_scholar", url),
            title=title,
            url=url,
            source="semantic_scholar",
            raw_text=abstract[:600],
            authors=authors[:5],
            published_at=published_at,
            metadata={
                "citation_count": citation_count,
                "paper_id": paper.get("paperId", ""),
            },
        )
