from __future__ import annotations

import asyncio
import dataclasses
from json import loads as json_loads
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Self

import aiohttp.multipart
from aiohttp import ClientResponse
from aiohttp.client_reqrep import ContentDisposition
from aiohttp_client_cache.response import CachedResponse
from bs4 import BeautifulSoup
from multidict import CIMultiDict, CIMultiDictProxy
from propcache import under_cached_property

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import InvalidContentTypeError, ScrapeError
from cyberdrop_dl.utils.utilities import parse_url

if TYPE_CHECKING:
    from curl_cffi.requests.models import Response as CurlResponse

    from cyberdrop_dl.clients.flaresolverr import FlareSolverrSolution


@dataclasses.dataclass(slots=True, weakref_slot=True)
class AbstractResponse:
    """
    Class to represent common methods and attributes between:
        - `aiohttp.ClientResponse`
        - `curl_cffi.Response`
        - `FlareSolverrSolution`
    """

    content_type: str
    status: int
    headers: CIMultiDictProxy[str]
    url: AbsoluteHttpURL
    location: AbsoluteHttpURL | None

    _resp: ClientResponse | CachedResponse | CurlResponse | None = None
    _text: str = ""
    _cache: dict[str, Any] = dataclasses.field(init=False, default_factory=dict)
    _read_lock: asyncio.Lock = dataclasses.field(init=False, default_factory=asyncio.Lock)

    @classmethod
    def from_resp(cls, response: ClientResponse | CachedResponse | CurlResponse) -> Self:
        if isinstance(response, ClientResponse | CachedResponse):
            status = response.status
            headers = response.headers
        else:
            status = response.status_code
            multi_items = ((k, v) for k, v in response.headers.multi_items() if v is not None)
            headers = CIMultiDictProxy(CIMultiDict(multi_items))

        url = AbsoluteHttpURL(response.url)
        content_type, location = cls.parse_headers(url, headers)
        return cls(
            content_type=content_type,
            status=status,
            headers=headers,
            url=url,
            location=location,
            _resp=response,
        )

    @classmethod
    def from_flaresolverr(cls, solution: FlareSolverrSolution) -> Self:
        content_type, location = cls.parse_headers(solution.url, solution.headers)
        return cls(
            content_type=content_type,
            status=solution.status,
            headers=solution.headers,
            url=solution.url,
            location=location,
            _text=solution.content,
        )

    @staticmethod
    def parse_headers(url: AbsoluteHttpURL, headers: CIMultiDictProxy[str]) -> tuple[str, AbsoluteHttpURL | None]:
        if location := headers.get("location"):
            location = parse_url(location, url.origin(), trim=False)
        else:
            location = None

        content_type = (headers.get("Content-Type") or "").lower()
        return content_type, location

    @under_cached_property
    def content_disposition(self) -> ContentDisposition:
        header = self.headers["Content-Disposition"]
        disposition_type, params = aiohttp.multipart.parse_content_disposition(header)
        params = MappingProxyType(params)
        filename = aiohttp.multipart.content_disposition_filename(params)
        return ContentDisposition(disposition_type, params, filename)

    @property
    def filename(self) -> str:
        assert self.content_disposition.filename
        return self.content_disposition.filename

    @property
    def consumed(self) -> bool:
        return bool(self._text)

    @property
    def ok(self) -> bool:
        """Returns `True` if `status` is less than `400`, `False` if not.

        This is **not** a check for ``200 OK``
        """
        return self.status < 400

    async def read(self) -> bytes:
        assert self._resp is not None
        async with self._read_lock:
            if isinstance(self._resp, ClientResponse | CachedResponse):
                return await self._resp.read()
            return await self._resp.acontent()

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
        self._check_content_type("text", "html", expecting="HTML")
        return BeautifulSoup(await self.text(encoding), "html.parser")

    async def json(self, encoding: str | None = None, content_type: str | bool = True) -> Any:
        if self.status == 204:
            raise ScrapeError(204)

        if content_type:
            if isinstance(content_type, str):
                check = (content_type,)
            else:
                check = ("text/plain", "json")

            self._check_content_type(*check, expecting="JSON")

        return json_loads(await self.text(encoding))

    def _check_content_type(self, *content_types, expecting: str):
        if not any(type_ in self.content_type for type_ in content_types):
            msg = f"Received {self.content_type}, was expecting {expecting}"
            raise InvalidContentTypeError(message=msg)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} [{self.status}] ({self.url})>"
