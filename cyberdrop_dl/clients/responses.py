from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiohttp
    from bs4 import BeautifulSoup
    from multidict import CIMultiDictProxy
    from yarl import URL

    Headers = CIMultiDictProxy[str] | dict[str, str | int]


@dataclass(slots=True, frozen=True)
class RequestResponse:
    response_url: URL
    headers: Headers
    response: aiohttp.ClientResponse


@dataclass(slots=True, frozen=True)
class GetRequestResponse(RequestResponse):
    soup: BeautifulSoup


@dataclass(slots=True, frozen=True)
class JsonRequestResponse(RequestResponse):
    json: dict


@dataclass(slots=True, frozen=True)
class PostRequestResponse(JsonRequestResponse):
    raw: bytes
