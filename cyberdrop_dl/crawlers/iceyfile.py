from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.cyberfile import CyberfileCrawler
from cyberdrop_dl.types import AbsoluteHttpURL, SupportedPaths

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class IceyFileCrawler(CyberfileCrawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = (
        ("Files", "/..."),
        ("Folders", "/folder/..."),
        ("Shared", "/shared/..."),
    )
    primary_base_domain = AbsoluteHttpURL("https://iceyfile.com/")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager)
        self.domain = "iceyfile"
        self.folder_domain = "Iceyfile"
