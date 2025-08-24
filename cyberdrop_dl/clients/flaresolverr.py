from __future__ import annotations

import asyncio
import dataclasses
from typing import TYPE_CHECKING, Any

import aiohttp

from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import DDOSGuardError
from cyberdrop_dl.utils.logger import log

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.client_manager import ClientManager


@dataclasses.dataclass(frozen=True, slots=True)
class FlareSolverrResponse:
    status: str
    url: AbsoluteHttpURL
    cookies: dict[str, str]
    user_agent: str
    content: str

    @classmethod
    def from_dict(cls, flaresolverr_resp: dict[str, Any]) -> FlareSolverrResponse:
        solution: dict[str, Any] = flaresolverr_resp["solution"]
        return cls(
            status=flaresolverr_resp["status"],
            cookies=solution.get("cookies") or {},
            user_agent=solution["userAgent"].strip(),
            content=solution["response"],
            url=AbsoluteHttpURL(solution["url"]),
        )


class FlareSolverr:
    """Class that handles communication with flaresolverr."""

    endpoint: AbsoluteHttpURL

    def __init__(self, client_manager: ClientManager) -> None:
        self.client_manager = client_manager
        self.enabled = bool(client_manager.manager.global_config.general.flaresolverr)
        self._session_id: str = ""
        self._session_lock = asyncio.Lock()
        self._request_lock = asyncio.Lock()
        self.request_count = 0
        if self.client_manager.manager.global_config.general.flaresolverr:
            self.endpoint = AbsoluteHttpURL(self.client_manager.manager.global_config.general.flaresolverr / "v1")

    async def _request(
        self,
        command: str,
        session: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Base request function to call flaresolverr."""
        if not self.enabled:
            raise DDOSGuardError("Found DDoS Challenge, but FlareSolverr is not configured")

        async with self._session_lock:
            if not (self._session_id or session):
                await self._create_session()
        return await self.__make_request(command, **kwargs)

    async def __make_request(self, command: str, **kwargs: Any) -> dict[str, Any]:
        timeout = self.client_manager.manager.global_config.rate_limiting_options._scrape_timeout
        if command == "sessions.create":
            timeout = aiohttp.ClientTimeout(total=5 * 60, connect=60)  # 5 minutes to create session

        for key, value in kwargs.items():
            if isinstance(value, AbsoluteHttpURL):
                kwargs[key] = str(value)

        playload = {
            "cmd": command,
            "maxTimeout": 60_000,  # This timeout is in miliseconds (60s)
            "session": self._session_id,
        } | kwargs

        self.request_count += 1

        async with (
            self._request_lock,
            self.client_manager.manager.progress_manager.show_status_msg(
                f"Waiting For Flaresolverr Response [{self.request_count}]"
            ),
        ):
            response = await self.client_manager.scraper_session._session.post(
                self.endpoint, json=playload, timeout=timeout
            )

        return await response.json()

    async def _create_session(self) -> None:
        """Creates a permanet flaresolverr session."""
        session_id = "cyberdrop-dl"
        kwargs = {}
        if proxy := self.client_manager.manager.global_config.general.proxy:
            kwargs["proxy"] = {"url": str(proxy)}

        flaresolverr_resp = await self.__make_request("sessions.create", session=session_id, **kwargs)
        if flaresolverr_resp.get("status") != "ok":
            raise DDOSGuardError("Failed to create flaresolverr session")
        self._session_id = session_id

    async def _destroy_session(self) -> None:
        if self._session_id:
            await self.__make_request("sessions.destroy", session=self._session_id)
            self._session_id = ""

    async def request(self, url: AbsoluteHttpURL) -> tuple[BeautifulSoup | None, AbsoluteHttpURL]:
        """Returns the resolved URL from the given URL."""
        json_resp = await self._request("request.get", url=url)

        try:
            fs_resp = FlareSolverrResponse.from_dict(json_resp)
        except (AttributeError, KeyError):
            raise DDOSGuardError("Invalid response from flaresolverr") from None

        if fs_resp.status != "ok":
            raise DDOSGuardError("Failed to resolve URL with flaresolverr")

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

        for cookie in fs_resp.cookies:
            self.client_manager.cookies.update_cookies(
                {cookie["name"]: cookie["value"]}, AbsoluteHttpURL(f"https://{cookie['domain']}")
            )

        return fs_resp.soup, fs_resp.url
