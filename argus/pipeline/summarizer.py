"""Summarizer — generates the final structured digest via LLM."""

from __future__ import annotations

import logging
from datetime import date

from argus.pipeline.llm import chat
from argus.pipeline.models import Digest, DigestSection, EnrichedItem

logger = logging.getLogger(__name__)

# Sources that produce research papers vs blog/community content
PAPER_SOURCES = {"arxiv", "semantic_scholar", "huggingface"}
BLOG_SOURCES = {"rss", "reddit"}

SYSTEM_PROMPT = """\
You are Argus, an expert research digest curator for AI safety and evaluation.
Your audience: AI researchers and engineers who track safety-relevant developments closely.
They want to understand a paper or post WITHOUT reading it in full.

You will receive a curated list of the day's top items (papers and blog posts).
Write a structured digest in two sections:

---

## 📄 Papers

For each paper, use this exact format:

### [Title](url)
**Authors:** Name, Name | **Published:** YYYY-MM-DD

**Core Problem:** One crisp sentence — what gap, failure mode, or open question does this paper address?

**Approach:**
- Bullet 1: key design decision or method
- Bullet 2: what they built or tested
- Bullet 3: what dataset/benchmark/setting (if relevant)

**Results:**
- Bullet 1: main quantitative or qualitative finding
- Bullet 2: comparison to prior work or baseline (if applicable)
- Bullet 3: limitation or caveat worth noting

---

## 📰 Blogs & Discussions

For each blog post or forum discussion, use this format:

### [Title](url)
**Source:** name | **Published:** YYYY-MM-DD

**What it covers:** 2–3 sentences. What argument is being made, what data or analysis is shared, and why it matters for safety/evals.

---

Rules:
- Start with a single line: **TL;DR:** followed by 2-3 sentences summarizing today's most important themes across all items.
- Then a blank line, then ## 📄 Papers (or ## 📰 Blogs & Discussions if no papers).
- Be precise. No filler phrases like "The authors propose..." — lead with the substance.
- If there are no blog items, omit the Blogs section entirely (and vice versa).
- Maintain the exact heading format shown — the renderer depends on it.
"""


async def generate_digest(
    items: list[EnrichedItem],
    api_key: str | None = None,  # kept for backward compat; key read from env
) -> Digest:
    """Generate a structured Digest from enriched items via LLM."""
    today = date.today().isoformat()

    if not items:
        return Digest(
            date=today,
            tldr="No relevant items found today.",
            body="",
            sections=[],
            total_items=0,
            sources_used=[],
        )

    papers = [i for i in items if i.source in PAPER_SOURCES]
    blogs = [i for i in items if i.source in BLOG_SOURCES]

    items_text = _format_items_for_prompt(papers, blogs)
    user_message = f"Today is {today}. Generate the digest for these items:\n\n{items_text}"

    try:
        body = await chat(SYSTEM_PROMPT, user_message, role="summarize")
    except Exception as e:
        logger.error("Summarizer API call failed: %s", e)
        body = _fallback_digest(items)

    tldr = _extract_tldr(body, items)

    sources_used = list({item.source for item in items})
    full_section = DigestSection(title="Full Digest", items=items)

    return Digest(
        date=today,
        tldr=tldr,
        body=body,
        sections=[full_section],
        total_items=len(items),
        sources_used=sources_used,
    )


def _format_items_for_prompt(
    papers: list[EnrichedItem], blogs: list[EnrichedItem]
) -> str:
    parts = []

    if papers:
        parts.append("### PAPERS")
        for item in papers:
            authors_str = ", ".join(item.authors[:3]) if item.authors else "Unknown"
            pub_str = item.published_at.date().isoformat() if item.published_at else "recent"
            citation_str = ""
            if item.metadata.get("citation_count"):
                citation_str = f" | Citations: {item.metadata['citation_count']}"
            elif item.metadata.get("upvotes"):
                citation_str = f" | Upvotes: {item.metadata['upvotes']}"
            parts.append(
                f"Title: {item.title}\n"
                f"URL: {item.url}\n"
                f"Authors: {authors_str} | Published: {pub_str}{citation_str}\n"
                f"Abstract: {item.abstract[:800]}\n"
            )

    if blogs:
        parts.append("### BLOGS & DISCUSSIONS")
        for item in blogs:
            pub_str = item.published_at.date().isoformat() if item.published_at else "recent"
            upvote_str = ""
            if item.metadata.get("upvotes"):
                upvote_str = f" | Upvotes: {item.metadata['upvotes']}"
            parts.append(
                f"Title: {item.title}\n"
                f"URL: {item.url}\n"
                f"Source: {item.metadata.get('feed_name', item.source)} | Published: {pub_str}{upvote_str}\n"
                f"Content: {item.abstract[:600]}\n"
            )

    return "\n\n---\n\n".join(parts)


def _extract_tldr(body: str, items: list[EnrichedItem]) -> str:
    """Extract the TL;DR line from the LLM body, or auto-generate."""
    for line in body.strip().split("\n"):
        stripped = line.strip()
        # Look for the explicit TL;DR marker the prompt asks for
        if stripped.lower().startswith("**tl;dr:**"):
            return stripped[len("**tl;dr:**"):].strip()
        if stripped.lower().startswith("tl;dr:"):
            return stripped[len("tl;dr:"):].strip()
    # Fallback: list top item titles
    titles = [i.title[:60] for i in items[:3]]
    return f"Today's highlights: {'; '.join(titles)}."


def _fallback_digest(items: list[EnrichedItem]) -> str:
    lines = [f"## {date.today().isoformat()} — Argus Daily Digest\n"]
    lines.append("*Note: Summary generation failed; showing raw items.*\n")
    for item in items:
        lines.append(f"- [{item.title}]({item.url})")
    return "\n".join(lines)
