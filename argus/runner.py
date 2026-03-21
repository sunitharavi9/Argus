"""Runner — top-level orchestrator that wires all pipeline stages together."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import date

from argus.config.settings import settings
from argus.delivery.email_delivery import send_email
from argus.delivery.git_delivery import commit_digest
from argus.delivery.slack_delivery import send_slack
from argus.fetchers.arxiv_fetcher import ArxivFetcher
from argus.fetchers.huggingface_fetcher import HuggingFaceFetcher
from argus.fetchers.reddit_fetcher import RedditFetcher
from argus.fetchers.rss_fetcher import RSSFetcher
from argus.fetchers.semantic_scholar_fetcher import SemanticScholarFetcher
from argus.pipeline.dedup import deduplicate, load_seen_ids, save_seen_ids
from argus.pipeline.enricher import enrich_items
from argus.pipeline.filter import filter_items
from argus.pipeline.models import FilterResult, RawItem
from argus.pipeline.renderer import render_digest
from argus.pipeline.summarizer import generate_digest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("argus.runner")


async def run() -> str:
    """
    Full pipeline: fetch → dedup → filter → enrich → rank → summarize → render → deliver.

    Returns the final rendered Markdown digest string.
    """
    today = date.today().isoformat()
    logger.info("=== Argus starting — %s ===", today)

    # ── 1. FETCH (parallel) ────────────────────────────────────────────────
    logger.info("Phase 1: Fetching from all sources …")
    raw_items = await _fetch_all()
    logger.info("Fetched %d total raw items", len(raw_items))

    # ── 2. DEDUP ───────────────────────────────────────────────────────────
    logger.info("Phase 2: Deduplicating …")
    seen_ids = load_seen_ids()
    new_items, _ = deduplicate(raw_items, seen_ids)

    # ── 3. FILTER ──────────────────────────────────────────────────────────
    logger.info("Phase 3: Filtering …")
    filtered, filter_map = await filter_items(
        new_items,
        threshold=settings.filter_threshold,
        api_key=settings.anthropic_api_key,
    )
    # Only mark items as seen once they've passed the filter.
    # Items dropped due to irrelevance OR filter errors get retried next run.
    updated_seen_ids = seen_ids | {item.id for item in filtered}

    # ── 4. ENRICH ──────────────────────────────────────────────────────────
    logger.info("Phase 4: Enriching %d items …", len(filtered))
    enriched = await enrich_items(filtered, filter_map)

    # ── 5. RANK → TOP N ────────────────────────────────────────────────────
    top_items = _select_top_items(enriched, n=settings.max_digest_items)
    logger.info(
        "Phase 5: Selected top %d / %d items for digest", len(top_items), len(enriched)
    )

    # ── 6. SUMMARIZE ───────────────────────────────────────────────────────
    logger.info("Phase 6: Generating structured digest …")
    digest = await generate_digest(top_items, api_key=settings.anthropic_api_key)

    # ── 7. RENDER ──────────────────────────────────────────────────────────
    logger.info("Phase 7: Rendering …")
    # Use LLM-generated body; fall back to simple body if empty
    digest_body = digest.body or _build_digest_body(top_items)
    rendered = render_digest(digest, digest_body)

    # ── 8. DELIVER ─────────────────────────────────────────────────────────
    logger.info("Phase 8: Delivering …")
    await _deliver(rendered, today)

    # ── 9. PERSIST STATE ───────────────────────────────────────────────────
    save_seen_ids(updated_seen_ids)
    logger.info("=== Argus complete — %d items in digest ===", digest.total_items)

    return rendered


async def _fetch_all() -> list[RawItem]:
    """Run all fetchers in parallel and merge results."""
    fetchers = [
        ArxivFetcher(days_back=settings.arxiv_days_back),
        SemanticScholarFetcher(
            api_key=settings.semantic_scholar_api_key or None,
            days_back=settings.s2_days_back,
        ),
        HuggingFaceFetcher(),
        RedditFetcher(
            client_id=settings.reddit_client_id or None,
            client_secret=settings.reddit_client_secret or None,
        ),
        RSSFetcher(),
    ]

    results = await asyncio.gather(
        *[f.fetch() for f in fetchers], return_exceptions=True
    )

    all_items: list[RawItem] = []
    for fetcher, result in zip(fetchers, results):
        if isinstance(result, Exception):
            logger.warning("%s failed: %s", fetcher.source_name, result)
        else:
            all_items.extend(result)  # type: ignore[arg-type]

    return all_items


def _select_top_items(enriched: list, n: int = 10) -> list:
    """
    Pick the top N items ranked by relevance score, with a popularity bonus.

    Scoring:
    - relevance_score (0-10) from the LLM filter — primary signal
    - citation_count / upvotes from metadata — tie-breaker bonus (log-scaled)
    - Papers and blogs compete in the same pool; we aim for a mix.
    """
    import math

    def _sort_key(item):
        base = item.relevance_score
        pop = item.metadata.get("citation_count") or item.metadata.get("upvotes") or 0
        # Log bonus caps at ~1.0 for 10 citations, ~2.0 for 100, ~3.0 for 1000
        bonus = math.log10(pop + 1) * 0.3
        return base + bonus

    # Split into papers and blogs to ensure representation of each type
    paper_sources = {"arxiv", "semantic_scholar", "huggingface"}
    papers = sorted(
        [i for i in enriched if i.source in paper_sources], key=_sort_key, reverse=True
    )
    blogs = sorted(
        [i for i in enriched if i.source not in paper_sources], key=_sort_key, reverse=True
    )

    # Reserve up to 3 slots for blogs; fill the rest with papers
    max_blogs = min(len(blogs), 3)
    max_papers = n - max_blogs
    selected = papers[:max_papers] + blogs[:max_blogs]

    # Final sort by score so the digest reads best-first
    return sorted(selected, key=_sort_key, reverse=True)


def _build_digest_body(enriched) -> str:
    """Build simple Markdown body from enriched items grouped by source/tag."""
    from collections import defaultdict

    if not enriched:
        return "_No relevant items found today._"

    # Group by dominant tag
    groups: dict[str, list] = defaultdict(list)
    tag_map = {
        "research": "New Papers",
        "evals": "New Papers",
        "benchmark": "New Papers",
        "alignment": "New Papers",
        "interpretability": "New Papers",
        "safety": "New Papers",
        "RLHF": "New Papers",
        "model-release": "Lab & Industry News",
        "governance": "Governance & Policy",
        "policy": "Governance & Policy",
        "red-teaming": "New Papers",
        "jailbreak": "New Papers",
    }

    for item in enriched:
        placed = False
        for tag in item.tags:
            section = tag_map.get(tag)
            if section:
                groups[section].append(item)
                placed = True
                break
        if not placed:
            # Source-based fallback
            if item.source == "reddit":
                groups["Community Discussion"].append(item)
            elif item.source == "rss":
                groups["Lab & Industry News"].append(item)
            else:
                groups["New Papers"].append(item)

    section_order = [
        "New Papers",
        "Lab & Industry News",
        "Governance & Policy",
        "Community Discussion",
    ]

    lines = []
    for section_title in section_order:
        items = groups.get(section_title, [])
        if not items:
            continue
        lines.append(f"## {section_title}\n")
        for item in sorted(items, key=lambda x: x.relevance_score, reverse=True):
            authors_str = (
                f" — {', '.join(item.authors[:2])}" if item.authors else ""
            )
            pub_str = (
                f" ({item.published_at.date()})"
                if item.published_at
                else ""
            )
            lines.append(f"### [{item.title}]({item.url}){authors_str}{pub_str}\n")
            abstract = item.abstract[:400].replace("\n", " ").strip()
            if abstract:
                lines.append(f"{abstract}\n")
            if item.tags:
                lines.append(f"*Tags: {', '.join(item.tags)}*\n")
            lines.append("")

    return "\n".join(lines)


async def _deliver(rendered: str, today: str) -> None:
    """Run all delivery channels."""
    subject = f"Argus Daily Digest — {today}"

    tasks = [
        send_email(
            rendered,
            subject=subject,
            api_key=settings.resend_api_key or None,
            to_addresses=settings.email_to or None,
            from_address=settings.email_from,
        ),
    ]

    if settings.slack_webhook_url:
        tasks.append(
            send_slack(
                rendered,
                digest_date=today,
                webhook_url=settings.slack_webhook_url,
                repo_url=settings.repo_url or None,
            )
        )

    await asyncio.gather(*tasks, return_exceptions=True)

    # Git delivery is synchronous (uses subprocess)
    if settings.git_push:
        commit_digest(today, rendered)
    else:
        # Still write the file locally even if not pushing
        from pathlib import Path
        digest_path = Path(__file__).parents[1] / "digests" / f"{today}.md"
        digest_path.parent.mkdir(parents=True, exist_ok=True)
        digest_path.write_text(rendered, encoding="utf-8")
        logger.info("Digest written to %s (no git push)", digest_path)


def main() -> None:
    """Entry point for CLI and GitHub Actions."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
