"""Git delivery — commits the rendered digest and updated seen_ids.json to the repo."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).parents[2]


def commit_digest(digest_date: str, digest_content: str) -> bool:
    """
    Write the digest to digests/<date>.md and commit with seen_ids.json.

    Returns True on success.
    """
    digest_path = REPO_ROOT / "digests" / f"{digest_date}.md"
    digest_path.parent.mkdir(parents=True, exist_ok=True)

    digest_path.write_text(digest_content, encoding="utf-8")
    logger.info("Wrote digest to %s", digest_path)

    _update_digests_index(digest_date)

    try:
        _git(["config", "user.email", os.environ.get("GIT_EMAIL", "argus-bot@users.noreply.github.com")])
        _git(["config", "user.name", os.environ.get("GIT_NAME", "Argus Bot")])

        _git(["add", str(digest_path)])

        seen_ids_path = REPO_ROOT / "data" / "seen_ids.json"
        if seen_ids_path.exists():
            _git(["add", str(seen_ids_path)])

        index_path = REPO_ROOT / "digests" / "README.md"
        if index_path.exists():
            _git(["add", str(index_path)])

        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=REPO_ROOT,
            capture_output=True,
        )
        if result.returncode == 0:
            logger.info("No changes to commit")
            return True

        _git(["commit", "-m", f"digest: {digest_date}"])
        _git(["push"])
        logger.info("Committed and pushed digest for %s", digest_date)
        return True

    except subprocess.CalledProcessError as e:
        logger.error("Git operation failed: %s", e)
        return False


def _git(args: list[str]) -> None:
    """Run a git command, raising on non-zero exit."""
    subprocess.run(
        ["git"] + args,
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def _update_digests_index(new_date: str) -> None:
    """Maintain a simple README index of all digest files."""
    digests_dir = REPO_ROOT / "digests"
    index_path = digests_dir / "README.md"

    digest_files = sorted(
        [f.stem for f in digests_dir.glob("*.md") if f.stem != "README"],
        reverse=True,
    )

    lines = ["# Argus Digest Archive\n", "| Date | Link |\n", "|------|------|\n"]
    for d in digest_files:
        lines.append(f"| {d} | [{d}](./{d}.md) |\n")

    index_path.write_text("".join(lines), encoding="utf-8")
