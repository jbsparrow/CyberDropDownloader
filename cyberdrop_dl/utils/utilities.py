from __future__ import annotations

import contextlib
import os
import re
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING

import aiofiles
import apprise
import rich
from aiohttp import ClientSession, FormData
from rich.text import Text
from yarl import URL

from cyberdrop_dl.clients.errors import CDLBaseError, NoExtensionError
from cyberdrop_dl.managers.real_debrid.errors import RealDebridError
from cyberdrop_dl.utils import constants
from cyberdrop_dl.utils.logger import log, log_with_color

if TYPE_CHECKING:
    from collections.abc import Callable

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.scraper.crawler import Crawler
    from cyberdrop_dl.utils.dataclasses.url_objects import ScrapeItem


def error_handling_wrapper(func: Callable) -> None:
    """Wrapper handles errors for url scraping."""

    @wraps(func)
    async def wrapper(self: Crawler, *args, **kwargs):
        link = args[0] if isinstance(args[0], URL) else args[0].url
        origin = exc_info = None
        try:
            return await func(self, *args, **kwargs)
        except CDLBaseError as e:
            log_message_short = e_ui_failure = e.ui_message
            log_message = e.message
            origin = e.origin
        except RealDebridError as e:
            log_message_short = log_message = f"RealDebridError - {e.error}"
            e_ui_failure = f"RD - {e.error}"
        except TimeoutError:
            log_message_short = log_message = e_ui_failure = "Timeout"
        except Exception as e:  # noqa
            exc_info = e
            if hasattr(e, "status") and hasattr(e, "message"):
                log_message_short = log_message = e_ui_failure = f"{e.status} - {e.message}"
            else:
                log_message = str(e)
                log_message_short = "See Log for Details"
                e_ui_failure = "Unknown"

        log(f"Scrape Failed: {link} ({log_message})", 40, exc_info=exc_info)
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
    download_dir = manager.path_manager.download_dir

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
    if not manager.config_manager.settings_data["Download_Options"]["remove_generated_id_from_filenames"]:
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


def parse_bytes(size: int) -> tuple[int, str]:
    """Get human repr of bytes as a tuple of (VALUE , UNIT)."""
    for unit in ["B", "KB", "MB", "GB", "TB", "PB", "EB"]:
        if size < 1024:
            return size, unit
        size /= 1024
    return size, "YB"


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

    with contextlib.suppress(OSError):
        for parent, dirs, _ in os.walk(dirname, topdown=False):
            for child_dir in dirs:
                Path(parent).joinpath(child_dir).rmdir()


async def check_partials_and_empty_folders(manager: Manager) -> None:
    """Checks for partial downloads and empty folders."""
    if manager.config_manager.settings_data["Runtime_Options"]["delete_partial_files"]:
        log_with_color("Deleting partial downloads...", "bold_red", 20)
        partial_downloads = manager.path_manager.download_dir.rglob("*.part")
        for file in partial_downloads:
            file.unlink(missing_ok=True)

    elif not manager.config_manager.settings_data["Runtime_Options"]["skip_check_for_partial_files"]:
        log_with_color("Checking for partial downloads...", "yellow", 20)
        partial_downloads = any(f.is_file() for f in manager.path_manager.download_dir.rglob("*.part"))
        if partial_downloads:
            log_with_color("There are partial downloads in the downloads folder", "yellow", 20)
        temp_downloads = any(Path(f).is_file() for f in await manager.db_manager.temp_table.get_temp_names())
        if temp_downloads:
            msg = "There are partial downloads from the previous run, please re-run the program."
            log_with_color(msg, "yellow", 20)

    if not manager.config_manager.settings_data["Runtime_Options"]["skip_check_for_empty_folders"]:
        log_with_color("Checking for empty folders...", "yellow", 20)
        purge_dir_tree(manager.path_manager.download_dir)
        # if isinstance(manager.path_manager.sorted_dir, Path):
        #     purge_dir_tree(manager.path_manager.sorted_dir)


