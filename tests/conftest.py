"""Global pytest fixtures for Tribbu test suites.

Usage::

    pytest tests/ --platform android --config config/capabilities/android.yaml \\
          --alluredir reports/allure-results

    # Open the report:
    allure serve reports/allure-results

Environment variables (loaded from .env)::

    APPIUM_URL        Appium server URL  (default: http://localhost:4723)
    TRIBBU_LOG_LEVEL  Logging level      (default: INFO)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Generator

import pytest
import yaml
from dotenv import load_dotenv

from tribbu.core.driver.driver_factory import DriverFactory

load_dotenv()

# ── CLI options ───────────────────────────────────────────────────────────────


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--platform",
        action="store",
        default="ios",
        choices=["ios", "android"],
        help="Target platform (ios or android)",
    )
    parser.addoption(
        "--config",
        action="store",
        default=None,
        help="Path to capabilities YAML (auto-detected if not set)",
    )


# ── Session-scoped fixtures ───────────────────────────────────────────────────


@pytest.fixture(scope="session")
def platform(request: pytest.FixtureRequest) -> str:
    return request.config.getoption("--platform")


@pytest.fixture(scope="session")
def capabilities(request: pytest.FixtureRequest, platform: str) -> dict:
    config_path = request.config.getoption("--config")
    if not config_path:
        config_path = f"config/capabilities/{platform}.yaml"

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Capabilities file not found: {path}\n"
            f"Create it or pass --config <path>"
        )
    with path.open() as fh:
        return yaml.safe_load(fh)


@pytest.fixture(scope="session")
def driver(platform: str, capabilities: dict) -> Generator:
    appium_url = os.getenv("APPIUM_URL", "http://localhost:4723")
    d = DriverFactory.create(platform, capabilities, appium_url)
    yield d
    d.quit()


# ── Function-scoped fixtures ──────────────────────────────────────────────────


@pytest.fixture
def test_data() -> dict[str, str]:
    """Expose environment variables as a plain dict for parametrised values.

    In JSONL recordings, template variables like ``${TEST_EMAIL}`` are resolved
    to ``test_data["TEST_EMAIL"]`` in generated tests.  Add your values to
    ``.env`` or export them before running pytest.
    """
    return dict(os.environ)


# ── Screenshot on failure ─────────────────────────────────────────────────────


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> Generator:
    """Capture a screenshot whenever a test fails and attach it to Allure."""
    outcome = yield
    report = outcome.get_result()

    if report.when == "call" and report.failed:
        driver = item.funcargs.get("driver")
        if driver is None:
            return

        try:
            png = driver.get_screenshot_as_png()
        except Exception:
            return

        # ── Save to disk (always) ──
        screenshots_dir = Path("reports/screenshots")
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        safe_name = item.nodeid.replace("/", "_").replace("::", "__")
        screenshot_path = screenshots_dir / f"{safe_name}_FAIL.png"
        screenshot_path.write_bytes(png)

        # ── Attach to Allure (when allure-pytest is installed) ──
        try:
            import allure
            allure.attach(
                png,
                name="FAILURE — screenshot",
                attachment_type=allure.attachment_type.PNG,
            )
        except ImportError:
            pass
