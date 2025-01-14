from __future__ import annotations

import contextlib
import json
import os
import platform
import re
import subprocess
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING

import aiofiles
import rich
from aiohttp import ClientConnectorError, ClientSession, FormData
from rich.text import Text
from yarl import URL

from cyberdrop_dl.clients.errors import CDLBaseError, NoExtensionError
from cyberdrop_dl.utils import constants
from cyberdrop_dl.utils.logger import log, log_debug, log_spacer, log_with_color

if TYPE_CHECKING:
    from collections.abc import Callable

    from cyberdrop_dl.downloader.downloader import Downloader
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.scraper.crawler import Crawler
    from cyberdrop_dl.utils.data_enums_classes.url_objects import MediaItem, ScrapeItem


def error_handling_wrapper(func: Callable) -> Callable:
    """Wrapper handles errors for url scraping."""

    @wraps(func)
    async def wrapper(self: Crawler | Downloader, *args, **kwargs):
        item: ScrapeItem | MediaItem | URL = args[0]
        link = item if isinstance(item, URL) else item.url
        origin = exc_info = None
        try:
            return await func(self, *args, **kwargs)
        except CDLBaseError as e:
            log_message_short = e_ui_failure = e.ui_message
            log_message = f"{e.ui_message} - {e.message}" if e.ui_message != e.message else e.message
            origin = e.origin
        except TimeoutError:
            log_message_short = log_message = e_ui_failure = "Timeout"
        except ClientConnectorError as e:
            log_message_short = e_ui_failure = "ClientConnectorError"
            log_message = f"Can't connect to {link}. If you're using a VPN, try turning it off \n  {e!s}"
        except Exception as e:
            exc_info = e
            if hasattr(e, "status") and hasattr(e, "message"):
                log_message_short = log_message = e_ui_failure = f"{e.status} - {e.message}"
            else:
                log_message = str(e)
                log_message_short = "See Log for Details"
                e_ui_failure = "Unknown"

        log_prefix = getattr(self, "log_prefix", None)
        log(f"{log_prefix or 'Scrape'} Failed: {link} ({log_message})", 40, exc_info=exc_info)
        if log_prefix:
            self.attempt_task_removal(item)
            await self.manager.log_manager.write_download_error_log(link, log_message_short, origin or item.referer)
            self.manager.progress_manager.download_stats_progress.add_failure(e_ui_failure)
            self.manager.progress_manager.download_progress.add_failed()
            return None

        await self.manager.log_manager.write_scrape_error_log(link, log_message_short, origin)
        self.manager.progress_manager.scrape_stats_progress.add_failure(e_ui_failure)
        return None

    return wrapper


"""~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""


def sanitize_filename(name: str) -> str:
    """Simple sanitization to remove illegal characters from filename."""
    return re.sub(constants.SANITIZE_FILENAME_PATTERN, "", name).strip()


def sanitize_folder(title: str) -> str:
    """Simple sanitization to remove illegal characters from titles and trim the length to be less than 60 chars."""
    title = title.replace("\n", "").strip()
    title = title.replace("\t", "").strip()
    title = re.sub(" +", " ", title)
    title = re.sub(r'[\\*?:"<>|/]', "-", title)
    title = re.sub(r"\.{2,}", ".", title)
    title = title.rstrip(".").strip()

    if all(char in title for char in ("(", ")")):
        new_title = title.rsplit("(")[0].strip()
        new_title = new_title[: constants.MAX_NAME_LENGTHS["FOLDER"]].strip()
        domain_part = title.rsplit("(")[1].strip()
        title = f"{new_title} ({domain_part}"
    else:
        title = title[: constants.MAX_NAME_LENGTHS["FOLDER"]].strip()
    return title


def get_filename_and_ext(filename: str, forum: bool = False) -> tuple[str, str]:
    """Returns the filename and extension of a given file, throws `NoExtensionError` if there is no extension."""
    filename_parts = filename.rsplit(".", 1)
    if len(filename_parts) == 1:
        raise NoExtensionError
    if filename_parts[-1].isnumeric() and forum:
        filename_parts = filename_parts[0].rsplit("-", 1)
    if len(filename_parts[-1]) > 5:
        raise NoExtensionError
    ext = "." + filename_parts[-1].lower()
    filename = filename_parts[0]
    if len(filename) > constants.MAX_NAME_LENGTHS["FILE"]:
        filename = filename_parts[0][: constants.MAX_NAME_LENGTHS["FILE"]]

    filename = filename.strip().rstrip(".")
    filename = sanitize_filename(filename + ext)
    return filename, ext


def get_download_path(manager: Manager, scrape_item: ScrapeItem, domain: str) -> Path:
    """Returns the path to the download folder."""
    download_dir = manager.path_manager.download_folder

    if scrape_item.retry:
        return scrape_item.retry_path
    if scrape_item.parent_title and scrape_item.part_of_album:
        return download_dir / scrape_item.parent_title
    if scrape_item.parent_title:
        return download_dir / scrape_item.parent_title / f"Loose Files ({domain})"
    return download_dir / f"Loose Files ({domain})"


def remove_file_id(manager: Manager, filename: str, ext: str) -> tuple[str, str]:
    """Removes the additional string some websites adds to the end of every filename."""
    original_filename = filename
    if not manager.config_manager.settings_data.download_options.remove_generated_id_from_filenames:
        return original_filename, filename

    filename = filename.rsplit(ext, 1)[0]
    filename = filename.rsplit("-", 1)[0]
    tail_no_dot = filename.rsplit("-", 1)[-1]
    ext_no_dot = ext.rsplit(".", 1)[-1]
    tail = f".{tail_no_dot}"
    if re.match(constants.RAR_MULTIPART_PATTERN, tail_no_dot) and ext == ".rar" and "-" in filename:
        filename, part = filename.rsplit("-", 1)
        filename = f"{filename}.{part}"
    elif ext_no_dot.isdigit() and tail in constants.FILE_FORMATS["7z"] and "-" in filename:
        filename, _7z_ext = filename.rsplit("-", 1)
        filename = f"{filename}.{_7z_ext}"
    if not filename.endswith(ext):
        filename = filename + ext
    return original_filename, filename


"""~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""


