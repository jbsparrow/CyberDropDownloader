from __future__ import annotations

import asyncio
import sys
from functools import wraps
from textwrap import dedent
from typing import TYPE_CHECKING, Any

from requests import request
from rich.console import Console
from rich.markdown import Markdown
from rich.text import Text

from cyberdrop_dl.clients.hash_client import hash_directory_scanner
from cyberdrop_dl.dependencies import browser_cookie3
from cyberdrop_dl.ui.prompts import user_prompts
from cyberdrop_dl.ui.prompts.basic_prompts import ask_dir_path, enter_to_continue
from cyberdrop_dl.ui.prompts.defaults import DONE_CHOICE, EXIT_CHOICE
from cyberdrop_dl.utils.cookie_management import clear_cookies
from cyberdrop_dl.utils.transfer.transfer_v4_config import transfer_v4_config
from cyberdrop_dl.utils.transfer.transfer_v4_db import transfer_v4_db
from cyberdrop_dl.utils.utilities import check_latest_pypi, clear_term, open_in_text_editor

if TYPE_CHECKING:
    from pathlib import Path

    from InquirerPy.base.control import Choice

    from cyberdrop_dl.managers.manager import Manager


console = Console()
ERROR_PREFIX = Text("ERROR: ", style="bold red")


def repeat_until_done(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
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
    def run(self) -> None:
        """Program UI."""
        clear_term()
        options_map = {
            -1: self._show_simpcity_disclaimer,
            1: self._download,
            2: self._retry_failed_download,
            3: self._scan_and_create_hashes,
            4: self._place_holder,
            5: self._edit_urls,
            6: self._change_config,
            7: self._manage_configs,
            8: self._import_from_v4,
            9: self._check_updates,
            10: self._view_changelog,
        }

        answer = user_prompts.main_prompt(self.manager)
        result = self._process_answer(answer, options_map)
        return_to_main = result and result != DONE_CHOICE
        if return_to_main:
            clear_term()
        return return_to_main

    def _download(self) -> True:
        """Starts download process."""
        return True

    def _retry_failed_download(self) -> True:
        """Sets retry failed and starts download process."""
        self.manager.parsed_args.cli_only_args.retry_failed = True
        return True

    def _scan_and_create_hashes(self) -> None:
        """Scans a folder and creates hashes for all of its files."""
        path = ask_dir_path("Select the directory to scan")
        hash_directory_scanner(self.manager, path)

    def _check_updates(self) -> None:
        """Checks Cyberdrop-DL updates."""
        check_latest_pypi(call_from_ui=True)
        enter_to_continue()

    @repeat_until_done
    def _import_from_v4(self) -> None:
        options_map = {
            1: self._import_v4_config,
            2: self._import_v4_download_history,
        }
        answer = user_prompts.import_cyberdrop_v4_items_prompt(self.manager)
        return self._process_answer(answer, options_map)

    def _import_v4_config(self) -> None:
        new_config = user_prompts.import_v4_config_prompt(self.manager)
        if not new_config:
            return
        transfer_v4_config(self.manager, *new_config)

    def _import_v4_download_history(self) -> None:
        import_download_history_path = user_prompts.import_v4_download_history_prompt()
        if import_download_history_path.is_file():
            transfer_v4_db(import_download_history_path, self.manager.path_manager.history_db)
            return

        for item in import_download_history_path.glob("**/*.sqlite"):
            if str(item) == str(self.manager.path_manager.history_db):
                continue
            try:
                transfer_v4_db(item, self.manager.path_manager.history_db)
            except Exception as e:
                self.print_error(f"Unable to import {item.name}: {e!s}")

    def _change_config(self) -> None:
        configs = self.manager.config_manager.get_configs()
        selected_config = user_prompts.select_config(configs)
        if selected_config.casefold() == "all":
            self.manager.multiconfig = True
            return
        self.manager.config_manager.change_config(selected_config)

    def _view_changelog(self) -> None:
        clear_term()
        changelog_content = self._get_changelog()
        if not changelog_content:
            return
        with console.pager(links=True):
            console.print(Markdown(changelog_content, justify="left"))

    @repeat_until_done
    def _manage_configs(self) -> None:
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
        domains = user_prompts.domains_prompt(domain_message="Select site(s) to clear cache for:")
        if not domains:
            console.print("No domains selected", style="red")
            enter_to_continue()
            return
        urls = user_prompts.filter_cache_urls(self.manager, domains)
        for url in urls:
            asyncio.run(self.manager.cache_manager.request_cache.delete_url(url))
        console.print("Finished clearing the cache", style="green")
        enter_to_continue()

    def _edit_auth_config(self) -> None:
        config_file = self.manager.path_manager.config_folder / "authentication.yaml"
        self._open_in_text_editor(config_file)

    def _edit_global_config(self) -> None:
        config_file = self.manager.path_manager.config_folder / "global_settings.yaml"
        self._open_in_text_editor(config_file)

    def _edit_config(self) -> None:
        if self.manager.multiconfig:
            self.print_error("Cannot edit 'ALL' config")
            return
        config_file = (
            self.manager.path_manager.config_folder / self.manager.config_manager.loaded_config / "settings.yaml"
        )
        self._open_in_text_editor(config_file)

    def _create_new_config(self) -> None:
        config_name = user_prompts.create_new_config(self.manager)
        if not config_name:
            return
        self.manager.config_manager.change_config(config_name)
        config_file = self.manager.path_manager.config_folder / config_name / "settings.yaml"
        self._open_in_text_editor(config_file)

    def _edit_urls(self) -> None:
        self._open_in_text_editor(self.manager.path_manager.input_file)

    def _change_default_config(self) -> None:
        configs = self.manager.config_manager.get_configs()
        selected_config = user_prompts.select_config(configs)
        self.manager.config_manager.change_default_config(selected_config)

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

    def _open_in_text_editor(self, file_path: Path):
        try:
            open_in_text_editor(file_path)
        except ValueError:
            self.print_error("No default text editor found")

    def _process_answer(self, answer: Any, options_map=dict) -> Choice | None:
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

    def _get_changelog(self) -> str:
        """Get latest changelog file from github. Returns its content."""
        path = self.manager.path_manager.config_folder.parent / "CHANGELOG.md"
        url = "https://raw.githubusercontent.com/jbsparrow/CyberDropDownloader/refs/heads/master/CHANGELOG.md"
        _, latest_version = check_latest_pypi(log_to_console=False)
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
