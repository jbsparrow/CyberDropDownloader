from __future__ import annotations

import asyncio
import logging
import os
import re
from enum import IntEnum
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Union

import rich
from yarl import URL

from cyberdrop_dl.clients.errors import NoExtensionFailure, FailedLoginFailure, InvalidContentTypeFailure, \
    PasswordProtected
from cyberdrop_dl.managers.console_manager import log as log_console

if TYPE_CHECKING:
    from typing import Tuple

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.dataclasses.url_objects import ScrapeItem

logger = logging.getLogger("cyberdrop_dl")
logger_debug = logging.getLogger("cyberdrop_dl_debug")

MAX_NAME_LENGTHS = {"FILE": 95, "FOLDER": 60}

DEBUG_VAR = False
CONSOLE_DEBUG_VAR = False

global LOG_OUTPUT_TEXT
LOG_OUTPUT_TEXT = "```diff\n"

RAR_MULTIPART_PATTERN = r'^part\d+'
_7Z_FILE_EXTENSIONS = {"7z","tar","gz","bz2","zip"}

FILE_FORMATS = {
    'Images': {
        '.jpg', '.jpeg', '.png', '.gif',
        '.gifv', '.webp', '.jpe', '.svg',
        '.jfif', '.tif', '.tiff', '.jif',
    },
    'Videos': {
        '.mpeg', '.avchd', '.webm', '.mpv',
        '.swf', '.avi', '.m4p', '.wmv',
        '.mp2', '.m4v', '.qt', '.mpe',
        '.mp4', '.flv', '.mov', '.mpg',
        '.ogg', '.mkv', '.mts', '.ts',
        '.f4v'
    },
    'Audio': {
        '.mp3', '.flac', '.wav', '.m4a',
    },
    'Text': {
        '.htm', '.html', '.md', '.nfo',
        '.txt',
    }
}


def error_handling_wrapper(func):
    """Wrapper handles errors for url scraping"""

    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        link = args[0] if isinstance(args[0], URL) else args[0].url

        try:
            return await func(self, *args, **kwargs)
        except NoExtensionFailure:
            await log(f"Scrape Failed: {link} (No File Extension)", 40)
            await self.manager.log_manager.write_scrape_error_log(link, " No File Extension")
            await self.manager.progress_manager.scrape_stats_progress.add_failure("No File Extension")
        except PasswordProtected as e:
            await log(f"Scrape Failed: {link} (Password Protected)", 40)
            parent_url = e.scrape_item.parents[0] if e.scrape_item.parents else None
            await self.manager.log_manager.write_unsupported_urls_log(link,parent_url)
            await self.manager.progress_manager.scrape_stats_progress.add_failure("Password Protected")
        except FailedLoginFailure:
            await log(f"Scrape Failed: {link} (Failed Login)", 40)
            await self.manager.log_manager.write_scrape_error_log(link, " Failed Login")
            await self.manager.progress_manager.scrape_stats_progress.add_failure("Failed Login")
        except InvalidContentTypeFailure:
            await log(f"Scrape Failed: {link} (Invalid Content Type Received)", 40)
            await self.manager.log_manager.write_scrape_error_log(link, " Invalid Content Type Received")
            await self.manager.progress_manager.scrape_stats_progress.add_failure("Invalid Content Type")
        except asyncio.TimeoutError:
            await log(f"Scrape Failed: {link} (Timeout)", 40)
            await self.manager.log_manager.write_scrape_error_log(link, " Timeout")
            await self.manager.progress_manager.scrape_stats_progress.add_failure("Timeout")
        except Exception as e:
            if hasattr(e, 'status'):
                if hasattr(e, 'message'):
                    await log(f"Scrape Failed: {link} ({e.status} - {e.message})", 40)
                    await self.manager.log_manager.write_scrape_error_log(link, f" {e.status} - {e.message}")
                else:
                    await log(f"Scrape Failed: {link} ({e.status})", 40)
                    await self.manager.log_manager.write_scrape_error_log(link, f" {e.status}")
                await self.manager.progress_manager.scrape_stats_progress.add_failure(e.status)
            else:
                await log(f"Scrape Failed: {link} ({e})", 40, exc_info=True)
                await self.manager.log_manager.write_scrape_error_log(link, " See Log for Details")
                await self.manager.progress_manager.scrape_stats_progress.add_failure("Unknown")

    return wrapper


async def log(message: Union[str, Exception], level: int, sleep: int = None, **kwargs) -> None:
    """Simple logging function"""
    logger.log(level, message, **kwargs)
    if DEBUG_VAR:
        logger_debug.log(level, message, **kwargs)
    log_console(level, message, sleep=sleep)


