from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

from .kemono import KemonoBaseCrawler

if TYPE_CHECKING:
    from aiohttp_client_cache.response import AnyResponse


class CoomerCrawler(KemonoBaseCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://coomer.st")
    DOMAIN: ClassVar[str] = "coomer"
    API_ENTRYPOINT = AbsoluteHttpURL("https://coomer.st/api/v1")
    SERVICES = "onlyfans", "fansly", "candfans"
    OLD_DOMAINS: ClassVar[tuple[str, ...]] = "coomer.party", "coomer.su"

    @property
    def session_cookie(self) -> str:
        return self.manager.config_manager.authentication_data.coomer.session

    async def async_startup(self) -> None:
        await super().async_startup()

        def check_coomer_page(response: AnyResponse) -> bool:
            if any(p in response.url.parts for p in ("onlyfans", "fansly", "data")):
                return False
            return True

        self.register_cache_filter(self.PRIMARY_URL, check_coomer_page)