def clear_term():
    os.system("cls" if os.name == "nt" else "clear")


def parse_rich_text_by_style(text: Text, style_map: dict, default_style_map_key: str = "default") -> str:
    """Returns `text` as a plain str, parsing each tag in text acording to `style_map`."""
    plain_text = ""
    for span in text.spans:
        span_text = text.plain[span.start : span.end].rstrip("\n")
        plain_line: str = style_map.get(span.style) or style_map.get(default_style_map_key)
        if plain_line:
            plain_text += plain_line.format(span_text) + "\n"

    return plain_text


def purge_dir_tree(dirname: Path) -> None:
    """Purges empty files and directories."""
    for file in dirname.rglob("*"):
        if file.is_file() and file.stat().st_size == 0:
            file.unlink()

    for dirpath, _, _ in os.walk(dirname, topdown=False):
        dir_to_remove = Path(dirpath)
        with contextlib.suppress(OSError):
            dir_to_remove.rmdir()


async def check_partials_and_empty_folders(manager: Manager) -> None:
    """Checks for partial downloads and empty folders."""
    if manager.config_manager.settings_data.runtime_options.delete_partial_files:
        log_with_color("Deleting partial downloads...", "bold_red", 20)
        partial_downloads = manager.path_manager.download_folder.rglob("*.part")
        for file in partial_downloads:
            file.unlink(missing_ok=True)

    elif not manager.config_manager.settings_data.runtime_options.skip_check_for_partial_files:
        log_with_color("Checking for partial downloads...", "yellow", 20)
        partial_downloads = any(manager.path_manager.download_folder.rglob("*.part"))
        if partial_downloads:
            log_with_color("There are partial downloads in the downloads folder", "yellow", 20)

    if not manager.config_manager.settings_data.runtime_options.skip_check_for_empty_folders:
        log_with_color("Checking for empty folders...", "yellow", 20)
        purge_dir_tree(manager.path_manager.download_folder)
        if (
            isinstance(manager.path_manager.sorted_folder, Path)
            and manager.config_manager.settings_data.sorting.sort_downloads
        ):
            purge_dir_tree(manager.path_manager.sorted_folder)


def check_latest_pypi(log_to_console: bool = True, call_from_ui: bool = False) -> tuple[str, str]:
    """Checks if the current version is the latest version."""

    from requests import request

    from cyberdrop_dl import __version__ as current_version

    with request("GET", constants.PYPI_JSON_URL, timeout=30) as response:
        contents = response.content

    data: dict[str, dict] = json.loads(contents)
    latest_version: str = data["info"]["version"]
    releases = data["releases"].keys()
    message = color = None
    level = 30
    is_prerelease, latest_testing_version, message = check_prelease_version(current_version, releases)

    if current_version not in releases:
        message = Text("You are on an unreleased version, skipping version check")
        color = "bold_yellow"
    elif is_prerelease:
        latest_version = latest_testing_version
        color = "bold_red"
    elif current_version != latest_version:
        message = f"A new version of Cyberdrop-DL is available: [cyan]{latest_version}[/cyan]"
        message = Text.from_markup(message)
    else:
        message = Text.from_markup("You are currently on the latest version of Cyberdrop-DL :white_check_mark:")
        level = 20

    if call_from_ui:
        rich.print(message)
    elif log_to_console:
        log_with_color(message.plain, color, level, show_in_stats=False)

    return current_version, latest_version


