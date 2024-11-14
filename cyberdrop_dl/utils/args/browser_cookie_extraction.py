from __future__ import annotations

import re
from functools import wraps
from http.cookiejar import MozillaCookieJar
from typing import TYPE_CHECKING

import browser_cookie3
from browser_cookie3 import BrowserCookieError
from InquirerPy import inquirer
from rich.console import Console

from cyberdrop_dl.utils.dataclasses.supported_domains import SupportedDomains

if TYPE_CHECKING:
    from collections.abc import Callable
    from http.cookiejar import CookieJar

    from cyberdrop_dl.managers.manager import Manager


def cookie_wrapper(func: Callable) -> CookieJar:
    """Wrapper handles cookie extraction errors."""

    @wraps(func)
    def wrapper(*args, **kwargs) -> CookieJar:
        try:
            return func(*args, **kwargs)
        except PermissionError:
            console = Console()
            console.clear()
            console.print(
                "We've encountered a Permissions Error. Please close all browsers and try again.",
                style="bold red",
            )
            console.print(
                "If you are still having issues, make sure all browsers processes are closed in a Task Manager.",
                style="bold red",
            )
            console.print("Nothing has been saved.", style="bold red")
            raise
        except ValueError as E:
            console = Console()
            console.clear()
            if str(E) == "Value cannot be None":
                console.print(
                    "No browser selected",
                    style="bold red",
                )
            else:
                console.print(
                    "The browser provided is not supported for extraction",
                    style="bold red",
                )
                console.print("Nothing has been saved.", style="bold red")
            raise
        except BrowserCookieError as E:
            console = Console()
            console.clear()
            console.print(
                "browser extraction ran into an error, the selected browser may not be available on your system",
                style="bold red",
            )
            console.print(
                str(E),
                style="bold red",
            )
            console.print(
                "If you are still having issues, make sure all browsers processes are closed in a Task Manager.",
                style="bold red",
            )
            console.print("Nothing has been saved.", style="bold red")
            raise
        except Exception:
            inquirer.confirm(message="Press enter to continue").execute()

    return wrapper


@cookie_wrapper
def get_cookies_from_browser(manager: Manager, browsers: str | None = None) -> None:
    """Get the cookies for the supported sites."""
    manager.path_manager.cookies_dir.mkdir(exist_ok=True)
    browsers = browsers or manager.config_manager.settings_data["Browser_Cookies"]["browsers"]
    if isinstance(browsers, str):
        browsers = re.split(r"[ ,]+", browsers)
    all_sites = set(SupportedDomains.supported_hosts)
    user_sites = manager.config_manager.settings_data["Browser_Cookies"]["sites"] or SupportedDomains.supported_hosts
    if isinstance(user_sites, str):
        user_sites = re.split(r"[ ,]+", user_sites)
    for domain in user_sites:
        domain = domain.lower() if domain else None
        if domain not in all_sites:
            continue
        cookie_jar = MozillaCookieJar()
        for browser in browsers:
            browser = browser.lower() if browser else None
            cookies = get_cookie(browser, domain)
            for cookie in cookies:
                cookie_jar.set_cookie(cookie)
        cookie_file_path = manager.path_manager.cookies_dir / f"{domain}.txt"
        cookie_jar.save(cookie_file_path, ignore_discard=True, ignore_expires=True)


def get_cookie(browser: str, domain: str) -> CookieJar:
    """Get the cookies for a specific domain."""
    if browser == "chrome":
        cookie = browser_cookie3.chrome(domain_name=domain)
    elif browser == "firefox":
        cookie = browser_cookie3.firefox(domain_name=domain)
    elif browser == "edge":
        cookie = browser_cookie3.edge(domain_name=domain)
    elif browser == "safari":
        cookie = browser_cookie3.safari(domain_name=domain)
    elif browser == "opera":
        cookie = browser_cookie3.opera(domain_name=domain)
    elif browser == "brave":
        cookie = browser_cookie3.brave(domain_name=domain)
    elif browser == "chromium":
        cookie = browser_cookie3.chromium(domain_name=domain)
    elif browser == "librewolf":
        cookie = browser_cookie3.librewolf(domain_name=domain)
    elif browser == "opera_gx":
        cookie = browser_cookie3.opera_gx(domain_name=domain)
    elif browser == "vivaldi":
        cookie = browser_cookie3.vivaldi(domain_name=domain)
    elif browser is None:
        msg = "Value cannot be None"
        raise ValueError(msg)
    else:
        msg = "Invalid browser specified"
        raise ValueError(msg)

    return cookie
