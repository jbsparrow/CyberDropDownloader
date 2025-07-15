# type: ignore[reportPrivateImportUsage]
from __future__ import annotations

import asyncio
from enum import IntEnum
from platform import system
from typing import TYPE_CHECKING

from InquirerPy import get_style
from InquirerPy.base.control import Choice
from InquirerPy.enum import (
    INQUIRERPY_EMPTY_CIRCLE_SEQUENCE,
    INQUIRERPY_FILL_CIRCLE_SEQUENCE,
)
from rich.console import Console

from cyberdrop_dl import __version__
from cyberdrop_dl.constants import BROWSERS, RESERVED_CONFIG_NAMES
from cyberdrop_dl.data_structures.supported_domains import (
    SUPPORTED_FORUMS,
    SUPPORTED_SITES_DOMAINS,
    SUPPORTED_WEBSITES,
)
from cyberdrop_dl.ui.prompts import basic_prompts
from cyberdrop_dl.ui.prompts.defaults import ALL_CHOICE, DONE_CHOICE, EXIT_CHOICE
from cyberdrop_dl.utils.cookie_management import get_cookies_from_browsers
from cyberdrop_dl.utils.utilities import clear_term

if TYPE_CHECKING:
    from pathlib import Path

    from yarl import URL

    from cyberdrop_dl.managers.manager import Manager

console = Console()


def main_prompt(manager: Manager) -> int:
    """Main prompt for the program."""
    prompt_header(manager)
    OPTIONS = {
        "group_1": ["Download", "Retry failed downloads", "Create file hashes", "Sort files in download folder"],
        "group_2": ["Edit URLs.txt", "Change config", "Edit configs"],
        "group_3": ["Check for updates", "View changelog"],
    }

    choices = basic_prompts.create_choices(OPTIONS, append_last=EXIT_CHOICE)
    simp_disclaimer_shown = manager.cache_manager.get("simp_disclaimer_shown")
    if not simp_disclaimer_shown:
        choices = [Choice(-1, "!! PRESS <ENTER> TO VIEW DISCLAIMER !!")]

    prompt_options = {"style": get_style({"pointer": "#ff0000 bold"}) if not simp_disclaimer_shown else None}

    if not simp_disclaimer_shown:
        prompt_options["long_instruction"] = "ENTER: view disclaimer"

    return basic_prompts.ask_choice(choices, **prompt_options)


""" ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ MANAGE CONFIG PROMPTS ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""


def manage_configs(manager: Manager) -> int:
    """Manage Configs Prompt."""
    prompt_header(manager)
    OPTIONS = {
        "group_1": [
            "Change default config",
            "Create a new config",
            "Delete a config",
        ],
        "group_2": [
            "Edit current config",
            "Edit authentication config",
            "Edit global config",
        ],
        "group_3": ["Edit auto cookie extraction settings", "Import cookies now", "Clear cookies"],
        "group_4": [
            "Clear cache",
        ],
    }
    choices = basic_prompts.create_choices(OPTIONS)
    return basic_prompts.ask_choice(choices)


def create_new_config(manager: Manager, *, title: str = "Create a new config file") -> str | None:
    """Asks the user for a new config name. Returns `None` if the config name is invalid."""
    clear_term()
    console.print(title)
    answer: str = basic_prompts.ask_text("Enter the name of the config:")
    return _check_valid_new_config_name(answer, manager)


def select_config(configs: list) -> str:
    """Asks the user to select an existing config name."""
    return basic_prompts.ask_choice_fuzzy(
        choices=configs,
        message="Select a config file:",
        validate_empty=True,
        long_instruction="ARROW KEYS: Navigate | TYPE: Filter | TAB: select, ENTER: Finish Selection",
        invalid_message="Need to select a config.",
    )


def switch_default_config_to(manager: Manager, config_name: str) -> str:
    """Asks the user if they want to switch the default config to the provided config"""
    if manager.config_manager.get_default_config() == config_name:
        return
    return basic_prompts.ask_toggle(
        message=f"Do you want to switch the default config to {config_name}?",
    )


def switch_default_config() -> str:
    """Asks the user if they want to switch the default config"""
    return basic_prompts.ask_toggle(
        message="Do you want to switch the default config?",
    )


def activate_config(manager: Manager, config) -> str:
    """Asks the user if they want to activate the provided config"""
    if manager.config_manager.get_loaded_config() == config:
        return
    return basic_prompts.ask_toggle(message=f"Do also want to activate the {config} config?")


def _check_valid_new_config_name(answer: str, manager: Manager) -> str | None:
    """Check if the provided config name if. Returns `None` if the config name is invalid."""
    msg = None
    if answer.casefold() in RESERVED_CONFIG_NAMES:
        msg = f"[bold red]ERROR:[/bold red] Config name '{answer}' is a reserved internal name"

    elif manager.path_manager.config_folder.joinpath(answer).is_dir():
        msg = f"[bold red]ERROR:[/bold red] Config with name '{answer}' already exists!"
    if msg:
        console.print(msg)
        basic_prompts.enter_to_continue()
        return None

    return answer


""" ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ AUTHENTICATION PROMPTS ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""


def auto_cookie_extraction(manager: Manager):
    answer = basic_prompts.ask_toggle("Enable auto cookies import:")
    manager.config_manager.settings_data.browser_cookies.auto_import = answer
    if answer:
        extract_cookies(manager, dry_run=True)
    manager.config_manager.write_updated_settings_config()


class DomainType(IntEnum):
    WEBSITE = 0
    FORUM = 1


