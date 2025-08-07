from __future__ import annotations

import asyncio
import sqlite3
import sys
from functools import wraps
from textwrap import dedent
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar

import browser_cookie3
from requests import request
from rich.console import Console
from rich.markdown import Markdown
from rich.text import Text

from cyberdrop_dl.clients.hash_client import hash_directory_scanner
from cyberdrop_dl.ui.prompts import user_prompts
from cyberdrop_dl.ui.prompts.basic_prompts import ask_dir_path, enter_to_continue
from cyberdrop_dl.ui.prompts.defaults import DONE_CHOICE, EXIT_CHOICE
from cyberdrop_dl.utils.cookie_management import clear_cookies
from cyberdrop_dl.utils.sorting import Sorter
from cyberdrop_dl.utils.updates import check_latest_pypi
from cyberdrop_dl.utils.utilities import clear_term, open_in_text_editor

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from InquirerPy.base.control import Choice

    from cyberdrop_dl.managers.manager import Manager

P = ParamSpec("P")
R = TypeVar("R")

console = Console()
ERROR_PREFIX = Text("ERROR: ", style="bold red")


def repeat_until_done(func: Callable[P, R]) -> Callable[P, R]:
    @wraps(func)
    def wrapper(*args, **kwargs) -> R:
        done = False
        while not done:
            done = func(*args, **kwargs)
        return done

    return wrapper


