from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

from myjdapi import myjdapi

from cyberdrop_dl.exceptions import JDownloaderError
from cyberdrop_dl.utils.logger import log

if TYPE_CHECKING:
    from pathlib import Path

    from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
    from cyberdrop_dl.managers.manager import Manager


@dataclasses.dataclass(slots=True)
class JDownloaderConfig:
    enabled: bool
    username: str
    password: str
    device: str
    download_dir: Path
    autostart: bool

    @staticmethod
    def from_manager(manager: Manager) -> JDownloaderConfig:
        download_dir = manager.config.runtime_options.jdownloader_download_dir or manager.path_manager.download_folder
        return JDownloaderConfig(
            enabled=manager.config.runtime_options.send_unsupported_to_jdownloader,
            device=manager.auth_config.jdownloader.device,
            username=manager.auth_config.jdownloader.username,
            password=manager.auth_config.jdownloader.password,
            download_dir=download_dir.resolve(),
            autostart=manager.config.runtime_options.jdownloader_autostart,
        )


class JDownloader:
    """Class that handles connecting and passing links to JDownloader."""

    def __init__(self, options: Manager | JDownloaderConfig, /) -> None:
        if isinstance(options, JDownloaderConfig):
            self._config = options
        else:
            self._config = JDownloaderConfig.from_manager(options)
        self.enabled = self._config.enabled
        self._agent = None

    def _connect(self) -> None:
        if not all((self._config.username, self._config.password, self._config.device)):
            raise JDownloaderError("JDownloader credentials were not provided.")
        jd = myjdapi.Myjdapi()
        jd.set_app_key("CYBERDROP-DL")
        jd.connect(self._config.username, self._config.password)
        self._agent = jd.get_device(self._config.device)

    def connect(self) -> None:
        if not self.enabled or self._agent is not None:
            return
        try:
            return self._connect()
        except JDownloaderError as e:
            msg = e.message
        except myjdapi.MYJDDeviceNotFoundException:
            msg = f"Device not found ({self._config.device})"
        except myjdapi.MYJDApiException as e:
            msg = e

        log(f"Failed to connect to jDownloader: {msg}", 40)
        self.enabled = False

    def direct_unsupported_to_jdownloader(
        self,
        url: AbsoluteHttpURL,
        title: str,
        relative_download_path: Path | None = None,
    ) -> None:
        """Sends links to JDownloader."""
        try:
            assert self._agent is not None
            download_folder = self._config.download_dir
            if relative_download_path:
                download_folder = download_folder / relative_download_path
            self._agent.linkgrabber.add_links(
                [
                    {
                        "autostart": self._config.autostart,
                        "links": str(url),
                        "packageName": title if title else "Cyberdrop-DL",
                        "destinationFolder": str(download_folder),
                        "overwritePackagizerRules": True,
                    },
                ],
            )
        except (AssertionError, myjdapi.MYJDException) as e:
            raise JDownloaderError(str(e)) from e
