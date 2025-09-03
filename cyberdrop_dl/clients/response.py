from __future__ import annotations

import asyncio
import dataclasses
from json import loads as json_loads
from typing import TYPE_CHECKING, Any

from aiohttp import ClientResponse
from aiohttp_client_cache.response import CachedResponse
from bs4 import BeautifulSoup
from multidict import CIMultiDict, CIMultiDictProxy

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import InvalidContentTypeError, ScrapeError
from cyberdrop_dl.utils.utilities import parse_url

if TYPE_CHECKING:
    from curl_cffi.requests.models import Response as CurlResponse

    from cyberdrop_dl.clients.flaresolverr import FlareSolverrSolution


@dataclasses.dataclass(slots=True, weakref_slot=True)
class AbstractResponse:
    """Class to represent common methods and attributes between an `aiohttp.ClientResponse` and a `CurlResponse`"""

    content_type: str
    status: int
    headers: CIMultiDictProxy[str]
    url: AbsoluteHttpURL
    location: AbsoluteHttpURL | None

    _resp: ClientResponse | CachedResponse | CurlResponse | None = None
    _text: str = ""
    _read_lock: asyncio.Lock = dataclasses.field(init=False, default_factory=asyncio.Lock)

    @classmethod
    def from_resp(cls, response: ClientResponse | CachedResponse | CurlResponse) -> AbstractResponse:
        if isinstance(response, ClientResponse | CachedResponse):
            status = response.status
            headers = response.headers
        else:
            status = response.status_code
            headers = CIMultiDictProxy(CIMultiDict({k: v or "" for k, v in response.headers}))

        url = AbsoluteHttpURL(response.url)
        content_type, location = cls.parse_headers(url, headers)
        return AbstractResponse(
            content_type=content_type,
            status=status,
            headers=headers,
            url=url,
            location=location,
            _resp=response,
        )

    @classmethod
    def from_flaresolverr(cls, sol: FlareSolverrSolution) -> AbstractResponse:
        content_type, location = AbstractResponse.parse_headers(sol.url, sol.headers)

        return AbstractResponse(
            content_type=content_type,
            status=sol.status,
            headers=sol.headers,
            url=sol.url,
            location=location,
            _text=sol.content,
        )

    @staticmethod
    def parse_headers(url: AbsoluteHttpURL, headers: CIMultiDictProxy[str]):
        if location := headers.get("location"):
            location = parse_url(location, url.origin(), trim=False)
        else:
            location = None

        content_type = (headers.get("Content-Type") or "").lower()
        return content_type, location

    async def text(self, encoding: str | None = None) -> str:
        if self._text:
            return self._text

        assert self._resp is not None
        async with self._read_lock:
            if self._text:
                return self._text
            if isinstance(self._resp, ClientResponse | CachedResponse):
                self._text = await self._resp.text(encoding)
            else:
                if encoding:
                    self._resp.encoding = encoding
                self._text = await self._resp.atext()
        return self._text

    async def soup(self, encoding: str | None = None) -> BeautifulSoup:
        if "text" in self.content_type or "html" in self.content_type:
            return BeautifulSoup(await self.text(encoding), "html.parser")

        raise InvalidContentTypeError(message=f"Received {self.content_type}, was expecting HTML")

    async def json(self, encoding: str | None = None, content_type: str | bool = True) -> Any:
        if self.status == 204:
            raise ScrapeError(204)

        if content_type:
            if isinstance(content_type, str):
                check = (content_type,)
            else:
                check = ("text/plain", "json")
            if not any(type_ in self.content_type for type_ in check):
                raise InvalidContentTypeError(message=f"Received {self.content_type}, was expecting JSON")

        return json_loads(await self.text(encoding))

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} [{self.status}] ({self.url!r})>"