def domains_prompt(*, domain_message: str = "Select site(s):") -> tuple[list[str], list[str]]:
    """Asks the user to select website(s) for cookie actions and cache actions."""
    OPTIONS = [["Forum", "File Host"], ["All Supported Websites"]]
    choices = basic_prompts.create_choices(OPTIONS)
    domain_type = basic_prompts.ask_choice(choices, message="Select category:")

    if domain_type == DONE_CHOICE.value:
        return [], []

    if domain_type == 3:
        return SUPPORTED_SITES_DOMAINS, SUPPORTED_SITES_DOMAINS

    all_domains = list(SUPPORTED_FORUMS.values() if domain_type == DomainType.FORUM else SUPPORTED_WEBSITES.values())
    domain_choices = [Choice(site) for site in all_domains] + [ALL_CHOICE]

    domains = basic_prompts.ask_choice_fuzzy(
        choices=domain_choices,
        message=domain_message,
        validate_empty=True,
        multiselect=True,
        marker_pl=f" {INQUIRERPY_EMPTY_CIRCLE_SEQUENCE} ",
        marker=f" {INQUIRERPY_FILL_CIRCLE_SEQUENCE} ",
        style=get_style(
            {
                "marker": "#98c379",
                "questionmark": "#e5c07b",
                "pointer": "#61afef",
                "long_instruction": "#abb2bf",
                "fuzzy_prompt": "#c678dd",
                "fuzzy_info": "#abb2bf",
                "fuzzy_border": "#4b5263",
                "fuzzy_match": "#c678dd",
            }
        ),
    )
    if ALL_CHOICE.value in domains:
        domains = all_domains
    return domains, all_domains


def extract_cookies(manager: Manager, *, dry_run: bool = False) -> None:
    """Asks the user to select browser(s) and domains(s) to import cookies from."""

    supported_forums, supported_websites = list(SUPPORTED_FORUMS.values()), list(SUPPORTED_WEBSITES.values())
    domains, all_domains = domains_prompt(domain_message="Select site(s) to import cookies from:")
    if domains == []:
        return
    browser = BROWSERS(browser_prompt())

    if dry_run:
        manager.config_manager.settings_data.browser_cookies.browser = browser
        current_sites = set(manager.config_manager.settings_data.browser_cookies.sites)
        new_sites = current_sites - set(all_domains)
        if domains == supported_forums:
            new_sites -= {"all"}
            new_sites.add("all_forums")
        elif domains == supported_websites:
            new_sites -= {"all"}
            new_sites.add("all_file_hosts")
        elif domains == SUPPORTED_SITES_DOMAINS:
            new_sites -= {"all_forums", "all_file_hosts"}
            new_sites.add("all")
        else:
            new_sites -= {"all", "all_forums", "all_file_hosts"}
            new_sites.update(domains)
        if "all_forums" in new_sites and "all_file_hosts" in new_sites:
            new_sites -= {"all_forums", "all_file_hosts"}
            new_sites.add("all")
        manager.config_manager.settings_data.browser_cookies.sites = sorted(new_sites)
        return

    get_cookies_from_browsers(manager, browser=browser, domains=domains)
    console.print("Import finished", style="green")
    basic_prompts.enter_to_continue()


def browser_prompt() -> str:
    """Asks the user to select browser(s) for cookie extraction."""
    unsupported_browsers = {
        "Windows": {
            "arc",
            "brave",
            "chrome",
            "chromium",
            "edge",
            "lynx",
            "opera",
            "opera_gx",
            "safari",
            "vivaldi",
            "w3m",
        },
        "Linux": {"arc", "opera_gx", "safari"},
        "Darwin": {"lynx", "w3m"},
    }.get(system(), set())
    choices = [
        Choice(browser, browser.capitalize() if browser != "opera_gx" else "Opera GX")
        for browser in BROWSERS
        if browser not in unsupported_browsers
    ]
    return basic_prompts.ask_choice(choices, message="Select the browser(s) for extraction:")


""" ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ CACHE PROMPTS ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""


async def _get_urls(manager: Manager) -> set[URL]:
    urls = set()
    async for url in manager.cache_manager.request_cache.get_urls():
        urls.add(url)
    return urls


def filter_cache_urls(manager: Manager, domains: list) -> set[URL]:
    urls_to_remove = set()
    cached_urls = asyncio.run(_get_urls(manager))
    cached_urls_copy = cached_urls.copy()
    for domain in domains:
        cached_urls = cached_urls_copy.copy()
        cached_urls_copy = cached_urls.copy()
        for url in cached_urls:
            if url.host == domain:
                urls_to_remove.add(url)
                cached_urls_copy.remove(url)
    return urls_to_remove


""" ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ V4 IMPORT PROMPTS ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""


def import_cyberdrop_v4_items_prompt(manager: Manager) -> int:
    """Import Cyberdrop_V4 Items."""
    prompt_header(manager)
    OPTIONS = [["Import config", "Import download_history.sql"]]
    choices = basic_prompts.create_choices(OPTIONS)
    console.print("V4 Import Menu")
    return basic_prompts.ask_choice(choices)


def import_v4_config_prompt(manager: Manager) -> tuple[str, Path] | None:
    """Asks the user for the name and path of the config to import. Returns `None` if the config name is invalid."""
    new_config = create_new_config(manager, title="What should this config be called:")
    if not new_config:
        return None
    return new_config, basic_prompts.ask_file_path("Select the config file to import:")


def import_v4_download_history_prompt() -> Path:
    return basic_prompts.ask_file_path("Select the download_history.sql file to import:")


""" ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ OTHERS ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""


def prompt_header(manager: Manager, title: str | None = None) -> None:
    clear_term()
    title = title or f"[bold]Cyberdrop Downloader ([blue]V{__version__!s}[/blue])[/bold]"
    console.print(title)
    console.print(f"[bold]Current config:[/bold] [blue]{manager.config_manager.loaded_config}[/blue]")