class ProgramUI:
    def __init__(self, manager: Manager, run: bool = True) -> None:
        self.manager = manager
        if run:
            self.run()

    @staticmethod
    def print_error(msg: str, critical: bool = False) -> None:
        text = ERROR_PREFIX + msg
        console.print(text, style="bold red" if critical else None)
        if critical:
            sys.exit(1)
        enter_to_continue()

    @repeat_until_done
    def run(self) -> bool | None:
        """Program UI."""
        clear_term()
        options_map = {
            -1: self._show_simpcity_disclaimer,
            1: self._download,
            2: self._retry_failed_download,
            3: self._scan_and_create_hashes,
            4: self._sort_files,
            5: self._edit_urls,
            6: self._change_config,
            7: self._manage_configs,
            8: self._check_updates,
            9: self._view_changelog,
        }

        answer = user_prompts.main_prompt(self.manager)
        result = self._process_answer(answer, options_map)
        return_to_main = result and result != DONE_CHOICE
        if return_to_main:
            clear_term()
        return return_to_main

    def _download(self) -> bool:
        """Starts download process."""
        return True

    def _retry_failed_download(self) -> bool:
        """Sets retry failed and starts download process."""
        self.manager.parsed_args.cli_only_args.retry_failed = True
        return True

    def _scan_and_create_hashes(self) -> None:
        """Scans a folder and creates hashes for all of its files."""
        path = ask_dir_path("Select the directory to scan", default=str(self.manager.path_manager.download_folder))
        hash_directory_scanner(self.manager, path)

    def _sort_files(self) -> None:
        """Sort files in download folder"""
        sorter = Sorter(self.manager)
        asyncio.run(sorter.run())

    def _check_updates(self) -> None:
        """Checks Cyberdrop-DL updates."""
        check_latest_pypi(logging="CONSOLE")
        enter_to_continue()

    def _change_config(self) -> None:
        configs = self.manager.config_manager.get_configs()
        selected_config = user_prompts.select_config(configs)
        if selected_config.casefold() == "all":
            self.manager.multiconfig = True
            return
        self.manager.config_manager.change_config(selected_config)
        if user_prompts.switch_default_config_to(self.manager, selected_config):
            self.manager.config_manager.change_default_config(selected_config)
        self.manager.config_manager.change_config(selected_config)

    def _view_changelog(self) -> None:
        clear_term()
        changelog_content = self._get_changelog()
        if not changelog_content:
            return
        with console.pager(links=True):
            console.print(Markdown(changelog_content, justify="left"))

    @repeat_until_done
    def _manage_configs(self) -> Choice | None:
        options_map = {
            1: self._change_default_config,
            2: self._create_new_config,
            3: self._delete_config,
            4: self._edit_config,
            5: self._edit_auth_config,
            6: self._edit_global_config,
            7: self._edit_auto_cookies_extration,
            8: self._import_cookies_now,
            9: self._clear_cookies,
            10: self._clear_cache,
        }
        answer = user_prompts.manage_configs(self.manager)
        return self._process_answer(answer, options_map)

    def _clear_cookies(self) -> None:
        domains, _ = user_prompts.domains_prompt(domain_message="Select site(s) to clear cookies for:")
        clear_cookies(self.manager, domains)
        console.print("Finished clearing cookies", style="green")
        enter_to_continue()

    def _clear_cache(self) -> None:
        domains, _ = user_prompts.domains_prompt(domain_message="Select site(s) to clear cache for:")
        if not domains:
            console.print("No domains selected", style="red")
            enter_to_continue()
            return
        urls = user_prompts.filter_cache_urls(self.manager, domains)
        for url in urls:
            asyncio.run(self.manager.cache_manager.request_cache.delete_url(url))

        console.print("\nExecuting database vacuum. This may take several minutes, please wait...")
        try:
            vacuum_database(self.manager.path_manager.cache_db)
        except sqlite3.Error as e:
            return self.print_error(f"Unable to clean request database. Database may be corrupted : {e!s}")
        console.print("Finished clearing the cache", style="green")
        enter_to_continue()

    def _edit_auth_config(self) -> None:
        config_file = self.manager.config_manager.authentication_settings
        self._open_in_text_editor(config_file)

    def _edit_global_config(self) -> None:
        config_file = self.manager.config_manager.global_settings
        self._open_in_text_editor(config_file)

    def _edit_config(self) -> None:
        if self.manager.multiconfig:
            self.print_error("Cannot edit 'ALL' config")
            return
        config_file = self.manager.config_manager.settings
        self._open_in_text_editor(config_file)

    def _create_new_config(self) -> None:
        config_name = user_prompts.create_new_config(self.manager)
        if not config_name:
            return
        if user_prompts.switch_default_config_to(self.manager, config_name):
            self.manager.config_manager.change_default_config(config_name)
        self.manager.config_manager.change_config(config_name)
        config_file = self.manager.config_manager.settings
        self._open_in_text_editor(config_file)

    def _edit_urls(self) -> None:
        self._open_in_text_editor(self.manager.path_manager.input_file, reload_config=False)

    def _change_default_config(self) -> None:
        configs = self.manager.config_manager.get_configs()
        selected_config = user_prompts.select_config(configs)
        self.manager.config_manager.change_default_config(selected_config)
        if user_prompts.activate_config(self.manager, selected_config) is not None:
            self.manager.config_manager.change_config(selected_config)

    def _delete_config(self) -> None:
        configs = self.manager.config_manager.get_configs()
        if len(configs) == 1:
            self.print_error("There is only one config")
            return

        selected_config = user_prompts.select_config(configs)
        if selected_config == self.manager.config_manager.loaded_config:
            self.print_error("You cannot delete the currently active config")
            return

        if self.manager.cache_manager.get("default_config") == selected_config:
            self.print_error("You cannot delete the default config")
            return

        self.manager.config_manager.delete_config(selected_config)
        if user_prompts.switch_default_config():
            self._change_default_config()

    def _edit_auto_cookies_extration(self) -> None:
        user_prompts.auto_cookie_extraction(self.manager)

    def _import_cookies_now(self) -> None:
        try:
            user_prompts.extract_cookies(self.manager)
        except browser_cookie3.BrowserCookieError as e:
            self.print_error(str(e))

    def _place_holder(self) -> None:
        self.print_error("Option temporarily disabled on this version")

    def _show_simpcity_disclaimer(self) -> None:
        simp_disclaimer = dedent(SIMPCITY_DISCLAIMER)
        clear_term()
        console.print(simp_disclaimer)
        enter_to_continue()

        self.manager.cache_manager.save("simp_disclaimer_shown", True)

    def _open_in_text_editor(self, file_path: Path, *, reload_config: bool = True):
        try:
            open_in_text_editor(file_path)
        except ValueError as e:
            self.print_error(str(e))
            return
        if reload_config:
            console.print("Revalidating config, please wait..")
            self.manager.config_manager.change_config(self.manager.config_manager.loaded_config)

    def _process_answer(self, answer: Any, options_map: dict) -> Choice | None:
        """Checks prompt answer and executes corresponding function."""
        if answer == EXIT_CHOICE.value:
            asyncio.run(self.manager.cache_manager.close())
            sys.exit(0)
        if answer == DONE_CHOICE.value:
            return DONE_CHOICE

        function_to_call = options_map.get(answer)
        if not function_to_call:
            self.print_error("Something went wrong. Please report it to the developer", critical=True)
            sys.exit(1)

        return function_to_call()

    def _get_changelog(self) -> str | None:
        """Get latest changelog file from github. Returns its content."""
        path = self.manager.path_manager.config_folder.parent / "CHANGELOG.md"
        url = "https://raw.githubusercontent.com/jbsparrow/CyberDropDownloader/refs/heads/master/CHANGELOG.md"
        _, latest_version = check_latest_pypi(logging="OFF")
        if not latest_version:
            self.print_error("UNABLE TO GET LATEST VERSION INFORMATION")
            return None

        name = f"{path.stem}_{latest_version}{path.suffix}"
        changelog = path.with_name(name)
        if not changelog.is_file():
            changelog_pattern = f"{path.stem}*{path.suffix}"
            for old_changelog in path.parent.glob(changelog_pattern):
                old_changelog.unlink()
            try:
                with request("GET", url, timeout=15) as response:
                    response.raise_for_status()
                    with changelog.open("wb") as f:
                        f.write(response.content)
            except Exception:
                self.print_error("UNABLE TO GET CHANGELOG INFORMATION")
                return None

        lines = changelog.read_text(encoding="utf8").splitlines()
        # remove keep_a_changelog disclaimer
        return "\n".join(lines[:4] + lines[6:])


