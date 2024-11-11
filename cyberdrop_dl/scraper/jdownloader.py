from __future__ import annotations

from dataclasses import field
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING

from myjdapi import myjdapi

from cyberdrop_dl.clients.errors import JDownloaderError
from cyberdrop_dl.utils.logger import log

if TYPE_CHECKING:
    from collections.abc import Callable

    from yarl import URL

    from cyberdrop_dl.managers.manager import Manager


def error_wrapper(func: Callable) -> None:
    """Wrapper handles limits for scrape session."""

    @wraps(func)
    def wrapper(self: JDownloader, *args, **kwargs) -> None:
        try:
            return func(self, *args, **kwargs)
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
        self.enabled = manager.config_manager.settings_data["Runtime_Options"]["send_unsupported_to_jdownloader"]
        self.jdownloader_device = manager.config_manager.authentication_data["JDownloader"]["jdownloader_device"]
        self.jdownloader_username = manager.config_manager.authentication_data["JDownloader"]["jdownloader_username"]
        self.jdownloader_password = manager.config_manager.authentication_data["JDownloader"]["jdownloader_password"]
        self.jdownloader_download_dir = manager.config_manager.settings_data["Runtime_Options"][
            "jdownloader_download_dir"
        ]
        self.jdownloader_autostart = manager.config_manager.settings_data["Runtime_Options"]["jdownloader_autostart"]
        if not self.jdownloader_download_dir:
            self.jdownloader_download_dir = manager.path_manager.download_dir
        self.jdownloader_download_dir = Path(self.jdownloader_download_dir)
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
        url: URL,
        title: str,
        relative_download_path: Path | None = None,
    ) -> None:
        """Sends links to JDownloader."""
        try:
            assert url.host is not None
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
        except (AssertionError, myjdapi.MYJDApiException) as e:
            raise JDownloaderError(e) from e
