"""Factory that creates an Appium WebDriver for iOS or Android."""
from __future__ import annotations

from typing import Any

from appium import webdriver
from appium.options.common.base import AppiumOptions

from tribbu.utils.logger import get_logger

logger = get_logger(__name__)

SUPPORTED_PLATFORMS = frozenset({"ios", "android"})


class DriverFactory:
    """Factory Pattern: centralises driver creation for all platforms.

    Usage::

        driver = DriverFactory.create(
            platform="ios",
            capabilities={...},
            server_url="http://localhost:4723",
        )
    """

    @staticmethod
    def create(
        platform: str,
        capabilities: dict[str, Any],
        server_url: str = "http://localhost:4723",
    ) -> webdriver.Remote:
        platform = platform.lower()
        if platform not in SUPPORTED_PLATFORMS:
            raise ValueError(
                f"Unsupported platform '{platform}'. "
                f"Choose from: {sorted(SUPPORTED_PLATFORMS)}"
            )

        options = AppiumOptions()
        options.load_capabilities(capabilities)

        logger.info("Creating %s driver → %s", platform, server_url)
        driver = webdriver.Remote(server_url, options=options)
        driver.implicitly_wait(10)
        logger.info("Driver ready. Session: %s", driver.session_id)
        return driver
