"""Quick smoke-test: run all fetchers and print item counts."""
import asyncio

from argus.fetchers.arxiv_fetcher import ArxivFetcher
from argus.fetchers.huggingface_fetcher import HuggingFaceFetcher
from argus.fetchers.rss_fetcher import RSSFetcher
from argus.fetchers.semantic_scholar_fetcher import SemanticScholarFetcher
from argus.fetchers.reddit_fetcher import RedditFetcher


async def main() -> None:
    fetchers = [
        ArxivFetcher(),
        SemanticScholarFetcher(),
        HuggingFaceFetcher(),
        RSSFetcher(),
        RedditFetcher(),
    ]
    total = 0
    for f in fetchers:
        results = await f.fetch()
        print(f"{f.source_name}: {len(results)} items")
        total += len(results)
    print(f"Total: {total} raw items")


asyncio.run(main())
