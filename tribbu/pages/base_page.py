"""Base Page Object — the single source of all element interactions.

Every generated (and hand-written) page object inherits from this class.
It wraps Appium/Selenium calls behind intention-revealing names and enforces
explicit waits throughout.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import TYPE_CHECKING, Generator

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from tribbu.utils.logger import get_logger

if TYPE_CHECKING:
    from appium.webdriver import WebDriver
    from appium.webdriver.webelement import WebElement

logger = get_logger(__name__)

DEFAULT_TIMEOUT: int = 15
SHORT_TIMEOUT: int = 3
TAP_PAUSE: float = 1.0         # seconds to wait after every tap
TRANSITION_PAUSE: float = 2.0  # seconds to wait after screen-changing taps

# ── Allure integration (optional) ─────────────────────────────────────────────

try:
    import allure as _allure
    _ALLURE = True
except ImportError:
    _allure = None  # type: ignore[assignment]
    _ALLURE = False


@contextmanager
def _step(title: str) -> Generator:
    if _ALLURE:
        with _allure.step(title):
            yield
    else:
        yield


def _screenshot(driver: WebDriver, name: str) -> None:
    """Attach a PNG screenshot to the current Allure step (silent on error)."""
    if not _ALLURE:
        return
    try:
        _allure.attach(
            driver.get_screenshot_as_png(),
            name=name,
            attachment_type=_allure.attachment_type.PNG,
        )
    except Exception:
        pass


# ── Base class ─────────────────────────────────────────────────────────────────

class BasePage:
    """Base for all Page Objects.

    Subclasses declare a ``LOCATORS`` class attribute::

        LOCATORS = {
            "ios": {
                "login_button": ("accessibility id", "login_button"),
            },
            "android": {
                "login_button": ("id", "com.app:id/btn_login"),
            },
        }

    The platform key is resolved automatically from the active driver session.
    """

    LOCATORS: dict[str, dict[str, tuple[str, str]]] = {}

    def __init__(self, driver: WebDriver, timeout: int = DEFAULT_TIMEOUT) -> None:
        self._driver = driver
        self._timeout = timeout
        self._platform: str = driver.capabilities.get("platformName", "").lower()
        self._wait = WebDriverWait(driver, timeout)
        logger.debug(
            "%s initialised — platform='%s'", self.__class__.__name__, self._platform
        )

    # ── Internal helpers ────────────────────────────────────────────────────

    def _resolve(self, name: str) -> tuple[str, str]:
        """Return the (strategy, value) tuple for *name* on the current platform."""
        platform_map = self.LOCATORS.get(self._platform)
        if platform_map is None:
            raise KeyError(
                f"No locators defined for platform '{self._platform}' "
                f"in {self.__class__.__name__}. Available: {list(self.LOCATORS)}"
            )
        locator = platform_map.get(name)
        if locator is None:
            raise KeyError(
                f"Locator '{name}' missing in {self.__class__.__name__} "
                f"[{self._platform}]. Available: {list(platform_map)}"
            )
        return locator

    def _wait_for(self, condition, timeout: int | None = None) -> WebElement:
        wait = WebDriverWait(self._driver, timeout or self._timeout)
        return wait.until(condition)

    # ── Element retrieval ───────────────────────────────────────────────────

    def find(self, locator_name: str) -> WebElement:
        """Wait for element presence and return it."""
        by, value = self._resolve(locator_name)
        logger.debug("find '%s' → (%s, %s)", locator_name, by, value)
        try:
            return self._wait.until(EC.presence_of_element_located((by, value)))
        except TimeoutException:
            raise TimeoutException(
                f"'{locator_name}' ({by}='{value}') not found after {self._timeout}s"
            )

    def find_visible(self, locator_name: str) -> WebElement:
        """Wait for element visibility and return it."""
        by, value = self._resolve(locator_name)
        try:
            return self._wait.until(EC.visibility_of_element_located((by, value)))
        except TimeoutException:
            raise TimeoutException(
                f"'{locator_name}' ({by}='{value}') not visible after {self._timeout}s"
            )

    # ── Actions ─────────────────────────────────────────────────────────────

    def tap(self, locator_name: str, pause: float = TAP_PAUSE) -> None:
        with _step(f"Tap · {locator_name}"):
            logger.info("tap '%s'", locator_name)
            self.find(locator_name).click()
            time.sleep(pause)
            _screenshot(self._driver, f"after tap · {locator_name}")

    def tap_and_wait(self, locator_name: str) -> None:
        """Tap and wait longer — use after actions that trigger screen transitions."""
        self.tap(locator_name, pause=TRANSITION_PAUSE)

    def send_keys(self, locator_name: str, text: str, hide_keyboard: bool = True) -> None:
        with _step(f"Type · {locator_name} = '{text}'"):
            logger.info("send_keys '%s' = '%s'", locator_name, text)
            element = self.find(locator_name)
            element.click()
            time.sleep(0.3)
            element.clear()
            time.sleep(0.3)
            element.send_keys(text)
            if hide_keyboard:
                time.sleep(0.3)
                try:
                    self._driver.hide_keyboard()
                except Exception:
                    pass

    def clear(self, locator_name: str) -> None:
        with _step(f"Clear · {locator_name}"):
            logger.info("clear '%s'", locator_name)
            self.find(locator_name).clear()

    def long_press(self, locator_name: str, duration_ms: int = 1000) -> None:
        from appium.webdriver.common.touch_action import TouchAction  # noqa: PLC0415

        with _step(f"Long press · {locator_name}"):
            logger.info("long_press '%s' for %dms", locator_name, duration_ms)
            element = self.find(locator_name)
            TouchAction(self._driver).long_press(element, duration=duration_ms).release().perform()
            _screenshot(self._driver, f"after long press · {locator_name}")

    def hide_keyboard(self) -> None:
        logger.info("hide_keyboard")
        try:
            self._driver.hide_keyboard()
        except Exception:
            pass  # keyboard may already be hidden

    def get_text(self, locator_name: str) -> str:
        return self.find(locator_name).text

    def scroll_into_view(self, locator_name: str) -> None:
        by, value = self._resolve(locator_name)
        self._driver.execute_script(
            "arguments[0].scrollIntoView(true);",
            self._driver.find_element(by, value),
        )

    # ── Assertions ──────────────────────────────────────────────────────────

    def assert_visible(self, locator_name: str) -> None:
        with _step(f"Assert visible · {locator_name}"):
            logger.info("assert_visible '%s'", locator_name)
            by, value = self._resolve(locator_name)
            try:
                element = self._wait.until(EC.visibility_of_element_located((by, value)))
            except TimeoutException:
                raise AssertionError(
                    f"Element '{locator_name}' ({by}='{value}') "
                    f"not visible after {self._timeout}s"
                )
            assert element.is_displayed(), f"Element '{locator_name}' found but not displayed"
            _screenshot(self._driver, f"assert visible · {locator_name}")

    def assert_text(self, locator_name: str, expected: str) -> None:
        with _step(f"Assert text · {locator_name} = '{expected}'"):
            actual = self.get_text(locator_name)
            assert actual == expected, (
                f"Text mismatch on '{locator_name}': "
                f"expected '{expected}', got '{actual}'"
            )
            _screenshot(self._driver, f"assert text · {locator_name}")

    def assert_text_contains(self, locator_name: str, substring: str) -> None:
        with _step(f"Assert text contains · {locator_name} ⊃ '{substring}'"):
            actual = self.get_text(locator_name)
            assert substring in actual, (
                f"'{locator_name}' text '{actual}' does not contain '{substring}'"
            )

    # ── Soft checks (no assertion error) ────────────────────────────────────

    def is_visible(self, locator_name: str, timeout: int = SHORT_TIMEOUT) -> bool:
        by, value = self._resolve(locator_name)
        try:
            el = WebDriverWait(self._driver, timeout).until(
                EC.visibility_of_element_located((by, value))
            )
            return el.is_displayed()
        except TimeoutException:
            return False
