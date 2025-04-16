from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers.kemono import KemonoCrawler

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


SERVICES = "fanbox", "fantia", "fantia_products", "subscribestar", "twitter"


class NekohouseCrawler(KemonoCrawler):
    primary_base_domain = URL("https://nekohouse.su")
    DEFAULT_POST_TITLE_FORMAT = "{date} - {title}"

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager)
        self.domain = "nekohouse"
        self.folder_domain = "Nekohouse"
        self.api_entrypoint = None  # type: ignore

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""
