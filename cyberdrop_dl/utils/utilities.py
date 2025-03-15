from __future__ import annotations

import contextlib
import json
import os
import platform
import re
import subprocess
from functools import partial, wraps
from pathlib import Path
from typing import TYPE_CHECKING

import aiofiles
import rich
from aiohttp import ClientConnectorError, ClientSession, FormData
from yarl import URL

from cyberdrop_dl.clients.errors import (
    CDLBaseError,
    ErrorLogMessage,
    InvalidExtensionError,
    NoExtensionError,
    get_origin,
)
from cyberdrop_dl.utils import constants
from cyberdrop_dl.utils.logger import log, log_debug, log_spacer, log_with_color

if TYPE_CHECKING:
    from collections.abc import Callable

    from rich.text import Text

    from cyberdrop_dl.downloader.downloader import Downloader
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.scraper.crawler import Crawler
    from cyberdrop_dl.utils.data_enums_classes.url_objects import MediaItem, ScrapeItem


subprocess_get_text = partial(subprocess.run, capture_output=True, text=True, check=False)


def error_handling_wrapper(func: Callable) -> Callable:
    """Wrapper handles errors for url scraping."""

    @wraps(func)
    async def wrapper(self: Crawler | Downloader, *args, **kwargs):
        item: ScrapeItem | MediaItem | URL = args[0]
        link: URL = item if isinstance(item, URL) else item.url
        origin = exc_info = None
        link_to_show: URL | str = ""
        try:
            return await func(self, *args, **kwargs)
        except CDLBaseError as e:
            error_log_msg = ErrorLogMessage(e.ui_failure, str(e))
            origin = e.origin
            e_url: URL | str | None = getattr(e, "url", None)
            link_to_show = e_url or link_to_show
        except TimeoutError:
            error_log_msg = ErrorLogMessage("Timeout")
        except ClientConnectorError as e:
            ui_failure = "Client Connector Error"
            # link_to_show = link.with_host(e.host) # For bunkr and jpg5, to make sure the log message matches the actual URL we tried to connect
            log_msg = f"Can't connect to {link}. If you're using a VPN, try turning it off \n  {e!s}"
            error_log_msg = ErrorLogMessage(ui_failure, log_msg)
        except Exception as e:
            exc_info = e
            error_log_msg = ErrorLogMessage.from_unknown_exc(e)

        link_to_show = link_to_show or link
        origin = origin or get_origin(item)
        log_prefix = getattr(self, "log_prefix", None)
        if log_prefix:  # This error came from a Downloader
            await self.write_download_error(item, error_log_msg, exc_info)  # type: ignore
            return

        log(f"Scrape Failed: {link_to_show} ({error_log_msg.main_log_msg})", 40, exc_info=exc_info)
        await self.manager.log_manager.write_scrape_error_log(link_to_show, error_log_msg.csv_log_msg, origin)
        self.manager.progress_manager.scrape_stats_progress.add_failure(error_log_msg.ui_failure)

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
        new_title, domain_part = title.rsplit("(", 1)
        new_title = truncate_str(new_title, constants.MAX_NAME_LENGTHS["FOLDER"])
        return f"{new_title} ({domain_part.strip()}"
    return truncate_str(title, constants.MAX_NAME_LENGTHS["FOLDER"])


def truncate_str(text: str, max_length: int = 0) -> str:
    """Truncates and strip strings to the desired len.

    If `max_length` is 0, uses `constants.MAX_NAME_LENGTHS["FILE"]`"""
    truncate_to = max_length or constants.MAX_NAME_LENGTHS["FILE"]
    if len(text) > truncate_to:
        return text[:truncate_to].strip()
    return text.strip()


def get_filename_and_ext(filename: str, forum: bool = False) -> tuple[str, str]:
    """Returns the filename and extension of a given file, throws `NoExtensionError` if there is no extension."""
    filename_as_path = Path(filename)
    if not filename_as_path.suffix:
        raise NoExtensionError
    ext_no_dot = filename_as_path.suffix.split(".")[1]
    if ext_no_dot.isdigit() and forum and "-" in filename:
        name, ext = filename_as_path.name.rsplit("-", 1)
        ext = ext.rsplit(".")[0]
        ext_w_dot = f".{ext}".lower()
        if ext_w_dot not in constants.MEDIA_EXTENSIONS:
            raise InvalidExtensionError
        filename_as_path = Path(f"{name}.{ext}")
    if len(filename_as_path.suffix) > 5:
        raise InvalidExtensionError

    filename_as_path = filename_as_path.with_suffix(filename_as_path.suffix.lower())
    filename_as_str = truncate_str(filename_as_path.stem.removesuffix(".")) + filename_as_path.suffix
    filename_as_path = Path(sanitize_filename(filename_as_str))
    return filename_as_path.name, filename_as_path.suffix


