"""Real-Debrid API Implementation. All methods return their JSON response (if any).

For details, visit: https://api.real-debrid.com

Unless specified otherwise, all API methods require authentication.

The API is limited to 250 requests per minute. Use `rate_limiter` context manager to auto limit the requests being made

Dates are formatted according to the Javascript method `date.toJSON`.
Use `convert_special_types` to convert response values to `datetime.date`, `datetime.datetime`, `datetime.timedelta` and `yarl.URL` when applicable

"""

from __future__ import annotations

from typing import Any

import aiohttp
from aiolimiter import AsyncLimiter

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import RealDebridError

RATE_LIMIT = 250
API_ENTRYPOINT = AbsoluteHttpURL("https://api.real-debrid.com/rest/1.0")
ERROR_CODES = {
    -1: "Internal error",
    1: "Missing parameter",
    2: "Bad parameter value",
    3: "Unknown method",
    4: "Method not allowed",
    5: "Slow down",
    6: "Ressource unreachable",
    7: "Resource not found",
    8: "Bad token",
    9: "Permission denied",
    10: "Two-Factor authentication needed",
    11: "Two-Factor authentication pending",
    12: "Invalid login",
    13: "Invalid password",
    14: "Account locked",
    15: "Account not activated",
    16: "Unsupported hoster",
    17: "Hoster in maintenance",
    18: "Hoster limit reached",
    19: "Hoster temporarily unavailable",
    20: "Hoster not available for free users",
    21: "Too many active downloads",
    22: "IP Address not allowed",
    23: "Traffic exhausted",
    24: "File unavailable",
    25: "Service unavailable",
    26: "Upload too big",
    27: "Upload error",
    28: "File not allowed",
    29: "Torrent too big",
    30: "Torrent file invalid",
    31: "Action already done",
    32: "Image resolution error",
    33: "Torrent already active",
    34: "Too many requests",
    35: "Infringing file",
    36: "Fair Usage Limit",
}


class RealDebridAPI:
    def __init__(self, api_token: str | None, session: aiohttp.ClientSession) -> None:
        self._headers: dict[str, str] = {}
        self._session = session
        self.update_token(api_token or "")
        self.unrestrict = Unrestrict(self)
        self.hosts = Hosts(self)
        self.request_limiter = AsyncLimiter(RATE_LIMIT, 60)

    async def _get(self, path: str, /) -> Any:
        async with self.request_limiter:
            response = await self._session.get(API_ENTRYPOINT / path, headers=self._headers)
        return _handle_response(response)

    async def _post(self, path: str, /, **data: Any) -> Any:
        async with self.request_limiter:
            response = await self._session.post(API_ENTRYPOINT / path, headers=self._headers, data=data)
        return _handle_response(response)

    def update_token(self, new_token: str) -> None:
        self._api_token = new_token
        self._headers["Authorization"] = f"Bearer {new_token}"


class Unrestrict:
    def __init__(self, api: RealDebridAPI) -> None:
        self.api = api

    async def check(self, link: AbsoluteHttpURL, password: str | None = None) -> dict[str, Any]:
        """Check if a file is downloadable on the concerned hoster. This request does not require authentication."""
        return await self.api._post("unrestrict/check", link=link, password=password)

    async def link(self, link: AbsoluteHttpURL, password: str | None = None, remote: bool = False) -> AbsoluteHttpURL:
        """Unrestrict a hoster link and get a new unrestricted link."""
        json_resp: dict[str, Any] = await self.api._post("unrestrict/link", link=link, password=password, remote=remote)
        return AbsoluteHttpURL(json_resp["download"])

    async def folder(self, link: AbsoluteHttpURL) -> list[AbsoluteHttpURL]:
        """Unrestrict a hoster folder link and get individual links, returns an empty array if no links found."""
        links: list[str] = await self.api._post("unrestrict/folder", link=link)
        return [AbsoluteHttpURL(link) for link in links]


class Hosts:
    def __init__(self, api: RealDebridAPI) -> None:
        self.api = api

    async def get(self) -> list[str]:
        """Get supported hosts. This request does not require authentication."""
        return await self.api._get("hosts")

    async def regex(self) -> list[str]:
        """Get all supported links Regex, useful to find supported links inside a document. This request does not require authentication."""
        return await self.api._get("hosts/regex")

    async def regex_folder(self) -> list[str]:
        """Get all supported folder Regex, useful to find supported links inside a document. This request does not require authentication."""
        return await self.api._get("hosts/regexFolder")

    async def domains(self) -> list[str]:
        """Get all hoster domains supported on the service. This request does not require authentication."""
        return await self.api._get("hosts/domains")


async def _handle_response(response: aiohttp.ClientResponse) -> Any:
    try:
        json_resp: dict[str, Any] = await response.json()
        try:
            response.raise_for_status()
        except aiohttp.ClientResponseError:
            code = json_resp.get("error_code")
            if not code or code not in ERROR_CODES:
                raise
            code = 7 if code == 16 else code
            msg = ERROR_CODES.get(code, "Unknown error")
            raise RealDebridError(response.url, code, msg) from None
        else:
            return json_resp
    except AttributeError:
        response.raise_for_status()
        return await response.text()
