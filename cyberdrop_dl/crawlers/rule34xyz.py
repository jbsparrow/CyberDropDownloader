from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.rule34vault import Rule34VaultCrawler
from cyberdrop_dl.types import AbsoluteHttpURL, SupportedPaths

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class Rule34XYZCrawler(Rule34VaultCrawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = (
        ("File page", "/post/..."),
        ("Tag", "/..."),
    )
    primary_base_domain = AbsoluteHttpURL("https://rule34.xyz")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager)
        self.domain = "rule34.xyz"
        self.folder_domain = "Rule34XYZ"

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""
