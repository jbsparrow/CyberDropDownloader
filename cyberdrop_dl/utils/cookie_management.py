from __future__ import annotations

import os
from collections.abc import Callable
from functools import wraps
from http.cookiejar import CookieJar, MozillaCookieJar
from textwrap import dedent
from typing import TYPE_CHECKING, TypeAlias

import browser_cookie3

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.constants import BROWSERS

CookieExtractor: TypeAlias = Callable[..., CookieJar]
COOKIE_EXTRACTORS: dict[str, CookieExtractor] = {func.__name__: func for func in browser_cookie3.all_browsers}
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
    manager: Manager, *, browsers: list[BROWSERS] | list[str] | None = None, domains: list[str] | None = None
) -> set[str]:
    """Extract cookies from browsers.

    :param browsers: list of browsers to extract from. If `None`, config `browser_cookies.browsers` will be used
    :param domains: list of domains to filter cookies. If `None`, config `browser_cookies.sites` will be used
    :return: A set with all the domains that actually had cookies
    :raises ValueError: If `browsers` or `domains` are empty lists
    :raises UnsupportedBrowserError: If there was a decrypt error while extracting cookies from a chromium browser
    and the current OS is Windows
    :raises BrowserCookieError: For any other kind of error while extracting cookies"""
    if browsers == []:
        msg = "No browser selected"
        raise ValueError(msg)
    if domains == []:
        msg = "No domains selected"
        raise ValueError(msg)

    browsers_to_extract_from = browsers or manager.config_manager.settings_data.browser_cookies.browsers
    extractors_to_use = list(map(str.lower, browsers_to_extract_from))
    domains_to_extract: list[str] = domains or manager.config_manager.settings_data.browser_cookies.sites

    def extract_cookies():
        for name, extractor in COOKIE_EXTRACTORS.items():
            if name not in extractors_to_use:
                continue
            try:
                yield name, extractor()
            except browser_cookie3.BrowserCookieError as e:
                check_unsupported_browser(e, name)
                raise

    extracted_cookies = [cookies_jar for _, cookies_jar in extract_cookies()]
    if not extracted_cookies:
        msg = "None of the provided browsers is supported for extraction"
        raise ValueError(msg)

    manager.path_manager.cookies_dir.mkdir(parents=True, exist_ok=True)
    domains_with_cookies: set[str] = set()
    for domain in domains_to_extract:
        cookie_file_path = manager.path_manager.cookies_dir / f"{domain}.txt"
        cdl_cookie_jar = MozillaCookieJar(cookie_file_path)
        for cookie_jar in extracted_cookies:
            for cookie in cookie_jar:
                if domain in cookie.domain:
                    domains_with_cookies.add(domain)
                    cdl_cookie_jar.set_cookie(cookie)

        if domain in domains_with_cookies:
            cdl_cookie_jar.save(ignore_discard=True, ignore_expires=True)

    return domains_with_cookies


def clear_cookies(manager: Manager, domains: list[str]) -> None:
    if not domains:
        raise ValueError("No domains selected")

    manager.path_manager.cookies_dir.mkdir(parents=True, exist_ok=True)
    for domain in domains:
        cookie_file_path = manager.path_manager.cookies_dir / f"{domain}.txt"
        cookie_jar = MozillaCookieJar(cookie_file_path)
        cookie_jar.save(ignore_discard=True, ignore_expires=True)


def check_unsupported_browser(error: browser_cookie3.BrowserCookieError, extractor_name: str) -> None:
    msg = str(error)
    if is_decrypt_error(msg) and extractor_name in CHROMIUM_BROWSERS and os.name == "nt":
        msg = f"Cookie extraction from {extractor_name.capitalize()} is not supported on Windows - {msg}"
        raise UnsupportedBrowserError(msg)


def is_decrypt_error(error_as_str: str) -> bool:
    return "Unable to get key for cookie decryption" in error_as_str
