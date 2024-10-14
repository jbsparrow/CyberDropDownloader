from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING
from pathlib import Path

import browser_cookie3
from InquirerPy import inquirer
from rich.console import Console
from http.cookiejar import MozillaCookieJar

from cyberdrop_dl.utils.dataclasses.supported_domains import SupportedDomains

if TYPE_CHECKING:
    from typing import Dict

    from cyberdrop_dl.managers.manager import Manager


def cookie_wrapper(func):
    """Wrapper handles errors for url scraping"""

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except PermissionError:
            console = Console()
            console.clear()
            console.print("We've encountered a Permissions Error. Please close all browsers and try again.",
                          style="bold red")
            console.print(
                "If you are still having issues, make sure all browsers processes are closed in a Task Manager.",
                style="bold red")
            console.print("Nothing has been saved.", style="bold red")
            inquirer.confirm(message="Press enter to return menu.").execute()
            return

    return wrapper


# noinspection PyProtectedMember
@cookie_wrapper
def get_cookies_from_browser(manager: Manager, browser: str, domains: list) -> None:
    """Get the cookies for the supported sites"""
    manager.path_manager.cookies_dir.mkdir(exist_ok=True)
    for domain in domains:
        cookies = get_cookie(browser, domain)
        cookie_jar = MozillaCookieJar()
        cookie_file_path = manager.path_manager.cookies_dir / f"{domain}.txt"

        for cookie in cookies:
            cookie_jar.set_cookie(cookie)

        cookie_jar.save(cookie_file_path, ignore_discard=True, ignore_expires=True)

    manager.cache_manager.save("browser", browser)


def get_cookie(browser: str, domain: str):
    """Get the cookies for a specific domain"""
    if browser == 'chrome':
        cookie = browser_cookie3.chrome(domain_name=domain)
    elif browser == 'firefox':
        cookie = browser_cookie3.firefox(domain_name=domain)
    elif browser == 'edge':
        cookie = browser_cookie3.edge(domain_name=domain)
    elif browser == 'safari':
        cookie = browser_cookie3.safari(domain_name=domain)
    elif browser == 'opera':
        cookie = browser_cookie3.opera(domain_name=domain)
    elif browser == 'brave':
        cookie = browser_cookie3.brave(domain_name=domain)
    else:
        raise ValueError('Invalid browser specified')

    return cookie