def check_prelease_version(current_version: str, releases: list[str]) -> tuple[str, Text]:
    match = re.match(constants.PRELEASE_VERSION_PATTERN, current_version)
    latest_testing_version = message = None

    if constants.RUNNING_PRERELEASE and match:
        major_version, minor_version, patch_version, dot_tag, no_dot_tag = match.groups()
        test_tag = dot_tag if dot_tag else no_dot_tag
        regex_str = rf"{major_version}\.{minor_version}\.{patch_version}(\.{test_tag}\d+|{test_tag}\d+)"
        rough_matches = [release for release in releases if re.match(regex_str, release)]
        latest_testing_version = max(rough_matches, key=lambda x: int(re.search(r"(\d+)$", x).group()))  # type: ignore
        ui_tag = constants.PRERELEASE_TAGS.get(test_tag, "Testing").lower()

        if current_version != latest_testing_version:
            message = f"A new {ui_tag} version of Cyberdrop-DL is available: "
            message = Text(message).append_text(Text(latest_testing_version, style="cyan"))
        else:
            message = f"You are currently on the latest {ui_tag} version of [b cyan]{major_version}.{minor_version}.{patch_version}[/b cyan]"
            message = Text.from_markup(message)

    return constants.RUNNING_PRERELEASE, latest_testing_version, message


async def send_webhook_message(manager: Manager) -> None:
    """Outputs the stats to a code block for webhook messages."""
    webhook = manager.config_manager.settings_data.logs.webhook

    if not webhook:
        return

    rich.print("\nSending Webhook Notifications.. ")
    url = webhook.url.get_secret_value()
    text: Text = constants.LOG_OUTPUT_TEXT
    plain_text = parse_rich_text_by_style(text, constants.STYLE_TO_DIFF_FORMAT_MAP)
    main_log = manager.path_manager.main_log

    form = FormData()

    if "attach_logs" in webhook.tags and main_log.is_file():
        if main_log.stat().st_size <= 25 * 1024 * 1024:
            async with aiofiles.open(main_log, "rb") as f:
                form.add_field("file", await f.read(), filename=main_log.name)

        else:
            plain_text += "\n\nWARNING: log file too large to send as attachment\n"

    form.add_fields(
        ("content", f"```diff\n{plain_text}```"),
        ("username", "CyberDrop-DL"),
    )

    async with ClientSession() as session, session.post(url, data=form) as response:
        successful = 200 <= response.status <= 300
        result = [constants.NotificationResult.SUCCESS.value]
        result_to_log = result
        if not successful:
            json_resp: dict = await response.json()
            if "content" in json_resp:
                json_resp.pop("content")
            json_resp = json.dumps(json_resp, indent=4)
            result_to_log = constants.NotificationResult.FAILED.value, json_resp

        log_spacer(10, log_to_console=False)
        rich.print("Webhook Notifications Results:", *result)
        logger = log_debug if successful else log
        result_to_log = "\n".join(map(str, result_to_log))
        logger(f"Webhook Notifications Results: {result_to_log}")


def open_in_text_editor(file_path: Path) -> bool:
    """Opens file in OS text editor."""
    using_desktop_enviroment = (
        any(var in os.environ for var in ("DISPLAY", "WAYLAND_DISPLAY")) and "SSH_CONNECTION" not in os.environ
    )
    default_editor = os.environ.get("EDITOR")
    if platform.system() == "Darwin":
        subprocess.Popen(["open", "-a", "TextEdit", file_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    elif platform.system() == "Windows":
        subprocess.Popen(["notepad.exe", file_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    elif using_desktop_enviroment and set_default_app_if_none(file_path):
        subprocess.Popen(["xdg-open", file_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    elif default_editor:
        subprocess.call([default_editor, file_path])

    elif subprocess.call(["which", "micro"], stdout=subprocess.DEVNULL) == 0:
        subprocess.call(["micro", file_path])

    elif subprocess.call(["which", "nano"], stdout=subprocess.DEVNULL) == 0:
        subprocess.call(["nano", file_path])

    elif subprocess.call(["which", "vim"], stdout=subprocess.DEVNULL) == 0:
        subprocess.call(["vim", file_path])

    else:
        raise ValueError


def set_default_app_if_none(file_path: Path) -> bool:
    mimetype = subprocess.run(
        ["xdg-mime", "query", "filetype", str(file_path)],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if not mimetype:
        return False

    default_app = subprocess.run(
        ["xdg-mime", "query", "default", mimetype],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if default_app:
        return True

    text_default = subprocess.run(
        ["xdg-mime", "query", "default", "text/plain"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if text_default:
        return subprocess.call(["xdg-mime", "default", text_default, mimetype]) == 0

    return False
