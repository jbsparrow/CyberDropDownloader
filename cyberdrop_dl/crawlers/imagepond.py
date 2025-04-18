from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers._chevereto import CheveretoCrawler

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager

PRIMARY_BASE_DOMAIN = URL("https://imagepond.net")


class ImagePondCrawler(CheveretoCrawler):
    primary_base_domain = PRIMARY_BASE_DOMAIN

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "imagepond.net", "ImagePond")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""
