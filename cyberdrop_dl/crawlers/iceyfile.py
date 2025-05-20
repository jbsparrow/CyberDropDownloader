from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.cyberfile import CyberfileCrawler
from cyberdrop_dl.types import AbsoluteHttpURL, OneOrTupleStrMapping

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class IceyFileCrawler(CyberfileCrawler):
    SUPPORTED_PATHS: ClassVar[OneOrTupleStrMapping] = {
        "Files": "/...",
        "Folders": "/folder/...",
        "Shared": "/shared/...",
    }
    primary_base_domain = AbsoluteHttpURL("https://iceyfile.com/")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager)
        self.DOMAIN = "iceyfile"
        self.folder_domain = "Iceyfile"