def check_latest_pypi(log_to_console: bool = True, call_from_ui: bool = False) -> tuple[str, str]:
    """Checks if the current version is the latest version."""
    import json

    from requests import request

    from cyberdrop_dl import __version__ as current_version

    with request("GET", constants.PYPI_JSON_URL, timeout=30) as response:
        contents = response.content

    data: dict[str, dict] = json.loads(contents)
    latest_version: str = data["info"]["version"]
    releases = data["releases"].keys()
    message = color = None
    level = 30
    is_prelease, message = check_prelease_version(current_version, releases)

    if current_version not in releases:
        message = Text("You are on an unreleased version, skipping version check")
        color = "bold_yellow"
    elif is_prelease:
        color = "bold_red"
    elif current_version != latest_version:
        message = f"A new version of Cyberdrop-DL is available: [cyan]{latest_version}[/cyan]"
        message = Text.from_markup(message)
    else:
        message = Text("You are currently on the latest version of Cyberdrop-DL")
        level = 20

    if call_from_ui:
        rich.print(message)
    elif log_to_console:
        log_with_color(message.plain, color, level, show_in_stats=False)

    return current_version, latest_version


def check_prelease_version(current_version: str, releases: list[str]) -> tuple[str, Text]:
    is_prelease = next((tag for tag in constants.PRELEASE_TAGS if tag in current_version), False)
    match = re.match(constants.PRELEASE_VERSION_PATTERN, current_version)
    latest_testing_version = message = None

    if is_prelease and match:
        major_version, minor_version, patch_version, dot_tag, no_dot_tag = match.groups()
        test_tag = dot_tag if dot_tag else no_dot_tag

        rough_matches = [
            release
            for release in releases
            if re.match(
                rf"{major_version}\.{minor_version}\.{patch_version}(\.{test_tag}\d+|{test_tag}\d+)",
                release,
            )
        ]
        latest_testing_version = max(rough_matches, key=lambda x: int(re.search(r"(\d+)$", x).group()))  # type: ignore
        latest_testing_version = Text(latest_testing_version, style="cyan")
        ui_tag = constants.PRELEASE_TAGS.get(test_tag, "Testing").lower()

        if current_version != latest_testing_version:
            message = f"A new {ui_tag} version of Cyberdrop-DL is available: "
            message = Text(message).append_text(latest_testing_version)
        else:
            message = f"You are currently on the latest {ui_tag} version of [b cyan]{major_version}.{minor_version}.{patch_version}[/b cyan]"
            message = Text.from_markup(message)

    return latest_testing_version, message


def sent_apprise_notifications(manager: Manager) -> None:
    apprise_file = manager.path_manager.config_dir / manager.config_manager.loaded_config / "apprise.txt"
    text: Text = constants.LOG_OUTPUT_TEXT
    constants.LOG_OUTPUT_TEXT = Text("")

    if not apprise_file.is_file():
        return

    with apprise_file.open(encoding="utf8") as file:
        lines = [line.strip() for line in file]

    if not lines:
        return

    rich.print("\nSending notifications.. ")
    apprise_obj = apprise.Apprise()
    for line in lines:
        parts = line.split("://", 1)[0].split("=", 1)
        url = line
        tags = "no_logs"
        if len(parts) == 2:
            tags, url = line.split("=", 1)
            tags = tags.split(",")
        apprise_obj.add(url, tag=tags)

    results = []
    result = apprise_obj.notify(
        body=text.plain,
        title="Cyberdrop-DL",
        body_format=apprise.NotifyFormat.TEXT,
        tag="no_logs",
    )

    if result is not None:
        results.append(result)

    result = apprise_obj.notify(
        body=text.plain,
        title="Cyberdrop-DL",
        body_format=apprise.NotifyFormat.TEXT,
        attach=str(manager.path_manager.main_log.resolve()),
        tag="attach_logs",
    )

    if result is not None:
        results.append(result)

    if not results:
        result = Text("No notifications sent", "yellow")
    if all(results):
        result = Text("Success", "green")
    elif any(results):
        result = Text("Partial Success", "yellow")
    else:
        result = Text("Failed", "bold red")

    rich.print("Apprise notifications results:", result)


async def send_webhook_message(manager: Manager) -> None:
    """Outputs the stats to a code block for webhook messages."""
    webhook_url: str = manager.config_manager.settings_data["Logs"]["webhook_url"]

    if not webhook_url:
        return

    url = webhook_url.strip()
    parts = url.split("://", 1)[0].split("=", 1)
    tags = ["no_logs"]
    if len(parts) == 2:
        tags, url = url.split("=", 1)
        tags = tags.split(",")

    url = URL(url)
    text: Text = constants.LOG_OUTPUT_TEXT
    plain_text = parse_rich_text_by_style(text, constants.STYLE_TO_DIFF_FORMAT_MAP)
    main_log = manager.path_manager.main_log

    form = FormData()

    if "attach_logs" in tags and main_log.is_file():
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
        await response.text()
