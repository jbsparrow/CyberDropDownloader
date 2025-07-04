from __future__ import annotations

from dataclasses import field
from functools import wraps
from typing import TYPE_CHECKING, ParamSpec, TypeVar

from myjdapi import myjdapi

from cyberdrop_dl.exceptions import JDownloaderError
from cyberdrop_dl.utils.logger import log

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
    from cyberdrop_dl.managers.manager import Manager


P = ParamSpec("P")
R = TypeVar("R")


def error_wrapper(func: Callable[P, R]) -> Callable[P, R | None]:
    """Wrapper handles limits for scrape session."""

    @wraps(func)
    def wrapper(*args, **kwargs) -> R | None:
        self: JDownloader = args[0]
        try:
            return func(*args, **kwargs)
        except JDownloaderError as e:
            msg = e.message

        except myjdapi.MYJDDeviceNotFoundException:
            msg = f"Device not found ({self.jdownloader_device})"

        except myjdapi.MYJDApiException as e:
            msg = e

        log(f"Failed JDownloader setup: {msg}", 40)
        self.enabled = False
        return None

    return wrapper


class JDownloader:
    """Class that handles connecting and passing links to JDownloader."""

    def __init__(self, manager: Manager) -> None:
        self.enabled = manager.config_manager.settings_data.runtime_options.send_unsupported_to_jdownloader
        self.jdownloader_device = manager.config_manager.authentication_data.jdownloader.device
        self.jdownloader_username = manager.config_manager.authentication_data.jdownloader.username
        self.jdownloader_password = manager.config_manager.authentication_data.jdownloader.password
        self.jdownloader_download_dir = (
            manager.config_manager.settings_data.runtime_options.jdownloader_download_dir
            or manager.path_manager.download_folder
        )
        self.jdownloader_autostart = manager.config_manager.settings_data.runtime_options.jdownloader_autostart
        self.jdownloader_download_dir = self.jdownloader_download_dir.resolve()
        self.jdownloader_agent = field(init=False)

    @error_wrapper
    def jdownloader_setup(self) -> None:
        """Setup function for JDownloader."""
        if not all((self.jdownloader_username, self.jdownloader_password, self.jdownloader_device)):
            msg = "JDownloader credentials were not provided."
            raise JDownloaderError(msg)
        jd = myjdapi.Myjdapi()
        jd.set_app_key("CYBERDROP-DL")
        jd.connect(self.jdownloader_username, self.jdownloader_password)
        self.jdownloader_agent = jd.get_device(self.jdownloader_device)

    def direct_unsupported_to_jdownloader(
        self,
        url: AbsoluteHttpURL,
        title: str,
        relative_download_path: Path | None = None,
    ) -> None:
        """Sends links to JDownloader."""
        try:
            assert self.jdownloader_agent is not None
            download_folder = self.jdownloader_download_dir
            if relative_download_path:
                download_folder = download_folder / relative_download_path
            self.jdownloader_agent.linkgrabber.add_links(
                [
                    {
                        "autostart": self.jdownloader_autostart,
                        "links": str(url),
                        "packageName": title if title else "Cyberdrop-DL",
                        "destinationFolder": str(download_folder.resolve()),
                        "overwritePackagizerRules": True,
                    },
                ],
            )
        except (AssertionError, myjdapi.MYJDException) as e:
            raise JDownloaderError(str(e)) from e
