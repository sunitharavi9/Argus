"""Settings — reads configuration from environment variables and config YAML."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).parents[2] / "config"


def _load_yaml(filename: str) -> dict:
    path = CONFIG_DIR / filename
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


class Settings:
    """Central settings object. All values read from env vars with YAML fallbacks."""

    def __init__(self) -> None:
        sentinel_cfg = _load_yaml("sentinel.yaml")

        # API keys
        self.groq_api_key: str = os.environ.get("GROQ_API_KEY", "")
        self.anthropic_api_key: str = os.environ.get("ANTHROPIC_API_KEY", "")
        self.resend_api_key: str = os.environ.get("RESEND_API_KEY", "")
        self.reddit_client_id: str = os.environ.get("REDDIT_CLIENT_ID", "")
        self.reddit_client_secret: str = os.environ.get("REDDIT_CLIENT_SECRET", "")
        self.semantic_scholar_api_key: str = os.environ.get(
            "SEMANTIC_SCHOLAR_API_KEY", ""
        )
        self.slack_webhook_url: str = os.environ.get("SLACK_WEBHOOK_URL", "")

        # Delivery
        self.email_to: list[str] = [
            addr.strip()
            for addr in os.environ.get("DIGEST_EMAIL_TO", "").split(",")
            if addr.strip()
        ]
        self.email_from: str = os.environ.get(
            "DIGEST_EMAIL_FROM",
            sentinel_cfg.get("email", {}).get("from", "Argus <digest@yourdomain.com>"),
        )
        self.repo_url: str = os.environ.get(
            "REPO_URL", sentinel_cfg.get("repo_url", "")
        )

        # Pipeline tuning
        self.filter_threshold: int = int(
            os.environ.get(
                "FILTER_THRESHOLD",
                sentinel_cfg.get("filter", {}).get("threshold", 6),
            )
        )
        self.arxiv_days_back: int = int(
            sentinel_cfg.get("sources", {}).get("arxiv_days_back", 2)
        )
        self.s2_days_back: int = int(
            sentinel_cfg.get("sources", {}).get("s2_days_back", 7)
        )
        self.max_digest_items: int = int(
            os.environ.get(
                "MAX_DIGEST_ITEMS",
                sentinel_cfg.get("filter", {}).get("max_digest_items", 10),
            )
        )

        # Git delivery
        self.git_push: bool = os.environ.get("GIT_PUSH", "true").lower() == "true"


# Singleton
settings = Settings()
