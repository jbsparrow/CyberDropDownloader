from __future__ import annotations

import asyncio
import dataclasses
import itertools
import time
from functools import partial
from http.cookies import SimpleCookie
from typing import TYPE_CHECKING, Any

import aiohttp
from multidict import CIMultiDict, CIMultiDictProxy

from cyberdrop_dl.compat import StrEnum
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import DDOSGuardError
from cyberdrop_dl.utils.logger import log

if TYPE_CHECKING:
    from collections.abc import Callable

    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.client_manager import ClientManager


class _Command(StrEnum):
    CREATE_SESSION = "sessions.create"
    DESTROY_SESSION = "sessions.destroy"
    GET_REQUEST = "request.get"
    POST_REQUEST = "request.post"
    LIST_SESSIONS = "sessions.list"


@dataclasses.dataclass(frozen=True, slots=True)
class _FlareSolverrSolution:
    content: str
    cookies: SimpleCookie
    headers: CIMultiDictProxy
    url: AbsoluteHttpURL
    user_agent: str
    status: int

    @staticmethod
    def from_dict(solution: dict[str, Any]) -> _FlareSolverrSolution:
        return _FlareSolverrSolution(
            status=int(solution["status"]),
            cookies=_parse_cookies(solution.get("cookies") or []),
            user_agent=solution["userAgent"],
            content=solution["response"],
            url=AbsoluteHttpURL(solution["url"]),
            headers=CIMultiDictProxy(CIMultiDict(solution["headers"])),
        )


@dataclasses.dataclass(frozen=True, slots=True)
class _FlareSolverrResponse:
    status: str
    message: str
    ok: bool
    solution: _FlareSolverrSolution | None

    @staticmethod
    def from_dict(resp: dict[str, Any]) -> _FlareSolverrResponse:
        status = resp["status"]
        return _FlareSolverrResponse(
            status=status,
            ok=status == "ok",
            message=resp["message"],
            solution=_FlareSolverrSolution.from_dict(sol) if (sol := resp.get("solution")) else None,
        )


class FlareSolverr:
    """Class that handles communication with flaresolverr."""

    __slots__ = (
        "_next_request_id",
        "_request_lock",
        "_session_id",
        "_session_lock",
        "_url",
        "client_manager",
        "enabled",
    )

    _url: AbsoluteHttpURL

    def __init__(self, client_manager: ClientManager) -> None:
        self.client_manager = client_manager
        self.enabled = bool(client_manager.manager.global_config.general.flaresolverr)
        self._session_id: str = ""
        self._session_lock = asyncio.Lock()
        self._request_lock = asyncio.Lock()
        self._next_request_id: Callable[[], int] = partial(next, itertools.count())
        if self.client_manager.manager.global_config.general.flaresolverr:
            self._url = AbsoluteHttpURL(self.client_manager.manager.global_config.general.flaresolverr / "v1")

    def __repr__(self):
        return (
            f"{self.__class__.__name__}(enabled={self.enabled}{f', url={str(self._url)=!r}' if self.enabled else ''})"
        )

    async def close(self):
        await self.__destroy_session()

    async def request(self, url: AbsoluteHttpURL, data: Any = None) -> tuple[BeautifulSoup | None, AbsoluteHttpURL]:
        """Returns the resolved URL from the given URL."""

        # TODO: make this method return an abstract response

        command = _Command.POST_REQUEST if data else _Command.GET_REQUEST
        resp = await self.__request(command, url=str(url), data=data)
        if not resp.ok:
            raise DDOSGuardError(f"Failed to resolve URL with flaresolverr. {resp.message}")

        if not resp.solution:
            raise DDOSGuardError("Invalid response from flaresolverr") from None

        solution = resp.solution
        cdl_user_agent = self.client_manager.manager.global_config.general.user_agent
        mismatch_ua_msg = (
            "Config user_agent and flaresolverr user_agent do not match:"
            f"\n  Cyberdrop-DL: '{cdl_user_agent}'"
            f"\n  Flaresolverr: '{solution.user_agent}'"
        )

        if resp.soup and (
            self.client_manager.check_ddos_guard(resp.soup) or self.client_manager.check_cloudflare(resp.soup)
        ):
            if resp.user_agent != cdl_user_agent:
                raise DDOSGuardError(mismatch_ua_msg)

        if solution.user_agent != cdl_user_agent:
            msg = f"{mismatch_ua_msg}\n Response was successful but cookies will not be valid"
            log(msg, 30)

        self.client_manager.cookies.update_cookies(solution.cookies)
        return resp.soup, solution.url

    async def __request(
        self,
        command: _Command,
        data: Any = None,
        **kwargs,
    ) -> _FlareSolverrResponse:
        """Base request function to call flaresolverr."""
        if not self.enabled:
            raise DDOSGuardError("Found DDoS challenge, but FlareSolverr is not configured")

        async with self._session_lock:
            if not self._session_id:
                await self.__create_session()
        return await self.__raw_request(command, data=data, **kwargs)

    async def __raw_request(self, command: _Command, /, data: Any = None, **kwargs: Any) -> _FlareSolverrResponse:
        timeout = self.client_manager.manager.global_config.rate_limiting_options._scrape_timeout
        if command is _Command.CREATE_SESSION:
            timeout = aiohttp.ClientTimeout(total=5 * 60, connect=60)  # 5 minutes to create session

        playload = {
            "cmd": command,
            "maxTimeout": 60_000,  # This timeout is in miliseconds (60s)
            "session": self._session_id,
        } | kwargs

        if data:
            assert command is _Command.POST_REQUEST
            playload["postData"] = aiohttp.FormData(data)().decode()

        async with (
            self._request_lock,
            self.client_manager.manager.progress_manager.show_status_msg(
                f"Waiting For Flaresolverr Response [{self._next_request_id()}]"
            ),
        ):
            response = await self.client_manager.scraper_session._session.post(
                self._url, json=playload, timeout=timeout
            )

        return _FlareSolverrResponse.from_dict(await response.json())

    async def __create_session(self) -> None:
        """Creates a permanent flaresolverr session."""
        session_id = "cyberdrop-dl"
        kwargs = {}
        if proxy := self.client_manager.manager.global_config.general.proxy:
            kwargs["proxy"] = {"url": str(proxy)}

        resp = await self.__raw_request(_Command.CREATE_SESSION, session=session_id, **kwargs)
        if not resp.ok:
            raise DDOSGuardError(f"Failed to create flaresolverr session: {resp.message}")
        self._session_id = session_id

    async def __destroy_session(self) -> None:
        if self._session_id:
            await self.__raw_request(_Command.DESTROY_SESSION)
            self._session_id = ""


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
    return simple_cookie
