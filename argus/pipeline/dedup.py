"""Deduplication — filters already-seen items using a committed JSON state file."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from argus.pipeline.models import RawItem

logger = logging.getLogger(__name__)

DEFAULT_STATE_PATH = Path(__file__).parents[2] / "data" / "seen_ids.json"


def load_seen_ids(path: Path = DEFAULT_STATE_PATH) -> set[str]:
    """Load the set of already-processed item IDs."""
    if not path.exists():
        return set()
    try:
        with open(path) as f:
            data = json.load(f)
        return set(data) if isinstance(data, list) else set()
    except Exception as e:
        logger.warning("Could not load seen_ids from %s: %s", path, e)
        return set()


def save_seen_ids(seen_ids: set[str], path: Path = DEFAULT_STATE_PATH) -> None:
    """Persist the updated seen-IDs set back to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "w") as f:
            json.dump(sorted(seen_ids), f, indent=2)
        logger.debug("Saved %d seen IDs to %s", len(seen_ids), path)
    except Exception as e:
        logger.warning("Could not save seen_ids to %s: %s", path, e)


def deduplicate(
    items: list[RawItem],
    seen_ids: set[str],
) -> tuple[list[RawItem], set[str]]:
    """
    Filter out items whose IDs are already in seen_ids.

    Returns:
        (new_items, updated_seen_ids)
    """
    new_items = [item for item in items if item.id not in seen_ids]
    updated = seen_ids | {item.id for item in new_items}
    logger.info(
        "Dedup: %d total → %d new (skipped %d)",
        len(items),
        len(new_items),
        len(items) - len(new_items),
    )
    return new_items, updated
