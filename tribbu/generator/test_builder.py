"""Builds TestFileSpec data structures from ActionEntries + PageSpecs.

Template variables in JSONL values (e.g. ``${TEST_EMAIL}``) are automatically
converted to ``test_data["TEST_EMAIL"]`` references so the generated test
receives a ``test_data`` fixture when needed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from tribbu.generator.models import ActionEntry
from tribbu.generator.page_builder import PageSpec, to_pascal, to_snake, parse_must_equal

_TMPL_VAR_RE = re.compile(r"\$\{(\w+)\}")
_API_CALL_RE = re.compile(r'Call using (GET|POST)\s+(https?://\S+)', re.IGNORECASE)


def _resolve_value(raw: str) -> str:
    """Turn ``${VAR}`` → ``test_data["VAR"]``."""
    return _TMPL_VAR_RE.sub(r'test_data["\1"]', raw)


def _needs_test_data(entries: list[ActionEntry]) -> bool:
    return any(
        entry.value and _TMPL_VAR_RE.search(entry.value) for entry in entries
    )


def _parse_api_call(context: str | None) -> tuple[str, str] | None:
    """Return (method, url) if context contains 'Call using GET/POST <url>'."""
    if not context:
        return None
    m = _API_CALL_RE.search(context)
    return (m.group(1).upper(), m.group(2)) if m else None


_RANDOM_DATA_MAP = [
    (re.compile(r'random\s+last[\s_-]?name', re.IGNORECASE), 'fake.last_name()'),
    (re.compile(r'random\s+name', re.IGNORECASE),            'fake.first_name()'),
    (re.compile(r'random\s+email', re.IGNORECASE),           'fake.email()'),
    (re.compile(r'random\s+phone', re.IGNORECASE),           'fake.numerify("6########")'),
]


def _parse_random_data(context: str | None) -> str | None:
    """Return a faker expression if context describes random data generation."""
    if not context:
        return None
    for pattern, faker_call in _RANDOM_DATA_MAP:
        if pattern.search(context):
            return faker_call
    return None


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class StepSpec:
    call: str  # e.g.  "page.tap_login_button()"


@dataclass
class TestSpec:
    name: str           # e.g.  "test_login_flow"
    page_class: str     # e.g.  "LoginPage"
    steps: list[StepSpec] = field(default_factory=list)
    needs_test_data: bool = False


@dataclass
class TestFileSpec:
    suite_name: str
    class_name: str          # e.g.  "TestNavigationTest"
    page_imports: list[str]  # one import line per unique screen
    needs_requests: bool = False
    needs_faker: bool = False
    tests: list[TestSpec] = field(default_factory=list)


# ── Step builders (Strategy Pattern) ─────────────────────────────────────────

def _step_for(entry: ActionEntry, prefer_strategy: str | None = None) -> StepSpec | None:
    action = entry.action
    if action == "hide_keyboard":
        return StepSpec(call="page.hide_keyboard()")
    key = entry.locator_key_for(prefer_strategy)
    m = entry.method  # explicit method name override from JSONL

    if action == "tap":
        name = m or f"tap_{key}"
        return StepSpec(call=f"page.{name}()")

    if action == "send_keys":
        name = m or f"enter_{key}"
        if entry.value:
            faker_expr = _parse_random_data(entry.context)
            if faker_expr:
                value_expr = faker_expr
            else:
                resolved = _resolve_value(entry.value)
                value_expr = resolved if "test_data[" in resolved else f'"{resolved.strip()}"'
        else:
            value_expr = '""'
        return StepSpec(call=f"page.{name}({value_expr})")

    if action == "clear":
        name = m or f"clear_{key}"
        return StepSpec(call=f"page.{name}()")

    if action == "assert_visible":
        expected = parse_must_equal(entry.context)
        if m:
            return StepSpec(call=f"page.{m}()")
        if expected:
            return StepSpec(call=f"page.assert_{key}_equals_{to_snake(expected)}()")
        return StepSpec(call=f"page.assert_{key}_visible()")

    if action == "long_press":
        name = m or f"long_press_{key}"
        return StepSpec(call=f"page.{name}()")

    return None  # unknown action — skip


# ── Public builder ────────────────────────────────────────────────────────────

def build_full_test_spec(
    suite_name: str,
    all_entries: list[ActionEntry],
    page_specs: dict[str, PageSpec],
    prefer_strategy: str | None = None,
) -> TestFileSpec:
    """Build a single :class:`TestFileSpec` for an entire JSONL recording.

    Generates one test method with all steps in order. When the screen
    changes, a new page object is instantiated inline (``page = XxxPage(driver)``).

    Args:
        suite_name: Name of the test suite (used for class/method names).
        all_entries: All parsed action entries in recording order.
        page_specs: Mapping of screen name → :class:`PageSpec`.
        prefer_strategy: Locator strategy to prefer for all steps, e.g.
            ``"id"``, ``"xpath"``, ``"-android uiautomator"``.
            Passed down to :func:`_step_for` and applied via
            :meth:`~tribbu.generator.models.ActionEntry.locator_key_for`.
    """
    # Collect unique page imports preserving first-appearance order
    seen_screens: set[str] = set()
    page_imports: list[str] = []
    for entry in all_entries:
        screen = entry.screen_key
        if screen not in seen_screens and screen in page_specs:
            seen_screens.add(screen)
            snake = to_snake(screen)
            cls = page_specs[screen].class_name
            page_imports.append(f"from tests.generated.pages.{snake}_page import {cls}")

    use_test_data = _needs_test_data(all_entries)
    needs_requests = any(_parse_api_call(e.context) for e in all_entries)
    needs_faker = any(_parse_random_data(e.context) for e in all_entries)

    # Build steps in recording order; re-instantiate page when screen changes
    steps: list[StepSpec] = []
    current_screen: str | None = None
    for entry in all_entries:
        if not entry.preferred_locator(prefer_strategy) and entry.action != "hide_keyboard":
            continue
        screen = entry.screen_key
        if screen != current_screen:
            current_screen = screen
            if screen in page_specs:
                cls = page_specs[screen].class_name
                steps.append(StepSpec(call=f"page = {cls}(driver)"))

        # Inject API call step before send_keys when context specifies it
        if entry.action == "send_keys" and entry.value:
            var_match = _TMPL_VAR_RE.search(entry.value)
            api = _parse_api_call(entry.context)
            if var_match and api:
                var_name = var_match.group(1)
                method, url = api
                steps.append(StepSpec(
                    call=f'test_data["{var_name}"] = requests.{method.lower()}("{url}").json()[0]'
                ))

        step = _step_for(entry, prefer_strategy)
        if step:
            steps.append(step)

    file_spec = TestFileSpec(
        suite_name=suite_name,
        class_name=f"Test{to_pascal(suite_name)}",
        page_imports=page_imports,
        needs_requests=needs_requests,
        needs_faker=needs_faker,
    )
    file_spec.tests.append(
        TestSpec(
            name=f"test_{to_snake(suite_name)}",
            page_class="",
            steps=steps,
            needs_test_data=use_test_data,
        )
    )
    return file_spec
