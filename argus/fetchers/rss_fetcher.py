"""Generic RSS fetcher for researcher blogs, Anthropic, DeepMind, AI Alignment Forum, LessWrong."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import httpx

from argus.fetchers.base import BaseFetcher
from argus.pipeline.models import RawItem

logger = logging.getLogger(__name__)


class RSSFetcher(BaseFetcher):
    source_name = "rss"

    def __init__(self, feeds: list[dict] | None = None):
        """
        feeds: list of {"url": str, "name": str} dicts.
        If None, uses the default feed list from config/rss_feeds.yaml.
        """
        self.feeds = feeds or self._default_feeds()

    async def fetch(self) -> list[RawItem]:
        items: dict[str, RawItem] = {}

        async with httpx.AsyncClient(
            timeout=20,
            headers={"User-Agent": "Argus-Digest/1.0"},
            follow_redirects=True,
        ) as client:
            for feed in self.feeds:
                try:
                    results = await self._fetch_feed(client, feed)
                    for item in results:
                        if item.id not in items:
                            items[item.id] = item
                except Exception as e:
                    logger.warning("RSS feed '%s' failed: %s", feed.get("name"), e)

        logger.info("RSS: fetched %d unique items", len(items))
        return list(items.values())

    async def _fetch_feed(
        self, client: httpx.AsyncClient, feed: dict
    ) -> list[RawItem]:
        resp = await client.get(feed["url"])
        resp.raise_for_status()
        return self._parse_feed(resp.text, feed["name"])

    def _parse_feed(self, xml_text: str, feed_name: str) -> list[RawItem]:
        items = []
        try:
            # Strip leading whitespace — some feeds have content before <?xml ...?>
            root = ElementTree.fromstring(xml_text.lstrip())
        except ElementTree.ParseError as e:
            logger.warning("Failed to parse RSS feed '%s': %s", feed_name, e)
            return []

        # Handle both RSS 2.0 (<item>) and Atom (<entry>)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall(".//item") or root.findall(".//atom:entry", ns)

        for entry in entries[:20]:  # cap per feed
            try:
                item = self._parse_entry(entry, feed_name, ns)
                if item:
                    items.append(item)
            except Exception as e:
                logger.debug("Failed to parse RSS entry in '%s': %s", feed_name, e)

        return items

    def _parse_entry(
        self, entry: ElementTree.Element, feed_name: str, ns: dict
    ) -> RawItem | None:
        # NOTE: Use explicit `is not None` — ElementTree elements with no children
        # are falsy, so `el or fallback` silently drops valid text-only elements.

        # Title
        title_el = entry.find("title")
        if title_el is None:
            title_el = entry.find("atom:title", ns)
        title = (title_el.text or "").strip() if title_el is not None else ""
        if not title:
            return None

        # Link
        link_el = entry.find("link")
        if link_el is None:
            link_el = entry.find("atom:link", ns)
        url = ""
        if link_el is not None:
            url = link_el.text or link_el.get("href", "")
        url = url.strip()
        if not url:
            return None

        # Description / summary
        desc_el = entry.find("description")
        if desc_el is None:
            desc_el = entry.find("summary")
        if desc_el is None:
            desc_el = entry.find("atom:summary", ns)
        if desc_el is None:
            desc_el = entry.find("content")
        if desc_el is None:
            desc_el = entry.find("atom:content", ns)
        raw_text = ""
        if desc_el is not None and desc_el.text:
            # Strip HTML tags naively
            import re
            raw_text = re.sub(r"<[^>]+>", " ", desc_el.text).strip()
        raw_text = (raw_text or title)[:600]

        # Published date
        pub_el = entry.find("pubDate")
        if pub_el is None:
            pub_el = entry.find("published")
        if pub_el is None:
            pub_el = entry.find("atom:published", ns)
        if pub_el is None:
            pub_el = entry.find("updated")
        if pub_el is None:
            pub_el = entry.find("atom:updated", ns)
        published_at = None
        if pub_el is not None and pub_el.text:
            try:
                published_at = parsedate_to_datetime(pub_el.text.strip())
            except Exception:
                try:
                    published_at = datetime.fromisoformat(
                        pub_el.text.strip().replace("Z", "+00:00")
                    )
                except Exception:
                    pass

        return RawItem(
            id=self.make_id("rss", url),
            title=title,
            url=url,
            source="rss",
            raw_text=raw_text,
            published_at=published_at,
            metadata={"feed_name": feed_name},
        )

    @staticmethod
    def _default_feeds() -> list[dict]:
        """Load feeds from config/rss_feeds.yaml, or fall back to hardcoded defaults."""
        import os

        config_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "config", "rss_feeds.yaml"
        )
        if os.path.exists(config_path):
            try:
                import yaml  # type: ignore[import]

                with open(config_path) as f:
                    data = yaml.safe_load(f)
                    return data.get("feeds", [])
            except Exception:
                pass

        # Hardcoded fallback
        return [
            {
                "name": "Anthropic Blog",
                "url": "https://www.anthropic.com/rss.xml",
            },
            {
                "name": "AI Alignment Forum",
                "url": "https://www.alignmentforum.org/feed.xml",
            },
            {
                "name": "LessWrong",
                "url": "https://www.lesswrong.com/feed.xml?view=curated-rss",
            },
            {
                "name": "DeepMind Blog",
                "url": "https://deepmind.google/blog/rss.xml",
            },
            {
                "name": "OpenAI Blog",
                "url": "https://openai.com/blog/rss.xml",
            },
            {
                "name": "Paul Christiano (ARC)",
                "url": "https://paulfchristiano.com/feed/",
            },
        ]