def vacuum_database(db_path: Path) -> None:
    if not db_path.is_file():
        return
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("VACUUM")
        conn.commit()
    finally:
        if conn:
            conn.close()


SIMPCITY_DISCLAIMER = """
\t\t[bold red]!!    DISCLAIMER    !![/bold red]


Due to the recent DDOS attacks on [italic]SimpCity[/italic], I have made some changes to [italic]Cyberdrop-DL[/italic].

First and foremost, we have removed support for scraping [italic]SimpCity[/italic] for the time being. I know that this will upset many of you, but hopefully, you will understand my reasoning.


Because of the DDOS attacks that [italic]SimpCity[/italic] has been receiving, they have been forced to implement some protective features such as using a DDOS-Guard browser check, only allowing [link=https://simpcity.su/threads/emails-august-2024.365869/]whitelisted email domains[/link] to access the website, and [link=https://simpcity.su/threads/rate-limit-429-error.397746/]new rate limits[/link].
[italic]Cyberdrop-DL[/italic] allows a user to scrape a model's entire thread in seconds, downloading all the files that it finds. This is great but can be problematic for a few reasons:
\t- We end up downloading a lot of content that we will never view.
\t- Such large-scale scraping with no limits puts a large strain on [italic]SimpCity[/italic]'s servers, especially when they are getting DDOSed.
\t- Scraping has no benefit for [italic]SimpCity[/italic] - they gain nothing from us scraping their website.

For those reasons, [italic]SimpCity[/italic] has decided that they don't want to allow automated thread scraping anymore, and have removed the [italic]Cyberdrop-DL[/italic] thread from their website.
I want to respect [italic]SimpCity[/italic]'s wishes, and as a result, have disabled scraping for [italic]SimpCity[/italic] links.

In order to help reduce the impact that [italic]Cyberdrop-DL[/italic] has on other websites, I have decided to enable the [italic bold]update_last_forum_post[/italic bold] setting for all users' configs.
You can disable it again after reading through this disclaimer, however, I would recommend against it. [italic bold]update_last_forum_post[/italic bold] actually speeds up scrapes and reduces the load on websites' servers by not re-scraping entire threads and picking up where it left off last time.

Furthermore, I have adjusted the default rate-limiting settings in an effort to reduce the impact that [italic]Cyberdrop-DL[/italic] will have on websites.

I encourage you to be conscientious about how you use [italic]Cyberdrop-DL[/italic].
Some tips on how to reduce the impact your use of [italic]Cyberdrop-DL[/italic] will have on a website:
\t- Try to avoid looping runs repeatedly.
\t- If you have a large URLs file, try to comb through it occasionally and get rid of items you don't want anymore, and try to run [italic]Cyberdrop-DL[/italic] less often.
\t- Avoid downloading content you don't want. It's good to scan through the content quickly to ensure it's not a bunch of stuff you're going to delete after downloading it.

If you do want to continue downloading from SimpCity, you can use a tampermonkey script like this one: [link=https://simpcity.su/threads/forum-post-downloader-tampermonkey-script.96714/]SimpCity Tampermonkey Forum Downloader[/link]
"""
