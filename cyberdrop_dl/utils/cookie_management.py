from __future__ import annotations

import os
from functools import wraps
from http.cookiejar import CookieJar, MozillaCookieJar
from textwrap import dedent
from typing import TYPE_CHECKING, NamedTuple, ParamSpec, TypeVar

import browser_cookie3

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from cyberdrop_dl.constants import BROWSERS
    from cyberdrop_dl.managers.manager import Manager

P = ParamSpec("P")
R = TypeVar("R")


class CookieExtractor(NamedTuple):
    name: str
    extract: Callable[..., CookieJar]


class UnsupportedBrowserError(browser_cookie3.BrowserCookieError): ...


COOKIE_EXTRACTORS = [CookieExtractor(func.__name__, func) for func in browser_cookie3.all_browsers]
COOKIE_ERROR_FOOTER = "\n\nNothing has been saved."
CHROMIUM_BROWSERS = ["chrome", "chromium", "opera", "opera_gx", "brave", "edge", "vivaldi", "arc"]


def cookie_wrapper(func: Callable[P, R]) -> Callable[P, R]:
    """Wrapper handles errors for cookie extraction."""

    @wraps(func)
    def wrapper(*args, **kwargs) -> R:
        try:
            return func(*args, **kwargs)
        except PermissionError as e:
            msg = """We've encountered a Permissions Error. Please close all browsers and try again
                     If you are still having issues, make sure all browsers processes are closed in Task Manager"""
            msg = f"{dedent(msg)}\nERROR: {e!s}"

        except (ValueError, UnsupportedBrowserError) as e:
            msg = f"ERROR: {e!s}"

        except browser_cookie3.BrowserCookieError as e:
            msg = """Browser extraction ran into an error, the selected browser(s) may not be available on your system
                     If you are still having issues, make sure all browsers processes are closed in Task Manager."""
            msg = f"{dedent(msg)}\nERROR: {e!s}"

        raise browser_cookie3.BrowserCookieError(f"{msg}{COOKIE_ERROR_FOOTER}")

    return wrapper


@cookie_wrapper
def get_cookies_from_browsers(
    manager: Manager, *, browsers: list[BROWSERS] | list[str] | None = None, domains: list[str] | None = None
) -> set[str]:
    """Extract cookies from browsers.

    :param browsers: list of browsers to extract from. If `None`, config `browser_cookies.browsers` will be used
    :param domains: list of domains to filter cookies. If `None`, config `browser_cookies.sites` will be used
    :return: A set with all the domains that actually had cookies
    :raises BrowserCookieError: If there's any error while extracting cookies"""
    if browsers == []:
        msg = "No browser selected"
        raise ValueError(msg)
    if domains == []:
        msg = "No domains selected"
        raise ValueError(msg)

    browsers_to_extract_from = browsers or manager.config_manager.settings_data.browser_cookies.browsers
    extractors_to_use = list(map(str.lower, browsers_to_extract_from))
    domains_to_extract: list[str] = domains or manager.config_manager.settings_data.browser_cookies.sites

    def is_decrypt_error(msg: str) -> bool:
        return "Unable to get key for cookie decryption" in msg

    def extract_cookies() -> Generator[CookieJar]:
        for extractor in COOKIE_EXTRACTORS:
            if extractor.name not in extractors_to_use:
                continue
            try:
                yield extractor.extract()
            except browser_cookie3.BrowserCookieError as e:
                msg = str(e)
                if is_decrypt_error(msg) and extractor.name in CHROMIUM_BROWSERS and os.name == "nt":
                    msg = f"Cookie extraction from {extractor.name.capitalize()} is not supported on Windows - {msg}"
                    raise UnsupportedBrowserError(msg) from None
                raise

    extracted_cookies = list(extract_cookies())
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
