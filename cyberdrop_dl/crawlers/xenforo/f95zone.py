from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils.utilities import error_handling_wrapper

from .xenforo import XenforoCrawler

_confirmation_data = ({"xhr": "1", "download": "1"},)


class F95ZoneCrawler(XenforoCrawler):
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://f95zone.to")
    DOMAIN: ClassVar[str] = "f95zone"
    FOLDER_DOMAIN: ClassVar[str] = "F95Zone"

    @error_handling_wrapper
    async def resolve_confirmation_link(self, link: AbsoluteHttpURL) -> AbsoluteHttpURL | None:
        async with self.request_limiter:
            json_resp = await self.client.post_data(self.DOMAIN, link, data=_confirmation_data)

        if json_resp["status"] == "ok":
            return self.parse_url(json_resp["msg"])

    @classmethod
    def is_thumbnail(cls, link: AbsoluteHttpURL) -> bool:
        return "thumb" in link.parts

    @classmethod
    def thumbnail_to_img(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        return url.with_path(url.path.replace("/thumb/", ""))

    def parse_url(self, link: str) -> AbsoluteHttpURL:
        url = super().parse_url(link)
        if self.is_thumbnail(url):
            return self.thumbnail_to_img(url)
        return url