async def log_debug(message: Union[str, Exception], level: int, sleep: int = None, *kwargs) -> None:
    """Simple logging function"""
    if DEBUG_VAR:
        logger_debug.log(level, message.encode('ascii', 'ignore').decode('ascii'), *kwargs)


async def log_debug_console(message: Union [str, Exception], level: int, sleep: int = None):
    if CONSOLE_DEBUG_VAR:
        log_console(level, message.encode('ascii', 'ignore').decode('ascii'), sleep=sleep)


async def log_with_color(message: str, style: str, level: int, *kwargs) -> None:
    """Simple logging function with color"""
    global LOG_OUTPUT_TEXT
    logger.log(level, message, *kwargs)
    if DEBUG_VAR:
        logger_debug.log(level, message, *kwargs)
    rich.print(f"[{style}]{message}[/{style}]")
    LOG_OUTPUT_TEXT += f"[{style}]{message}\n"


async def get_log_output_text() -> str:
    global LOG_OUTPUT_TEXT
    return LOG_OUTPUT_TEXT + "```"


"""~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""


class CustomHTTPStatus(IntEnum):
    WEB_SERVER_IS_DOWN = 521
    IM_A_TEAPOT = 418
    DDOS_GUARD = 429


"""~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""


async def sanitize(name: str) -> str:
    """Simple sanitization to remove illegal characters"""
    return re.sub(r'[<>:"/\\|?*\']', "", name).strip()


async def sanitize_folder(title: str) -> str:
    """Simple sanitization to remove illegal characters from titles and trim the length to be less than 60 chars"""
    title = title.replace("\n", "").strip()
    title = title.replace("\t", "").strip()
    title = re.sub(' +', ' ', title)
    title = re.sub(r'[\\*?:"<>|/]', "-", title)
    title = re.sub(r'\.{2,}', ".", title)
    title = title.rstrip(".").strip()

    if "(" in title and ")" in title:
        new_title = title.rsplit("(")[0].strip()
        new_title = new_title[:MAX_NAME_LENGTHS['FOLDER']].strip()
        domain_part = title.rsplit("(")[1].strip()
        title = f"{new_title} ({domain_part}"
    else:
        title = title[:MAX_NAME_LENGTHS['FOLDER']].strip()
    return title


async def get_filename_and_ext(filename: str, forum: bool = False) -> Tuple[str, str]:
    """Returns the filename and extension of a given file, throws NoExtensionFailure if there is no extension"""
    filename_parts = filename.rsplit('.', 1)
    if len(filename_parts) == 1:
        raise NoExtensionFailure()
    if filename_parts[-1].isnumeric() and forum:
        filename_parts = filename_parts[0].rsplit('-', 1)
    if len(filename_parts[-1]) > 5:
        raise NoExtensionFailure()
    ext = "." + filename_parts[-1].lower()
    filename = filename_parts[0][:MAX_NAME_LENGTHS['FILE']] if len(filename_parts[0]) > MAX_NAME_LENGTHS['FILE'] else \
        filename_parts[0]
    filename = filename.strip()
    filename = filename.rstrip(".")
    filename = await sanitize(filename + ext)
    return filename, ext


async def get_download_path(manager: Manager, scrape_item: ScrapeItem, domain: str) -> Path:
    """Returns the path to the download folder"""
    download_dir = manager.path_manager.download_dir

    if scrape_item.retry:
        return scrape_item.retry_path

    if scrape_item.parent_title and scrape_item.part_of_album:
        return download_dir / scrape_item.parent_title
    elif scrape_item.parent_title:
        return download_dir / scrape_item.parent_title / f"Loose Files ({domain})"
    else:
        return download_dir / f"Loose Files ({domain})"

async def _is_number(ext: str):
    try:
        int(ext.rsplit(".", 1)[-1])
        return True
    except ValueError:
        return False

async def remove_id(manager: Manager, filename: str, ext: str) -> Tuple[str, str]:
    """Removes the additional string some websites adds to the end of every filename"""
    original_filename = filename
    if manager.config_manager.settings_data["Download_Options"]["remove_generated_id_from_filenames"]:
        original_filename = filename
        filename = filename.rsplit(ext, 1)[0]
        filename = filename.rsplit("-", 1)[0]
        tail = filename.rsplit("-", 1)[-1]
        if re.match(RAR_MULTIPART_PATTERN, tail) and ext == ".rar" and "-" in filename:
            filename , part = filename.rsplit("-", 1)
            filename = f"{filename}.{part}"
        elif await _is_number(ext) and tail in _7Z_FILE_EXTENSIONS and "-" in filename:
            filename , _7z_ext = filename.rsplit("-", 1)
            filename = f"{filename}.{_7z_ext}"
        if not filename.endswith(ext):
            filename = filename + ext
    return original_filename, filename


