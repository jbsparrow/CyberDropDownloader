from __future__ import annotations

import asyncio
import dataclasses
import time
from http.cookies import SimpleCookie
from typing import TYPE_CHECKING, Any

import aiohttp
from multidict import CIMultiDict, CIMultiDictProxy

from cyberdrop_dl.compat import StrEnum
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import DDOSGuardError
from cyberdrop_dl.utils.logger import log

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.client_manager import ClientManager


class _Command(StrEnum):
    CREATE_SESSION = "sessions.create"
    DESTROY_SESSION = "sessions.destroy"
    GET_REQUEST = "request.get"
    LIST_SESSIONS = "sessions.list"


@dataclasses.dataclass(frozen=True, slots=True)
class _FlareSolverrResponse:
    content: str
    cookies: SimpleCookie
    headers: CIMultiDictProxy
    message: str
    status: str
    url: AbsoluteHttpURL
    user_agent: str

    @classmethod
    def from_dict(cls, resp: dict[str, Any]) -> _FlareSolverrResponse:
        solution: dict[str, Any] = resp["solution"]
        cookies: list[dict[str, Any]] = solution.get("cookies") or []
        return cls(
            status=resp["status"],
            cookies=_parse_cookies(cookies),
            user_agent=solution["userAgent"].strip(),
            content=solution["response"],
            url=AbsoluteHttpURL(solution["url"]),
            headers=CIMultiDictProxy(CIMultiDict(solution["headers"])),
            message=resp["message"],
        )


class FlareSolverr:
    """Class that handles communication with flaresolverr."""

    __slots__ = ("_request_count", "_request_lock", "_session_id", "_session_lock", "_url", "client_manager", "enabled")

    _url: AbsoluteHttpURL

    def __init__(self, client_manager: ClientManager) -> None:
        self.client_manager = client_manager
        self.enabled = bool(client_manager.manager.global_config.general.flaresolverr)
        self._session_id: str = ""
        self._session_lock = asyncio.Lock()
        self._request_lock = asyncio.Lock()
        self._request_count = 0
        if self.client_manager.manager.global_config.general.flaresolverr:
            self._url = AbsoluteHttpURL(self.client_manager.manager.global_config.general.flaresolverr / "v1")

    def __repr__(self):
        return (
            f"{self.__class__.__name__}(enabled={self.enabled}{f', url={str(self._url)=!r}' if self.enabled else ''})"
        )

    async def close(self):
        await self.__destroy_session()

    async def _request(
        self,
        command: _Command,
        **kwargs,
    ) -> dict[str, Any]:
        """Base request function to call flaresolverr."""
        if not self.enabled:
            raise DDOSGuardError("Found DDoS challenge, but FlareSolverr is not configured")

        async with self._session_lock:
            if not self._session_id:
                await self.__create_session()
        return await self.__make_request(command, **kwargs)

    async def __make_request(self, command: _Command, /, **kwargs: Any) -> dict[str, Any]:
        timeout = self.client_manager.manager.global_config.rate_limiting_options._scrape_timeout
        if command is _Command.CREATE_SESSION:
            timeout = aiohttp.ClientTimeout(total=5 * 60, connect=60)  # 5 minutes to create session

        for key, value in kwargs.items():
            if isinstance(value, AbsoluteHttpURL):
                kwargs[key] = str(value)

        playload = {
            "cmd": command,
            "maxTimeout": 60_000,  # This timeout is in miliseconds (60s)
            "session": self._session_id,
        } | kwargs

        self._request_count += 1

        async with (
            self._request_lock,
            self.client_manager.manager.progress_manager.show_status_msg(
                f"Waiting For Flaresolverr Response [{self._request_count}]"
            ),
        ):
            response = await self.client_manager.scraper_session._session.post(
                self._url, json=playload, timeout=timeout
            )

        return await response.json()

    async def __create_session(self) -> None:
        """Creates a permanet flaresolverr session."""
        session_id = "cyberdrop-dl"
        kwargs = {}
        if proxy := self.client_manager.manager.global_config.general.proxy:
            kwargs["proxy"] = {"url": str(proxy)}

        flaresolverr_resp = await self.__make_request(_Command.CREATE_SESSION, session=session_id, **kwargs)
        if flaresolverr_resp.get("status") != "ok":
            raise DDOSGuardError(f"Failed to create flaresolverr session. {flaresolverr_resp.get('message')}")
        self._session_id = session_id

    async def __destroy_session(self) -> None:
        if self._session_id:
            await self.__make_request(_Command.DESTROY_SESSION)
            self._session_id = ""

    async def request(self, url: AbsoluteHttpURL) -> tuple[BeautifulSoup | None, AbsoluteHttpURL]:
        """Returns the resolved URL from the given URL."""

        # TODO: make this method return an abstract response
        json_resp = await self._request(_Command.GET_REQUEST, url=url)

        try:
            fs_resp = _FlareSolverrResponse.from_dict(json_resp)
        except (AttributeError, KeyError):
            raise DDOSGuardError("Invalid response from flaresolverr") from None

        if fs_resp.status != "ok":
            raise DDOSGuardError(f"Failed to resolve URL with flaresolverr. {fs_resp.message}")

        user_agent = self.client_manager.manager.global_config.general.user_agent
        mismatch_ua_msg = (
            "Config user_agent and flaresolverr user_agent do not match:"
            f"\n  Cyberdrop-DL: '{user_agent}'"
            f"\n  Flaresolverr: '{fs_resp.user_agent}'"
        )

        if fs_resp.soup and (
            self.client_manager.check_ddos_guard(fs_resp.soup) or self.client_manager.check_cloudflare(fs_resp.soup)
        ):
            if fs_resp.user_agent != user_agent:
                raise DDOSGuardError(mismatch_ua_msg)

        if fs_resp.user_agent != user_agent:
            log(f"{mismatch_ua_msg}\nResponse was successful but cookies will not be valid", 30)

        self.client_manager.cookies.update_cookies(fs_resp.cookies)

        return fs_resp.soup, fs_resp.url


def _parse_cookies(cookies: list[dict[str, Any]]) -> SimpleCookie:
    simple_cookie = SimpleCookie()
    now = time.time()
    for cookie in cookies:
        name: str = cookie["name"]
        simple_cookie[name] = cookie["value"]
        morsel = simple_cookie[name]
        morsel["domain"] = cookie["domain"]
        morsel["path"] = cookie["path"]
        morsel["secure"] = "TRUE" if cookie["secure"] else ""
        if expires := cookie["expires"]:
            morsel["max-age"] = str(max(0, int(expires) - int(now)))
        else:
            morsel["max-age"] = ""
    return simple_cookie
