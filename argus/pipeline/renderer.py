"""Renderer — applies the Jinja2 template to produce the final Markdown digest."""

from __future__ import annotations

import os
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from argus.pipeline.models import Digest

TEMPLATE_DIR = Path(__file__).parents[2] / "templates"
TEMPLATE_NAME = "digest.md.jinja2"


def render_digest(digest: Digest, digest_body: str) -> str:
    """
    Render a Digest + raw LLM body text into the final Markdown string.

    Args:
        digest: structured Digest metadata (date, tldr, sources, etc.)
        digest_body: the raw Markdown text produced by the summarizer LLM call
    """
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=False,
        keep_trailing_newline=True,
    )
    template = env.get_template(TEMPLATE_NAME)
    return template.render(digest=digest, digest_body=digest_body)
