from __future__ import annotations

import os
from functools import wraps
from http.cookiejar import MozillaCookieJar
from textwrap import dedent
from typing import TYPE_CHECKING

import browser_cookie3
from rich.console import Console

if TYPE_CHECKING:
    from collections.abc import Callable

    from cyberdrop_dl.managers.manager import Manager

console = Console()
COOKIE_ERROR_FOOTER = "\n\nNothing has been saved."
CHROMIUM_BROWSERS = ["chrome", "chromium", "opera", "opera_gx", "brave", "edge", "vivaldi", "arc"]


class UnsupportedBrowserError(browser_cookie3.BrowserCookieError):
    pass


def cookie_wrapper(func: Callable) -> Callable:
    """Wrapper handles errors for cookie extraction."""

    @wraps(func)
    def wrapper(*args, **kwargs) -> None:
        msg = ""
        try:
            return func(*args, **kwargs)
        except PermissionError as e:
            msg = """We've encountered a Permissions Error. Please close all browsers and try again
                     If you are still having issues, make sure all browsers processes are closed in Task Manager"""
            msg = dedent(msg) + f"\nERROR: {e!s}"

        except (ValueError, UnsupportedBrowserError) as e:
            msg = f"ERROR: {e!s}"

        except browser_cookie3.BrowserCookieError as e:
            msg = """Browser extraction ran into an error, the selected browser(s) may not be available on your system
                     If you are still having issues, make sure all browsers processes are closed in Task Manager."""

            msg = dedent(msg) + f"\nERROR: {e!s}"

        raise browser_cookie3.BrowserCookieError(msg + COOKIE_ERROR_FOOTER)

    return wrapper


@cookie_wrapper
def get_cookies_from_browsers(
    manager: Manager, *, browsers: list[str] | None = None, domains: list[str] | None = None
) -> None:
    if not browsers and browsers is not None:
        msg = "No browser selected"
        raise ValueError(msg)
    if not domains and domains is not None:
        msg = "No domains selected"
        raise ValueError(msg)

    browsers = browsers or manager.config_manager.settings_data.browser_cookies.browsers
    browsers = list(map(str.lower, browsers))
    domains: list[str] = domains or manager.config_manager.settings_data.browser_cookies.sites
    extractors = [(str(b), getattr(browser_cookie3, b)) for b in browsers if hasattr(browser_cookie3, b)]

    if not extractors:
        msg = "None of the provided browsers is supported for extraction"
        raise ValueError(msg)

    for domain in domains:
        cookie_jar = MozillaCookieJar()
        for extractor_name, extractor in extractors:
            try:
                cookies = extractor(domain_name=domain)
            except browser_cookie3.BrowserCookieError as e:
                check_unsupported_browser(e, extractor_name)
                raise
            for cookie in cookies:
                cookie_jar.set_cookie(cookie)
            manager.path_manager.cookies_dir.mkdir(parents=True, exist_ok=True)
            cookie_file_path = manager.path_manager.cookies_dir / f"{domain}.txt"
        cookie_jar.save(cookie_file_path, ignore_discard=True, ignore_expires=True)


def clear_cookies(manager: Manager, domains: list[str] | None = None) -> None:
    if not domains and domains is not None:
        raise ValueError("No domains selected")

    for domain in domains:
        cookie_jar = MozillaCookieJar()
        manager.path_manager.cookies_dir.mkdir(parents=True, exist_ok=True)
        cookie_file_path = manager.path_manager.cookies_dir / f"{domain}.txt"
        cookie_jar.save(cookie_file_path, ignore_discard=True, ignore_expires=True)


def check_unsupported_browser(error: browser_cookie3.BrowserCookieError, extractor_name: str) -> None:
    msg = str(error)
    if is_decrypt_error(msg) and extractor_name in CHROMIUM_BROWSERS and os.name == "nt":
        msg = f"Cookie extraction from {extractor_name.capitalize()} is not supported on Windows - {msg}"
        raise UnsupportedBrowserError(msg)


def is_decrypt_error(error_as_str: str) -> bool:
    return "Unable to get key for cookie decryption" in error_as_str
