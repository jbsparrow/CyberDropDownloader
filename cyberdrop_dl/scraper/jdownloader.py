from __future__ import annotations

import time
from dataclasses import field
from typing import TYPE_CHECKING

from myjdapi import myjdapi
from pathlib import Path

from cyberdrop_dl.clients.errors import JDownloaderFailure
from cyberdrop_dl.managers.manager import Manager
from cyberdrop_dl.utils.utilities import log

if TYPE_CHECKING:
    from yarl import URL


class JDownloader:
    """Class that handles connecting and passing links to JDownloader"""

    def __init__(self, manager: Manager):
        self.enabled = manager.config_manager.settings_data['Runtime_Options']['send_unsupported_to_jdownloader']
        self.jdownloader_device = manager.config_manager.authentication_data['JDownloader']['jdownloader_device']
        self.jdownloader_username = manager.config_manager.authentication_data['JDownloader']['jdownloader_username']
        self.jdownloader_password = manager.config_manager.authentication_data['JDownloader']['jdownloader_password']
        self.jdownloader_download_dir = manager.config_manager.settings_data['Runtime_Options']['jdownloader_download_dir']
        self.jdownloader_autostart = manager.config_manager.settings_data['Runtime_Options']['jdownloader_autostart']
        if not self.jdownloader_download_dir:
            self.jdownloader_download_dir = manager.path_manager.download_dir
        self.jdownloader_download_dir = Path(self.jdownloader_download_dir)
        self.jdownloader_agent = field(init=False)

    async def jdownloader_setup(self) -> None:
        """Setup function for JDownloader"""
        try:
            if not all (self.jdownloader_username, self.jdownloader_password, self.jdownloader_device):
                raise JDownloaderFailure("JDownloader credentials were not provided.")
            jd = myjdapi.Myjdapi()
            jd.set_app_key("CYBERDROP-DL")
            jd.connect(self.jdownloader_username, self.jdownloader_password)
            self.jdownloader_agent = jd.get_device(self.jdownloader_device)
            return

        except (myjdapi.MYJDApiException, JDownloaderFailure) as e:
            msg = e.message

        except myjdapi.MYJDDeviceNotFoundException as e:
            msg = str(e)

        await log(f"Failed JDownloader setup\n{msg}", 40)
        self.enabled = False
        time.sleep(20)

    async def direct_unsupported_to_jdownloader(self, url: URL, title: str) -> None:
        """Sends links to JDownloader"""
        try:
            assert url.host is not None
            assert self.jdownloader_agent is not None
            self.jdownloader_agent.linkgrabber.add_links([{
                "autostart": self.jdownloader_autostart ,
                "links": str(url),
                "packageName": title if title else "Cyberdrop-DL",
                "destinationFolder": str(self.jdownloader_download_dir.resolve()),
                "overwritePackagizerRules": True
            }])

        except (JDownloaderFailure, AssertionError) as e:
            await log(f"Failed to send {url} to JDownloader\n{e.message}", 40)
