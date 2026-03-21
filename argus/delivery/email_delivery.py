"""Email delivery via Resend API — converts Markdown digest to HTML and sends it."""

from __future__ import annotations

import logging
import os

import httpx
import mistune  # type: ignore[import]

logger = logging.getLogger(__name__)

RESEND_API = "https://api.resend.com/emails"


async def send_email(
    markdown_content: str,
    subject: str,
    api_key: str | None = None,
    to_addresses: list[str] | None = None,
    from_address: str = "Argus <digest@yourdomain.com>",
) -> bool:
    """
    Send the digest as an HTML email via Resend.

    Returns True on success, False on failure.
    """
    api_key = api_key or os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        logger.info("RESEND_API_KEY not set; skipping email delivery")
        return False

    recipients = to_addresses or _parse_recipients()
    if not recipients:
        logger.info("No email recipients configured; skipping email delivery")
        return False

    html_content = _markdown_to_html(markdown_content)

    payload = {
        "from": from_address,
        "to": recipients,
        "subject": subject,
        "html": html_content,
        "text": markdown_content,  # plain text fallback
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                RESEND_API,
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if resp.status_code in (200, 201):
                logger.info("Email sent to %s", recipients)
                return True
            else:
                logger.warning(
                    "Resend returned %d: %s", resp.status_code, resp.text[:200]
                )
                return False
    except Exception as e:
        logger.error("Email delivery failed: %s", e)
        return False


def _markdown_to_html(markdown_content: str) -> str:
    """Convert Markdown to HTML with basic styling."""
    body_html = mistune.html(markdown_content)
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          max-width: 720px; margin: 40px auto; padding: 0 20px;
          color: #1a1a1a; line-height: 1.6; }}
  h1 {{ font-size: 1.6em; border-bottom: 2px solid #e0e0e0; padding-bottom: 8px; }}
  h2 {{ font-size: 1.2em; margin-top: 2em; }}
  h3 {{ font-size: 1em; }}
  blockquote {{ border-left: 4px solid #4a90d9; margin: 1em 0;
               padding: 0.5em 1em; background: #f0f6ff; }}
  a {{ color: #2563eb; }}
  code {{ background: #f4f4f4; padding: 2px 5px; border-radius: 3px; }}
  hr {{ border: none; border-top: 1px solid #e0e0e0; margin: 2em 0; }}
  em {{ color: #555; }}
</style>
</head>
<body>
{body_html}
</body>
</html>"""


def _parse_recipients() -> list[str]:
    """Parse comma-separated email addresses from env var."""
    raw = os.environ.get("DIGEST_EMAIL_TO", "")
    if not raw:
        return []
    return [addr.strip() for addr in raw.split(",") if addr.strip()]