"""~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""


async def purge_dir_tree(dirname: Path) -> None:
    """Purges empty files and directories"""

    for file in dirname.rglob('*'):
        if file.is_file() and file.stat().st_size == 0:
            file.unlink()

    for parent, dirs, _ in os.walk(dirname, topdown=False):
        for child_dir in dirs:
            try:
                (Path(parent) / child_dir).rmdir()
            except OSError:
                pass #skip if folder is not empty


async def check_partials_and_empty_folders(manager: Manager):
    """Checks for partial downloads and empty folders"""
    if manager.config_manager.settings_data['Runtime_Options']['delete_partial_files']:
        await log_with_color("Deleting partial downloads...", "bold_red", 20)
        partial_downloads = manager.path_manager.download_dir.rglob("*.part")
        for file in partial_downloads:
            file.unlink(missing_ok=True)
    elif not manager.config_manager.settings_data['Runtime_Options']['skip_check_for_partial_files']:
        await log_with_color("Checking for partial downloads...", "yellow", 20)
        partial_downloads = any(f.is_file() for f in manager.path_manager.download_dir.rglob("*.part"))
        if partial_downloads:
            await log_with_color("There are partial downloads in the downloads folder", "yellow", 20)
        temp_downloads = any(Path(f).is_file() for f in await manager.db_manager.temp_table.get_temp_names())
        if temp_downloads:
            await log_with_color("There are partial downloads from the previous run, please re-run the program.",
                                "yellow", 20)

    if not manager.config_manager.settings_data['Runtime_Options']['skip_check_for_empty_folders']:
        await log_with_color("Checking for empty folders...", "yellow", 20)
        await purge_dir_tree(manager.path_manager.download_dir)
        if isinstance(manager.path_manager.sorted_dir, Path):
            await purge_dir_tree(manager.path_manager.sorted_dir)


async def check_latest_pypi(log_to_console: bool = True, call_from_ui: bool = False) -> Tuple[str]:
    """Checks if the current version is the latest version"""
    from cyberdrop_dl import __version__ as current_version
    import json
    import urllib.request

    contents = urllib.request.urlopen('https://pypi.org/pypi/cyberdrop-dl-patched/json').read()
    data = json.loads(contents)
    latest_version = data['info']['version']
    releases = data['releases'].keys()


    if current_version not in releases:
        message = "You are on an unreleased version, skipping version check"
        if call_from_ui:
            rich.print(message)
        elif log_to_console:
            await log_with_color(message, "bold_yellow", 30)
        return current_version, latest_version


    tags = {'dev': 'Development', 'pre': 'Pre-Release', 'post': 'Post-Release', 
            'rc': 'Release Candidate', 'a': 'Alpha', 'b': 'Beta'}

    latest_version_rich = f"[b cyan]{latest_version}[/b cyan]"
    
    for tag in tags:
        if tag in current_version:
            match = re.match(r'(\d+)\.(\d+)\.(\d+)(?:\.([a-z]+)\d+|([a-z]+)\d+)', current_version)
            if match:
                major_version, minor_version, patch_version, dot_tag, no_dot_tag = match.groups()
                test_tag = dot_tag if dot_tag else no_dot_tag

                rough_matches = [release for release in releases 
                                if re.match(rf'{major_version}\.{minor_version}\.{patch_version}(\.{test_tag}\d+|{test_tag}\d+)', release)]
                latest_testing_version = max(rough_matches, key=lambda x: int(re.search(r'(\d+)$', x).group()))
                latest_testing_version_rich = f"[b cyan]{latest_testing_version}[/b cyan]"

                if current_version != latest_testing_version:
                    message = f"A new {tags.get(test_tag, 'Testing').lower()} version of Cyberdrop-DL is available: "
                    if call_from_ui:
                        rich.print(f"{message}{latest_testing_version_rich}")
                    elif log_to_console:
                        await log_with_color(f"{message}{latest_testing_version}", "bold_red", 30)
                else:
                    if call_from_ui:
                        rich.print(f"You are currently on the latest {tags.get(test_tag, 'Testing').lower()} version of [b cyan]{major_version}.{minor_version}.{patch_version}[/b cyan]")

                return current_version, latest_testing_version

    if current_version != latest_version:
        message = f"A new version of Cyberdrop-DL is available: "
        if call_from_ui:
            rich.print(f"{message}{latest_version_rich}")
        elif log_to_console:
            await log_with_color(f"{message}{latest_version}", "bold_red", 30)
    else:
        if call_from_ui:
            rich.print("You are currently on the latest version of Cyberdrop-DL")

    return current_version, latest_version
