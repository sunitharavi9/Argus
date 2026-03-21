"""Abstract base class for all fetchers."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod

from argus.pipeline.models import RawItem


class BaseFetcher(ABC):
    """Every fetcher must implement fetch() and return a list of RawItem."""

    source_name: str = ""

    @abstractmethod
    async def fetch(self) -> list[RawItem]:
        """Fetch items from the source and return them as RawItem list."""
        ...

    @staticmethod
    def make_id(source: str, url: str) -> str:
        """Generate a stable dedup ID from source + URL."""
        h = hashlib.sha256(url.encode()).hexdigest()[:16]
        return f"{source}:{h}"
