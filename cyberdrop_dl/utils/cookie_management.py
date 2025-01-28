from __future__ import annotations

import contextlib
from functools import wraps
from http.cookiejar import MozillaCookieJar
from textwrap import dedent
from typing import TYPE_CHECKING

import browser_cookie3
from rich.console import Console

from cyberdrop_dl.utils.data_enums_classes.supported_domains import SUPPORTED_FORUMS

if TYPE_CHECKING:
    from collections.abc import Callable
    from http.cookiejar import CookieJar

    from cyberdrop_dl.managers.manager import Manager

console = Console()
COOKIE_ERROR_FOOTER = "\n\nNothing has been saved."


class UnsupportedBrowserError(browser_cookie3.BrowserCookieError): ...


def cookie_wrapper(func: Callable) -> Callable:
    """Wrapper handles errors for cookie extraction."""

    @wraps(func)
    def wrapper(*args, **kwargs) -> None:
        msg = ""
        try:
            return func(*args, **kwargs)
        except PermissionError:
            msg = """
            We've encountered a Permissions Error. Please close all browsers and try again
            If you are still having issues, make sure all browsers processes are closed in Task Manager
            """
            msg = dedent(msg)

        except ValueError as e:
            msg = str(e)

        except UnsupportedBrowserError as e:
            msg = "Cookie extraction from Chrome is not supported on Windows"
            msg = dedent(msg) + f"\nERROR: {e!s}"

        except browser_cookie3.BrowserCookieError as e:
            msg = """
            Browser extraction ran into an error, the selected browser(s) may not be available on your system
            If you are still having issues, make sure all browsers processes are closed in Task Manager.
            """

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
    domains: list[str] = domains or manager.config_manager.settings_data.browser_cookies.sites
    extractors = [getattr(browser_cookie3, b) for b in browsers if hasattr(browser_cookie3, b)]

    if not extractors:
        msg = "None of the provided browsers is supported for extraction"
        raise ValueError(msg)

    for domain in domains:
        cookie_jar = MozillaCookieJar()
        for extractor in extractors:
            try:
                cookies = extractor(domain_name=domain)
            except browser_cookie3.BrowserCookieError as e:
                if "Unable to get key for cookie decryption" in str(e) and extractor == "chrome":
                    raise UnsupportedBrowserError(str(e)) from None
                raise
            for cookie in cookies:
                cookie_jar.set_cookie(cookie)
            manager.path_manager.cookies_dir.mkdir(parents=True, exist_ok=True)
            cookie_file_path = manager.path_manager.cookies_dir / f"{domain}.txt"
            update_forum_config_cookies(manager, domain, cookies)
        cookie_jar.save(cookie_file_path, ignore_discard=True, ignore_expires=True)


def update_forum_config_cookies(manager: Manager, forum: str, cookie: CookieJar) -> None:
    if forum not in SUPPORTED_FORUMS:
        return
    auth_args = manager.config_manager.authentication_data
    forum_domain = SUPPORTED_FORUMS[forum]
    forum_dict = auth_args.forums.model_dump()
    with contextlib.suppress(KeyError):
        forum_dict[f"{forum}_xf_user_cookie"] = cookie._cookies[forum_domain]["/"]["xf_user"].value
        forum_dict[f"{forum}_xf_user_cookie"] = cookie._cookies["www." + forum_domain]["/"]["xf_user"].value
    auth_args.forums = auth_args.forums.model_copy(update=forum_dict)


def clear_cookies(manager: Manager, domains: list[str] | None = None) -> None:
    if not domains and domains is not None:
        raise ValueError("No domains selected")

    for domain in domains:
        cookie_jar = MozillaCookieJar()
        manager.path_manager.cookies_dir.mkdir(parents=True, exist_ok=True)
        cookie_file_path = manager.path_manager.cookies_dir / f"{domain}.txt"
        cookie_jar.save(cookie_file_path, ignore_discard=True, ignore_expires=True)
