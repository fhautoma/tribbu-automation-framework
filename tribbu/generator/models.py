"""Pydantic models for JSONL action entries."""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, field_validator

_SNAKE_RE = re.compile(r"[^a-zA-Z0-9]+")


def _to_snake(text: str) -> str:
    text = _SNAKE_RE.sub("_", text)
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", text)
    text = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", text)
    return re.sub(r"_+", "_", text).lower().strip("_")


def _key_from_locator(loc: Locator) -> str:
    value = loc.value
    if loc.strategy == "id" and "/" in value:
        value = value.split("/")[-1]
    return _to_snake(value)


class Locator(BaseModel):
    strategy: str
    value: str


class ActionEntry(BaseModel):
    """One line of a JSONL recording produced by Appium Inspector."""

    ts: str
    action: str
    platform: Optional[str] = None
    screen: Optional[str] = None
    locator: Optional[Locator] = None
    locators: Optional[list[Locator]] = None  # all available locators for this element
    value: Optional[str] = None
    context: Optional[str] = None
    key: Optional[str] = None     # semantic locator key override (e.g. "otp_field")
    method: Optional[str] = None  # semantic method name override (e.g. "fill_phone_number")

    @field_validator("platform", mode="before")
    @classmethod
    def normalise_platform(cls, v: object) -> object:
        return v.lower() if isinstance(v, str) else v

    @field_validator("action", mode="before")
    @classmethod
    def normalise_action(cls, v: object) -> object:
        return v.lower() if isinstance(v, str) else v

    # ── Derived helpers ─────────────────────────────────────────────────────

    @property
    def screen_key(self) -> str:
        """Canonical screen identifier (never None)."""
        return self.screen or "UnknownScreen"

    def preferred_locator(self, prefer_strategy: str | None = None) -> Locator | None:
        """Return the best locator for this entry.

        Resolution order:
        1. From ``locators`` list: first one matching *prefer_strategy* (case-insensitive).
        2. From ``locators`` list: first available entry.
        3. Fall back to the single ``locator`` field.

        Args:
            prefer_strategy: Locator strategy name to prefer, e.g. ``"id"``,
                ``"xpath"``, ``"-android uiautomator"``, ``"accessibility id"``.
                Pass ``None`` to use the default (first available / ``locator``).
        """
        candidates = self.locators or []
        if prefer_strategy and candidates:
            preferred = prefer_strategy.lower()
            for loc in candidates:
                if loc.strategy.lower() == preferred:
                    return loc
        if candidates:
            return candidates[0]
        return self.locator

    def locator_key_for(self, prefer_strategy: str | None = None) -> str | None:
        """Snake-cased locator key derived from :meth:`preferred_locator`.

        If a ``key`` override is present in the entry it takes precedence over
        the auto-derived name.  Android resource IDs like
        ``com.example:id/login_button`` are reduced to just ``login_button``
        so both platforms share the same method names.
        """
        if self.key:
            return self.key
        loc = self.preferred_locator(prefer_strategy)
        if not loc:
            return None
        return _key_from_locator(loc)

    @property
    def locator_key(self) -> str | None:
        """Backward-compatible key — always uses the raw ``locator`` field."""
        return self.locator_key_for(prefer_strategy=None)
