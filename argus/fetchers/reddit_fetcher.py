"""Reddit fetcher — monitors AI safety and ML subreddits via PRAW."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from argus.fetchers.base import BaseFetcher
from argus.pipeline.models import RawItem

logger = logging.getLogger(__name__)

SUBREDDITS = ["aisafety", "MachineLearning", "AIAlignment", "artificial"]
MIN_SCORE = 30
POST_LIMIT = 25  # per subreddit


class RedditFetcher(BaseFetcher):
    source_name = "reddit"

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
    ):
        self.client_id = client_id or os.environ.get("REDDIT_CLIENT_ID", "")
        self.client_secret = client_secret or os.environ.get(
            "REDDIT_CLIENT_SECRET", ""
        )

    async def fetch(self) -> list[RawItem]:
        if not self.client_id or not self.client_secret:
            logger.info("Reddit credentials not set; skipping Reddit fetcher")
            return []

        try:
            import praw  # type: ignore[import]
        except ImportError:
            logger.warning("praw not installed; skipping Reddit fetcher")
            return []

        reddit = praw.Reddit(
            client_id=self.client_id,
            client_secret=self.client_secret,
            user_agent="Argus-Digest/1.0 (by /u/argus_bot)",
            read_only=True,
        )

        items: dict[str, RawItem] = {}

        for subreddit_name in SUBREDDITS:
            try:
                subreddit = reddit.subreddit(subreddit_name)
                for post in subreddit.hot(limit=POST_LIMIT):
                    if post.score < MIN_SCORE:
                        continue
                    item = self._parse_post(post, subreddit_name)
                    if item and item.id not in items:
                        items[item.id] = item
            except Exception as e:
                logger.warning("Reddit r/%s failed: %s", subreddit_name, e)

        logger.info("Reddit: fetched %d unique items", len(items))
        return list(items.values())

    def _parse_post(self, post: object, subreddit: str) -> RawItem | None:
        url = f"https://www.reddit.com{post.permalink}"  # type: ignore[attr-defined]
        title = post.title.strip()  # type: ignore[attr-defined]

        # Prefer external link; fall back to selftext
        link_url = post.url  # type: ignore[attr-defined]
        is_self = getattr(post, "is_self", False)

        text_parts = [title]
        if is_self:
            body = (post.selftext or "")[:400]  # type: ignore[attr-defined]
            if body:
                text_parts.append(body)
        else:
            text_parts.append(f"Link: {link_url}")

        raw_text = "\n".join(text_parts)[:600]

        created_utc = getattr(post, "created_utc", None)
        published_at = None
        if created_utc:
            published_at = datetime.fromtimestamp(created_utc, tz=timezone.utc)

        return RawItem(
            id=self.make_id("reddit", url),
            title=title,
            url=link_url if not is_self else url,
            source="reddit",
            raw_text=raw_text,
            published_at=published_at,
            metadata={
                "subreddit": subreddit,
                "score": post.score,  # type: ignore[attr-defined]
                "reddit_url": url,
                "num_comments": getattr(post, "num_comments", 0),
            },
        )
