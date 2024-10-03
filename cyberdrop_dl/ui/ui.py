from __future__ import annotations

from pathlib import Path
from rich.markdown import Markdown
from textwrap import dedent
from typing import TYPE_CHECKING

from InquirerPy import inquirer
from InquirerPy.validator import PathValidator
from rich import print as rprint
import asyncio
from rich.console import Console

import aiofiles
from aiohttp import request
import asyncio

from cyberdrop_dl import __version__
from cyberdrop_dl.clients.hash_client import hash_directory_scanner
from cyberdrop_dl.ui.prompts.general_prompts import (
    main_prompt, select_config_prompt, import_cyberdrop_v4_items_prompt, manage_configs_prompt)
from cyberdrop_dl.ui.prompts.settings_authentication_prompts import edit_authentication_values_prompt
from cyberdrop_dl.ui.prompts.settings_global_prompts import edit_global_settings_prompt
from cyberdrop_dl.ui.prompts.settings_hash_prompts import path_prompt
from cyberdrop_dl.ui.prompts.settings_user_prompts import create_new_config_prompt, edit_config_values_prompt
from cyberdrop_dl.ui.prompts.url_file_prompts import edit_urls_prompt
from cyberdrop_dl.utils.utilities import check_latest_pypi

console = Console()

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


def bold(text: str) -> str:
    """Format a string in bold by overstriking."""
    return ''.join(ch + '\b' + ch for ch in text)


def program_ui(manager: Manager):
    """Program UI"""
    while True:
        console.clear()
        console.print(f"[bold]Cyberdrop Downloader (V{str(__version__)})[/bold]")
        console.print(f"[bold]Current Config:[/bold] {manager.config_manager.loaded_config}")

        action = main_prompt(manager)

        if action == -1:
            simp_disclaimer = """
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

            console.clear()
            simp_disclaimer = dedent(simp_disclaimer)
            rprint(simp_disclaimer)

            input("Press Enter to continue...")
            manager.cache_manager.save('simp_disclaimer_shown', True)

        # Download
        if action == 1:
            break

        # Download (All Configs)
        if action == 2:
            manager.args_manager.all_configs = True
            break

        # Retry Failed Downloads
        elif action == 3:
            manager.args_manager.retry_failed = True
            break

        # Scanning folder to create hashes
        elif action == 4:
            path = path_prompt(manager)
            hash_directory_scanner(manager, path)

        # Sort All Configs
        elif action == 5:
            manager.args_manager.sort_all_configs = True
            manager.args_manager.all_configs = True
            break

        # Edit URLs
        elif action == 6:
            input_file = manager.config_manager.settings_data['Files'][
                'input_file'] if not manager.args_manager.input_file else manager.args_manager.input_file
            edit_urls_prompt(input_file, manager.vi_mode)

        # Select Config
        elif action == 7:
            configs = manager.config_manager.get_configs()
            selected_config = select_config_prompt(manager, configs)
            manager.config_manager.change_config(selected_config)

        elif action == 8:
            console.clear()
            console.print("Editing Input / Output File Paths")
            input_file = inquirer.filepath(
                message="Enter the input file path:",
                default=str(manager.config_manager.settings_data['Files']['input_file']),
                validate=PathValidator(is_file=True, message="Input is not a file"),
                vi_mode=manager.vi_mode,
            ).execute()
            download_folder = inquirer.text(
                message="Enter the download folder path:",
                default=str(manager.config_manager.settings_data['Files']['download_folder']),
                validate=PathValidator(is_dir=True, message="Input is not a directory"),
                vi_mode=manager.vi_mode,
            ).execute()

            manager.config_manager.settings_data['Files']['input_file'] = Path(input_file)
            manager.config_manager.settings_data['Files']['download_folder'] = Path(download_folder)
            manager.config_manager.write_updated_settings_config()

        # Manage Configs
        elif action == 9:
            while True:
                console.clear()
                console.print("[bold]Manage Configs[/bold]")
                console.print(f"[bold]Current Config:[/bold] {manager.config_manager.loaded_config}")

                action = manage_configs_prompt(manager)

                # Change Default Config
                if action == 1:
                    configs = manager.config_manager.get_configs()
                    selected_config = select_config_prompt(manager, configs)
                    manager.config_manager.change_default_config(selected_config)

                # Create A Config
                elif action == 2:
                    create_new_config_prompt(manager)

                # Delete A Config
                elif action == 3:
                    configs = manager.config_manager.get_configs()
                    if len(configs) != 1:
                        selected_config = select_config_prompt(manager, configs)
                        if selected_config == manager.config_manager.loaded_config:
                            inquirer.confirm(
                                message="You cannot delete the currently active config, press enter to continue.",
                                default=False,
                                vi_mode=manager.vi_mode,
                            ).execute()
                            continue
                        manager.config_manager.delete_config(selected_config)
                    else:
                        inquirer.confirm(
                            message="There is only one config, press enter to continue.",
                            default=False,
                            vi_mode=manager.vi_mode,
                        ).execute()

                # Clear Request Cache
                elif action == 4:
                    # Clear the request cache using an async function
                    asyncio.run(manager.cache_manager.request_cache.clear())

                # Edit Config
                elif action == 5:
                    edit_config_values_prompt(manager)

                # Edit Authentication Values
                elif action == 6:
                    edit_authentication_values_prompt(manager)

                # Edit Global Settings
                elif action == 7:
                    edit_global_settings_prompt(manager)

                # Done
                elif action == 8:
                    break

        # Import Cyberdrop_V4 Items
        elif action == 10:
            import_cyberdrop_v4_items_prompt(manager)

        elif action == 11:
            changelog_path = manager.path_manager.config_dir.parent / "CHANGELOG.md"
            changelog_content = asyncio.run(_get_changelog(changelog_path))

            with console.pager(links = True):
                console.print(Markdown(changelog_content , justify = "left"))

        # Exit
        elif action == 12:
            asyncio.run(manager.cache_manager.close())
            exit(0)


async def _get_changelog(changelog_path: Path):
    url = "https://raw.githubusercontent.com/jbsparrow/CyberDropDownloader/refs/heads/master/CHANGELOG.md"
    _ , lastest_version = await check_latest_pypi(log_to_console = False)
    latest_changelog = changelog_path.with_name(f"{changelog_path.stem}_{lastest_version}{changelog_path.suffix}")
    if not latest_changelog.is_file():
        changelog_pattern = f"{changelog_path.stem}*{changelog_path.suffix}"
        for old_changelog in changelog_path.parent.glob(changelog_pattern):
            old_changelog.unlink() 
        try:
            async with request("GET", url) as response:
                response.raise_for_status()
                async with aiofiles.open(latest_changelog, 'wb') as f:   
                    await f.write(await response.read())
        except Exception:
            return "UNABLE TO GET CHANGELOG INFORMATION"
 
    changelog_lines = latest_changelog.read_text(encoding="utf8").splitlines()
    # remove keep_a_changelog disclaimer
    changelog_content = "\n".join(changelog_lines[:4] + changelog_lines[6:])
    
    return changelog_content
    