"""CLI entry point for the Tribbu code generator.

Usage examples::

    # Single platform
    tribbu generate --ios recordings/login.jsonl --name login

    # Both platforms (locators merged per screen)
    tribbu generate --ios  recordings/login_ios.jsonl \\
                   --android recordings/login_android.jsonl \\
                   --name login

    # Custom output directory
    tribbu generate --ios recordings/login.jsonl --name login \\
                   --output tests/generated

    # Prefer a specific locator strategy for all generated elements
    tribbu generate --android recordings/login_android.jsonl --name login \\
                   --prefer-strategy id

    tribbu generate --android recordings/onboarding.jsonl --name onboarding \\
                   --prefer-strategy xpath
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from collections import defaultdict

import click

from tribbu.generator.jsonl_parser import parse_jsonl
from tribbu.generator.page_builder import build_page_specs, to_snake
from tribbu.generator.renderer import render_page, render_test
from tribbu.generator.test_builder import build_full_test_spec
from tribbu.utils.logger import get_logger

logger = get_logger(__name__)


@click.group()
def main() -> None:
    """Tribbu — Mobile test automation generator."""


@main.command()
@click.option("--ios", "ios_path", type=click.Path(), default=None, help="iOS JSONL recording")
@click.option(
    "--android", "android_path", type=click.Path(), default=None, help="Android JSONL recording"
)
@click.option("--name", required=True, help="Test suite name, e.g. login")
@click.option(
    "--output",
    default="tests/generated",
    show_default=True,
    help="Root output directory",
)
@click.option(
    "--prefer-strategy",
    "prefer_strategy",
    default=None,
    help=(
        "Preferred locator strategy when an entry exposes multiple locators. "
        "E.g.: id, xpath, accessibility id, -android uiautomator. "
        "When omitted the first available locator is used."
    ),
)
def generate(
    ios_path: str | None,
    android_path: str | None,
    name: str,
    output: str,
    prefer_strategy: str | None,
) -> None:
    """Generate Page Objects and test files from JSONL recordings."""
    if not ios_path and not android_path:
        raise click.UsageError("Provide at least one JSONL file via --ios or --android.")

    # ── Parse recordings ──────────────────────────────────────────────────
    all_entries = []
    if ios_path:
        click.echo(f"  Parsing iOS  recording: {ios_path}")
        all_entries.extend(parse_jsonl(ios_path))
    if android_path:
        click.echo(f"  Parsing Android recording: {android_path}")
        all_entries.extend(parse_jsonl(android_path))

    click.echo(f"  Total entries: {len(all_entries)}")
    if prefer_strategy:
        click.echo(f"  Preferred locator strategy: {prefer_strategy}")

    # ── Build specs ───────────────────────────────────────────────────────
    page_specs = build_page_specs(all_entries, prefer_strategy=prefer_strategy)
    if not page_specs:
        click.echo("No actionable entries found — nothing generated.")
        return

    # Group entries per screen for test building
    entries_by_screen: dict[str, list] = defaultdict(list)
    for entry in all_entries:
        entries_by_screen[entry.screen_key].append(entry)

    # ── Write files ───────────────────────────────────────────────────────
    output_dir = Path(output)
    pages_dir = output_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    # Ensure __init__.py files exist
    for d in (output_dir, pages_dir):
        init = d / "__init__.py"
        if not init.exists():
            init.write_text("")

    click.echo(f"\n  Generating into {output_dir}/\n")

    # One Page Object per screen
    for screen_name, page_spec in page_specs.items():
        snake = to_snake(screen_name)
        page_code = render_page(page_spec)
        page_file = pages_dir / f"{snake}_page.py"
        page_file.write_text(page_code, encoding="utf-8")
        click.echo(f"  [page]  {page_file}")

    # One test file for the entire JSONL
    test_spec = build_full_test_spec(name, all_entries, page_specs, prefer_strategy=prefer_strategy)
    test_code = render_test(test_spec)
    test_file = output_dir / f"test_{to_snake(name)}.py"
    test_file.write_text(test_code, encoding="utf-8")
    click.echo(f"  [test]  {test_file}")

    click.echo(
        f"\n  Done — {len(page_specs)} screen(s) generated."
        f" Run with:\n\n"
        f"    pytest {output_dir}/ --platform ios\n"
    )


@main.command()
@click.option(
    "--platform",
    default="android",
    show_default=True,
    type=click.Choice(["ios", "android"]),
    help="Target platform",
)
@click.option(
    "--config",
    default=None,
    help="Path to capabilities YAML (auto-detected from platform if not set)",
)
@click.option(
    "--tests-dir",
    "tests_dir",
    default="tests/generated",
    show_default=True,
    help="Directory where generated test files live",
)
@click.option(
    "--results-dir",
    "results_dir",
    default="reports/allure-results",
    show_default=True,
    help="Directory for raw Allure results",
)
@click.option(
    "--report-dir",
    "report_dir",
    default="reports/allure-report",
    show_default=True,
    help="Directory for the generated HTML report",
)
@click.option(
    "--test",
    "test_name",
    default=None,
    help="Run a specific test file by name, e.g. onboarding_test (without test_ prefix or .py)",
)
@click.option(
    "--no-open",
    "no_open",
    is_flag=True,
    default=False,
    help="Skip opening the report in the browser",
)
def run(
    platform: str,
    config: str | None,
    tests_dir: str,
    results_dir: str,
    report_dir: str,
    test_name: str | None,
    no_open: bool,
) -> None:
    """Run all generated tests, build an Allure report and open it."""

    # ── Discover test files ───────────────────────────────────────────────
    tests_path = Path(tests_dir)
    if test_name:
        target = tests_path / f"test_{test_name}.py"
        if not target.exists():
            available = [f.stem[5:] for f in sorted(tests_path.glob("test_*.py"))]
            raise click.ClickException(
                f"Test '{test_name}' not found.\n"
                f"Available: {', '.join(available) or 'none'}"
            )
        test_files = [target]
    else:
        test_files = sorted(tests_path.glob("test_*.py"))
    if not test_files:
        raise click.ClickException(f"No test files found in '{tests_dir}'.")

    click.echo(f"\n  Platform  : {platform}")
    click.echo(f"  Tests dir : {tests_dir}")
    click.echo(f"  Found     : {len(test_files)} test file(s)")
    for f in test_files:
        click.echo(f"    · {f.name}")

    # ── Resolve capabilities config ───────────────────────────────────────
    config_path = config or f"config/capabilities/{platform}.yaml"
    if not Path(config_path).exists():
        raise click.ClickException(
            f"Capabilities file not found: {config_path}\n"
            f"Pass --config <path> to override."
        )

    # ── Clean previous raw results ────────────────────────────────────────
    results_path = Path(results_dir)
    if results_path.exists():
        import shutil
        shutil.rmtree(results_path)
    results_path.mkdir(parents=True)

    # ── Run pytest ────────────────────────────────────────────────────────
    click.echo(f"\n  Running tests...\n")
    pytest_cmd = [
        sys.executable, "-m", "pytest",
        *[str(f) for f in test_files],
        "--platform", platform,
        "--config", config_path,
        f"--alluredir={results_dir}",
        "-v",
    ]
    result = subprocess.run(pytest_cmd)
    exit_code = result.returncode

    # ── Generate Allure HTML report ───────────────────────────────────────
    click.echo("\n  Generating Allure report...")
    report_path = Path(report_dir)
    if report_path.exists():
        import shutil
        shutil.rmtree(report_path)

    gen_result = subprocess.run(
        ["allure", "generate", results_dir, "--output", report_dir, "--clean"],
        capture_output=True,
        text=True,
    )
    if gen_result.returncode != 0:
        click.echo(f"  [warn] allure generate failed: {gen_result.stderr.strip()}")
        click.echo("  Make sure Allure CLI is installed: brew install allure")
    else:
        click.echo(f"  Report saved → {report_dir}/index.html")
        if not no_open:
            click.echo("  Opening report in browser...")
            subprocess.run(["allure", "open", report_dir])

    # ── Exit with pytest's code so CI picks up failures ──────────────────
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
