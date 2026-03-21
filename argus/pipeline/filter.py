"""Relevance filter — scores items on AI safety/eval topics via LLM."""

from __future__ import annotations

import json
import logging
from typing import Any

from argus.pipeline.llm import chat
from argus.pipeline.models import FilterResult, RawItem

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 6
BATCH_SIZE = 20

SYSTEM_PROMPT = """\
You are an expert classifier for AI safety and evaluation research content.
Score each item on relevance to the core topics below.

HIGH relevance (score 7-10): directly about these topics:
- AI safety, AI alignment, value learning, corrigibility
- AI evaluation, benchmarks, capability assessments
- Red-teaming, jailbreaks, adversarial prompting
- Mechanistic interpretability, feature/circuit analysis
- RLHF, reward modeling, constitutional AI, preference learning
- AI governance, policy, regulation, AI risk
- Agentic AI safety, multi-agent safety
- LLM robustness, debiasing, fairness in the context of safety

LOW relevance (score 0-4): general ML papers unrelated to safety/evals:
- Image generation, audio synthesis, robotics without safety focus
- NLP tasks (summarization, translation) without safety angle
- General computer vision, recommendation systems
- Any paper only tangentially mentioning "safety" in passing

Score 5-6 only if the connection to safety/evals is indirect but real.
Tags: pick from [evals, alignment, interpretability, red-teaming, governance,
benchmark, safety, model-release, research, policy, jailbreak, RLHF].

Respond ONLY with a JSON array, one object per item:
[
  {"item_id": "...", "score": 8, "tags": ["safety", "alignment"], "reason": "..."},
  ...
]
"""


async def filter_items(
    items: list[RawItem],
    threshold: int = DEFAULT_THRESHOLD,
    api_key: str | None = None,  # kept for backward compat; key read from env
) -> tuple[list[RawItem], dict[str, FilterResult]]:
    """Score all items via LLM and return (passed_items, all_filter_results)."""
    if not items:
        return [], {}

    results: dict[str, FilterResult] = {}

    for batch_start in range(0, len(items), BATCH_SIZE):
        batch = items[batch_start : batch_start + BATCH_SIZE]
        batch_results = await _score_batch(batch)
        results.update({r.item_id: r for r in batch_results})

    passed = [
        item
        for item in items
        if results.get(item.id, FilterResult(item_id=item.id, score=0)).score
        >= threshold
    ]

    logger.info(
        "Filter: %d items scored, %d passed threshold %d",
        len(results),
        len(passed),
        threshold,
    )
    return passed, results


async def _score_batch(batch: list[RawItem]) -> list[FilterResult]:
    """Send one batch to the LLM and parse the JSON response."""
    items_text = "\n".join(
        f'- item_id: "{item.id}"\n  title: "{item.title}"\n  text: "{item.raw_text[:300]}"'
        for item in batch
    )
    user_message = f"Score these {len(batch)} items:\n\n{items_text}"

    try:
        text = await chat(SYSTEM_PROMPT, user_message, role="filter")
        return _parse_filter_response(text, batch)
    except Exception as e:
        logger.warning("Filter API call failed: %s — passing batch through", e)
        return [FilterResult(item_id=item.id, score=5) for item in batch]


def _parse_filter_response(
    text: str, batch: list[RawItem]
) -> list[FilterResult]:
    """Extract JSON array from the model response."""
    # Find first [ ... ] block
    start = text.find("[")
    end = text.rfind("]") + 1
    if start == -1 or end == 0:
        logger.warning("Filter response had no JSON array; using defaults")
        return [FilterResult(item_id=item.id, score=5) for item in batch]

    try:
        data: list[dict[str, Any]] = json.loads(text[start:end])
    except json.JSONDecodeError as e:
        logger.warning("Filter JSON parse error: %s", e)
        return [FilterResult(item_id=item.id, score=5) for item in batch]

    results = []
    id_set = {item.id for item in batch}

    for obj in data:
        item_id = obj.get("item_id", "")
        if item_id not in id_set:
            continue
        results.append(
            FilterResult(
                item_id=item_id,
                score=int(obj.get("score", 0)),
                tags=obj.get("tags", []),
                reason=obj.get("reason", ""),
            )
        )

    # Fill in any items the model missed
    returned_ids = {r.item_id for r in results}
    for item in batch:
        if item.id not in returned_ids:
            results.append(FilterResult(item_id=item.id, score=0))

    return results
