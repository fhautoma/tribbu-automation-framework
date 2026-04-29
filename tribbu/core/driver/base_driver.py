"""Abstract base for platform-specific driver configuration."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseDriverConfig(ABC):
    """Contract for platform capability builders."""

    @abstractmethod
    def build_capabilities(self, raw_caps: dict[str, Any]) -> dict[str, Any]:
        """Validate and enrich raw capabilities for the target platform."""
        ...
