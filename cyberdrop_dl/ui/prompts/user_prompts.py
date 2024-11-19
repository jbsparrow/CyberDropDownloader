from __future__ import annotations

from typing import TYPE_CHECKING

from InquirerPy import get_style
from InquirerPy.base.control import Choice
from rich.console import Console

from cyberdrop_dl import __version__
from cyberdrop_dl.ui.prompts import basic_prompts
from cyberdrop_dl.ui.prompts.defaults import ALL_CHOICE, DONE_CHOICE, EXIT_CHOICE
from cyberdrop_dl.utils.constants import BROWSERS, RESERVED_CONFIG_NAMES
from cyberdrop_dl.utils.cookie_extraction import get_cookies_from_browsers
from cyberdrop_dl.utils.data_enums_classes.supported_domains import SupportedDomains
from cyberdrop_dl.utils.utilities import clear_term

if TYPE_CHECKING:
    from pathlib import Path

    from cyberdrop_dl.managers.manager import Manager

console = Console()


def main_prompt(manager: Manager) -> int:
    """Main prompt for the program."""
    prompt_header(manager)
    OPTIONS = {
        "group_1": [
            "Download",
            "Retry failed downloads",
            "Create file hashes",
            "Sort files in download folder",
        ],
        "group_2": ["Edit URLs.txt", "Change config", "Edit configs", "Import V4 items"],
        "group_3": [
            "Check for updates",
            "View changelog",
        ],
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
            "Clear cached responses",
        ],
        "group_2": [
            "Edit current config",
            "Edit authentication config",
            "Edit global config ",
        ],
        "group 3": ["Edit auto cookie extraction settings", "Import cookies now"],
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
        message="Select a config file:",
        choices=configs,
        validate_empty=True,
        long_instruction="ARROW KEYS: Navigate | TYPE: Filter | TAB: select, ENTER: Finish Selection",
        invalid_message="Need to select a config.",
    )


def _check_valid_new_config_name(answer: str, manager: Manager) -> str | None:
    """Check if the provided config name if. Returns `None` if the config name is invalid."""
    msg = None
    if answer.casefold() in RESERVED_CONFIG_NAMES:
        msg = f"[bold red]ERROR:[/bold red] Config name '{answer}' is a reserved internal name"

    elif manager.path_manager.config_dir.joinpath(answer).is_dir():
        msg = f"[bold red]ERROR:[/bold red] Config with name '{answer}' already exists!"
    if msg:
        console.print(msg)
        basic_prompts.enter_to_continue()
        return None

    return answer


""" ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ AUTHENTICATION PROMPTS ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""


def auto_cookie_extraction(manager: Manager):
    answer = basic_prompts.ask_toggle("Enable auto cookies import:")
    manager.config_manager.settings_data["Browser_Cookies"]["auto_import"] = answer
    if answer:
        extract_cookies(manager, dry_run=True)
    manager.config_manager.write_updated_settings_config()


def extract_cookies(manager: Manager, *, dry_run: bool = False) -> None:
    """Asks the user to select browser(s) and domains(s) to import cookies from."""
    OPTIONS = [["forum", "file-host"]]
    choices = basic_prompts.create_choices(OPTIONS)
    domain_type = basic_prompts.ask_choice(choices, message="Select categorie:")

    if domain_type == DONE_CHOICE.value:
        return

    all_domains = SupportedDomains.supported_forums_map.keys() if domain_type == 1 else SupportedDomains.supported_hosts
    domain_choices = [Choice(site) for site in all_domains] + [ALL_CHOICE]
    domains = basic_prompts.ask_checkbox(domain_choices, message="Select site(s) to import cookies from:")
    browsers = browser_prompt()

    if ALL_CHOICE.value in domains:
        domains = all_domains

    if ALL_CHOICE.value in browsers:
        browsers = list(map(str.capitalize, BROWSERS))

    if dry_run:
        manager.config_manager.settings_data["Browser_Cookies"]["browsers"] = browsers
        manager.config_manager.settings_data["Browser_Cookies"]["sites"] = domains
        return

    get_cookies_from_browsers(manager, browsers=browsers, domains=domains)
    console.print("Import finished", style="green")
    basic_prompts.enter_to_continue()


def browser_prompt() -> str:
    choices = [Choice(browser, browser.capitalize()) for browser in BROWSERS]
    return basic_prompts.ask_checkbox(choices, message="Select the browser(s) for extraction:")


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
