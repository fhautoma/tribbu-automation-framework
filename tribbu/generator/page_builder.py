"""Builds PageSpec data structures from a list of ActionEntry objects.

Design:
  - One PageSpec per unique screen name.
  - Each PageSpec accumulates locators per platform and one method per
    (action, locator_key) pair — duplicates are merged automatically.
  - The Strategy Pattern is applied when mapping action names to method bodies:
    each action type has its own handler in ``_METHOD_BUILDERS``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from tribbu.generator.models import ActionEntry


# ── Naming utilities ──────────────────────────────────────────────────────────

def to_snake(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]", "_", text)
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", text)
    text = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", text)
    return re.sub(r"_+", "_", text).lower().strip("_")


def to_pascal(text: str) -> str:
    return "".join(word.capitalize() for word in to_snake(text).split("_") if word)


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class MethodSpec:
    """A single method to be rendered inside a Page Object class."""

    name: str
    signature: str           # e.g.  "def tap_login_button(self) -> None:"
    body: str                # e.g.  'self.tap("login_button")'
    has_value_param: bool = False


@dataclass
class PageSpec:
    """All the data needed to render one Page Object file."""

    screen_name: str
    class_name: str
    # platform → { locator_key → (strategy, value) }
    platforms: dict[str, dict[str, tuple[str, str]]] = field(default_factory=dict)
    methods: list[MethodSpec] = field(default_factory=list)

    def add_locator(
        self, platform: str, key: str, strategy: str, value: str
    ) -> None:
        self.platforms.setdefault(platform, {})[key] = (strategy, value)

    def add_method(self, method: MethodSpec) -> None:
        """Idempotent — ignores duplicate method names."""
        if not any(m.name == method.name for m in self.methods):
            self.methods.append(method)


# ── Strategy Pattern: action → method builder ─────────────────────────────────

_MethodBuilder = Callable[[str], MethodSpec]


def _build_tap(key: str) -> MethodSpec:
    name = f"tap_{key}"
    return MethodSpec(
        name=name,
        signature=f"def {name}(self) -> None:",
        body=f'self.tap("{key}")',
    )


def _build_send_keys(key: str, hide_keyboard: bool = True) -> MethodSpec:
    name = f"enter_{key}"
    body = f'self.send_keys("{key}", value)' if hide_keyboard else f'self.send_keys("{key}", value, hide_keyboard=False)'
    return MethodSpec(
        name=name,
        signature=f"def {name}(self, value: str) -> None:",
        body=body,
        has_value_param=True,
    )


def _build_clear(key: str) -> MethodSpec:
    name = f"clear_{key}"
    return MethodSpec(
        name=name,
        signature=f"def {name}(self) -> None:",
        body=f'self.clear("{key}")',
    )


def _build_assert_visible(key: str) -> MethodSpec:
    name = f"assert_{key}_visible"
    return MethodSpec(
        name=name,
        signature=f"def {name}(self) -> None:",
        body=f'self.assert_visible("{key}")',
    )


def _build_long_press(key: str) -> MethodSpec:
    name = f"long_press_{key}"
    return MethodSpec(
        name=name,
        signature=f"def {name}(self) -> None:",
        body=f'self.long_press("{key}")',
    )


_METHOD_BUILDERS: dict[str, _MethodBuilder] = {
    "tap": _build_tap,
    "send_keys": _build_send_keys,
    "clear": _build_clear,
    "assert_visible": _build_assert_visible,
    "long_press": _build_long_press,
}

# Actions we skip (no page method generated for these)
_SKIP_ACTIONS = frozenset({"execute_script"})

_MUST_EQUAL_RE = re.compile(r'must equal(?:\s+to)?\s+["\'](.+)["\']', re.IGNORECASE)


def parse_must_equal(context: Optional[str]) -> Optional[str]:
    """Extract expected value from context like 'must equal \"Success\"'."""
    if not context:
        return None
    m = _MUST_EQUAL_RE.search(context)
    return m.group(1) if m else None

# Actions that require no locator
_NO_LOCATOR_ACTIONS = frozenset({"hide_keyboard"})


def _build_method(action: str, locator_key: str) -> MethodSpec | None:
    builder = _METHOD_BUILDERS.get(action)
    if builder is None:
        return None
    return builder(locator_key)


# ── Public builder ────────────────────────────────────────────────────────────

def build_page_specs(
    entries: list[ActionEntry],
    prefer_strategy: str | None = None,
) -> dict[str, PageSpec]:
    """Group *entries* by screen and return one :class:`PageSpec` per screen.

    When the same flow is recorded on multiple platforms (iOS + Android),
    pass all entries together — locators are grouped by the ``platform``
    field on each entry.

    Args:
        entries: All parsed action entries.
        prefer_strategy: Locator strategy to prefer when an entry exposes
            multiple locators (``locators`` list).  E.g. ``"id"``,
            ``"xpath"``, ``"-android uiautomator"``, ``"accessibility id"``.
            When ``None`` the first available locator is used (original
            behaviour).
    """
    specs: dict[str, PageSpec] = {}

    for entry in entries:
        screen = entry.screen_key

        if screen not in specs:
            specs[screen] = PageSpec(
                screen_name=screen,
                class_name=f"{to_pascal(screen)}Page",
            )

        spec = specs[screen]

        if entry.action in _NO_LOCATOR_ACTIONS:
            spec.add_method(MethodSpec(
                name="hide_keyboard",
                signature="def hide_keyboard(self) -> None:",
                body="self.hide_keyboard()",
            ))
        elif entry.preferred_locator(prefer_strategy):
            loc = entry.preferred_locator(prefer_strategy)
            key = entry.locator_key_for(prefer_strategy)
            platform = entry.platform or "unknown"
            spec.add_locator(platform, key, loc.strategy, loc.value)

            if entry.action not in _SKIP_ACTIONS:
                expected = parse_must_equal(entry.context)
                if entry.action == "assert_visible" and expected:
                    method = MethodSpec(
                        name=f"assert_{key}_equals_{to_snake(expected)}",
                        signature=f"def assert_{key}_equals_{to_snake(expected)}(self) -> None:",
                        body=f'self.assert_text("{key}", "{expected}")',
                    )
                elif entry.action == "send_keys":
                    no_hide = bool(entry.context and "no_hide_keyboard" in entry.context.lower())
                    method = _build_send_keys(key, hide_keyboard=not no_hide)
                else:
                    method = _build_method(entry.action, key)
                if method and entry.method:
                    sig_rest = method.signature[method.signature.index("("):]
                    method = MethodSpec(
                        name=entry.method,
                        signature=f"def {entry.method}{sig_rest}",
                        body=method.body,
                        has_value_param=method.has_value_param,
                    )
                if method:
                    spec.add_method(method)

    return specs
