"""JSONL file parser — converts raw recordings into ActionEntry objects."""
from __future__ import annotations

import json
from pathlib import Path

from tribbu.generator.models import ActionEntry

# Actions produced by the recorder internals that carry no test-relevant info
_SKIP_ACTIONS = frozenset({"findandassign"})


def parse_jsonl(path: str | Path) -> list[ActionEntry]:
    """Parse a JSONL recording file and return a list of :class:`ActionEntry`.

    Args:
        path: Path to the ``.jsonl`` file produced by Appium Inspector.

    Returns:
        Ordered list of parsed action entries (internal actions filtered out).

    Raises:
        FileNotFoundError: If *path* does not exist.
        ValueError: If any line cannot be parsed as a valid ActionEntry.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Recording not found: {path}")

    entries: list[ActionEntry] = []
    with path.open(encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                entry = ActionEntry.model_validate(data)
            except Exception as exc:
                raise ValueError(
                    f"Invalid JSONL at {path}:{lineno} — {exc}"
                ) from exc

            if entry.action.lower() in _SKIP_ACTIONS:
                continue
            entries.append(entry)

    return entries
