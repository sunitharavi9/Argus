"""Optional Slack delivery via incoming webhook."""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

MAX_CHARS = 2900  # Slack block text limit


async def send_slack(
    markdown_content: str,
    digest_date: str,
    webhook_url: str | None = None,
    repo_url: str | None = None,
) -> bool:
    """Post a truncated digest snippet to Slack with a link to the full digest."""
    webhook_url = webhook_url or os.environ.get("SLACK_WEBHOOK_URL", "")
    if not webhook_url:
        logger.debug("SLACK_WEBHOOK_URL not set; skipping Slack delivery")
        return False

    snippet = markdown_content[:MAX_CHARS]
    if len(markdown_content) > MAX_CHARS:
        snippet += "\n\n_[truncated — see full digest in repo]_"

    full_link = ""
    if repo_url:
        full_link = f"\n\n<{repo_url}/blob/main/digests/{digest_date}.md|View full digest>"

    payload = {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":robot_face: *Argus Daily Digest — {digest_date}*{full_link}",
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": snippet},
            },
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(webhook_url, json=payload)
            if resp.status_code == 200:
                logger.info("Slack notification sent")
                return True
            logger.warning("Slack webhook returned %d", resp.status_code)
            return False
    except Exception as e:
        logger.error("Slack delivery failed: %s", e)
        return False
