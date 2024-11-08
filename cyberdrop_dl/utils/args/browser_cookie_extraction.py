from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING

import browser_cookie3
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
            inquirer.confirm(message="Press enter to return menu.").execute()

    return wrapper


# noinspection PyProtectedMember
@cookie_wrapper
def get_forum_cookies(manager: Manager, browser: str) -> None:
    """Get the cookies for the forums."""
    auth_args: dict = manager.config_manager.authentication_data
    for forum in SupportedDomains.supported_forums:
        forum_key = f"{SupportedDomains.supported_forums_map[forum]}_xf_user_cookie"
        cookie = get_cookie(browser, forum)
        posible_cookie_keys = [forum, f"www.{forum}"]
        cookie_key = next((key for key in posible_cookie_keys if key in cookie._cookies), None)
        if not cookie_key:
            continue
        auth_args["Forums"][forum_key] = cookie._cookies[cookie_key]["/"]["xf_user"].value

    manager.cache_manager.save("browser", browser)


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
    else:
        msg = "Invalid browser specified"
        raise ValueError(msg)

    return cookie
