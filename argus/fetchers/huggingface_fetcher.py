"""HuggingFace Daily Papers fetcher — community-curated ML papers."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from argus.fetchers.base import BaseFetcher
from argus.pipeline.models import RawItem

logger = logging.getLogger(__name__)

HF_PAPERS_URL = "https://huggingface.co/papers"


class HuggingFaceFetcher(BaseFetcher):
    source_name = "huggingface"

    async def fetch(self) -> list[RawItem]:
        try:
            async with httpx.AsyncClient(
                timeout=20,
                headers={"User-Agent": "Argus-Digest/1.0"},
                follow_redirects=True,
            ) as client:
                resp = await client.get(HF_PAPERS_URL)
                resp.raise_for_status()
                items = self._parse(resp.text)
                logger.info("HuggingFace: fetched %d items", len(items))
                return items
        except Exception as e:
            logger.warning("HuggingFace fetch failed: %s", e)
            return []

    def _parse(self, html: str) -> list[RawItem]:
        soup = BeautifulSoup(html, "html.parser")
        items = []

        # HF papers page: each paper is an <article> or an <h3> link
        for article in soup.select("article"):
            try:
                link = article.find("a", href=re.compile(r"^/papers/"))
                if not link:
                    continue

                title_el = article.find("h3") or article.find("h2")
                title = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)

                href = link["href"]
                url = f"https://huggingface.co{href}"

                # Try to get upvotes as a relevance signal
                upvote_el = article.select_one("[data-upvotes], .upvote-count, .vote-count")
                upvotes = 0
                if upvote_el:
                    txt = upvote_el.get_text(strip=True)
                    try:
                        upvotes = int(re.sub(r"[^\d]", "", txt))
                    except ValueError:
                        pass

                # Extract abstract/description snippet if present
                desc_el = article.find("p")
                raw_text = desc_el.get_text(strip=True) if desc_el else title

                arxiv_id = href.split("/")[-1]
                arxiv_url = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else url

                items.append(
                    RawItem(
                        id=self.make_id("huggingface", url),
                        title=title,
                        url=arxiv_url,  # prefer arxiv link for full abstract
                        source="huggingface",
                        raw_text=raw_text[:600],
                        published_at=datetime.now(timezone.utc),
                        metadata={"hf_url": url, "upvotes": upvotes},
                    )
                )
            except Exception as e:
                logger.debug("Failed to parse HF article: %s", e)

        return items
