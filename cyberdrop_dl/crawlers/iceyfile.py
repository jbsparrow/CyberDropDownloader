from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers.cyberfile import CyberfileCrawler

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class IceyFileCrawler(CyberfileCrawler):
    primary_base_domain = URL("https://iceyfile.com/")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager)
        self.domain = "iceyfile"
        self.folder_domain = "Iceyfile"
