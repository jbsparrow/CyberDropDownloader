from __future__ import annotations

import asyncio
from json import loads as json_loads
from typing import TYPE_CHECKING, Any

from aiohttp_client_cache.response import AnyResponse
from bs4 import BeautifulSoup
from multidict import CIMultiDict, CIMultiDictProxy

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import InvalidContentTypeError, ScrapeError
from cyberdrop_dl.utils.utilities import parse_url

if TYPE_CHECKING:
    from curl_cffi.requests.models import Response as CurlResponse


class AbstractResponse:
    """Class to represent common methods and attributes between aiohttp ClientResponse and a CurlResponse"""

    __slots__ = ("_read_lock", "_resp", "content_type", "headers", "location", "status", "url")

    def __init__(self, response: AnyResponse | CurlResponse) -> None:
        self._resp = response
        self.content_type = (self._resp.headers.get("Content-Type") or "").lower()
        if isinstance(response, AnyResponse):
            self.status = response.status
            self.headers = response.headers
        else:
            self.status = response.status_code
            self.headers = CIMultiDictProxy(CIMultiDict({k: v or "" for k, v in response.headers}))

        self.url = AbsoluteHttpURL(response.url)
        if location := response.headers.get("location"):
            self.location = parse_url(location, self.url.origin(), trim=False)
        else:
            self.location = None

        self._read_lock = asyncio.Lock()

    async def text(self) -> str:
        async with self._read_lock:
            if isinstance(self._resp, AnyResponse):
                return await self._resp.text()
            return self._resp.text

    async def soup(self) -> BeautifulSoup:
        if "text" in self.content_type or "html" in self.content_type:
            return BeautifulSoup(await self.text(), "html.parser")

        raise InvalidContentTypeError(message=f"Received {self.content_type}, was expecting text")

    async def json(self) -> Any:
        if self.status == 204:
            raise ScrapeError(204)

        if "text/plain" in self.content_type or "json" in self.content_type:
            return json_loads(await self.text())

        raise InvalidContentTypeError(message=f"Received {self.content_type}, was expecting JSON")

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} [{self.status}] ({self.url})>"