def get_download_path(manager: Manager, scrape_item: ScrapeItem, domain: str) -> Path:
    """Returns the path to the download folder."""
    download_dir = manager.path_manager.download_folder

    if scrape_item.retry:
        return scrape_item.retry_path  # type: ignore
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
        plain_line: str | None = style_map.get(span.style) or style_map.get(default_style_map_key)
        if plain_line:
            plain_text += plain_line.format(span_text) + "\n"

    return plain_text


def purge_dir_tree(dirname: Path) -> None:
    """Purges empty files and directories efficiently."""
    if not dirname.is_dir():
        return

    # Use os.walk() to remove empty files and directories in a single pass
    for dirpath, _dirnames, filenames in os.walk(dirname, topdown=False):
        dir_path = Path(dirpath)

        # Remove empty files
        for file_name in filenames:
            file_path = dir_path / file_name
            if file_path.exists() and file_path.stat().st_size == 0:
                file_path.unlink()

        # Remove empty directories
        with contextlib.suppress(OSError):
            dir_path.rmdir()


def check_partials_and_empty_folders(manager: Manager):
    """Checks for partial downloads, deletes partial files and empty folders."""
    settings = manager.config_manager.settings_data.runtime_options
    if settings.delete_partial_files:
        delete_partial_files(manager)
    if not settings.skip_check_for_partial_files:
        check_for_partial_files(manager)
    if not settings.skip_check_for_empty_folders:
        delete_empty_folders(manager)


def delete_partial_files(manager: Manager):
    """Deletes partial download files recursively."""
    log_red("Deleting partial downloads...")
    for file in manager.path_manager.download_folder.rglob("*.part"):
        file.unlink(missing_ok=True)


def check_for_partial_files(manager: Manager):
    """Checks if there are partial downloads in any subdirectory and logs if found."""
    log_yellow("Checking for partial downloads...")
    if next(manager.path_manager.download_folder.rglob("*.part"), None) is not None:
        log_yellow("There are partial downloads in the downloads folder")


def delete_empty_folders(manager: Manager):
    """Deletes empty folders efficiently."""
    log_yellow("Checking for empty folders...")
    purge_dir_tree(manager.path_manager.download_folder)

    sorted_folder = manager.path_manager.sorted_folder
    if sorted_folder and manager.config_manager.settings_data.sorting.sort_downloads:
        purge_dir_tree(sorted_folder)


async def send_webhook_message(manager: Manager) -> None:
    """Outputs the stats to a code block for webhook messages."""
    webhook = manager.config_manager.settings_data.logs.webhook

    if not webhook:
        return

    rich.print("\nSending Webhook Notifications.. ")
    url: URL = webhook.url.get_secret_value()  # type: ignore
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
            json_resp_str = json.dumps(json_resp, indent=4)
            result_to_log = constants.NotificationResult.FAILED.value, json_resp_str

        log_spacer(10, log_to_console=False)
        rich.print("Webhook Notifications Results:", *result)
        logger = log_debug if successful else log
        result_to_log = "\n".join(map(str, result_to_log))
        logger(f"Webhook Notifications Results: {result_to_log}")


def open_in_text_editor(file_path: Path) -> bool | None:
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
        subprocess.call(["micro", "-keymenu", "true", file_path])

    elif subprocess.call(["which", "nano"], stdout=subprocess.DEVNULL) == 0:
        subprocess.call(["nano", file_path])

    elif subprocess.call(["which", "vim"], stdout=subprocess.DEVNULL) == 0:
        subprocess.call(["vim", file_path])

    else:
        raise ValueError


def set_default_app_if_none(file_path: Path) -> bool:
    mimetype = xdg_mime_query("filetype", str(file_path))
    if not mimetype:
        return False

    default_app = xdg_mime_query("default", mimetype)
    if default_app:
        return True

    text_default = xdg_mime_query("default", "text/plain")
    if text_default:
        return subprocess.call(["xdg-mime", "default", text_default, mimetype]) == 0

    return False


def xdg_mime_query(*args) -> str:
    assert args
    arg_list = ["xdg-mime", "query", *args]
    return subprocess_get_text(arg_list).stdout.strip()


log_cyan = partial(log_with_color, style="cyan", level=20)
log_yellow = partial(log_with_color, style="yellow", level=20)
log_green = partial(log_with_color, style="green", level=20)
log_red = partial(log_with_color, style="red", level=20)
