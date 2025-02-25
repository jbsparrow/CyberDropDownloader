from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import aiohttp
from aiohttp import ClientSession
from bs4 import BeautifulSoup
from yarl import URL

from cyberdrop_dl.clients import check
from cyberdrop_dl.clients.errors import DDOSGuardError
from cyberdrop_dl.clients.responses import GetRequestResponse
from cyberdrop_dl.utils.logger import log

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.scraper.crawler import ScrapeItem


FAILED_RESOLVE_MSG = "Failed to resolve URL with flaresolverr"
FAILED_SESSION_CREATE_MSG = "Failed to create flaresolverr session"
INVALID_RESPONSE_MSG = "Invalid response from flaresolverr"
NOT_CONFIGURED_MSG = "FlareSolverr is not configured"


class Flaresolverr:
    """Class that handles communication with flaresolverr."""

    def __init__(self, manager: Manager) -> None:
        self.client_manager = manager.client_manager
        self.flaresolverr_url: URL = manager.config_manager.global_settings_data.general.flaresolverr  # type: ignore
        self.enabled = bool(self.flaresolverr_url)
        self.session_id = None
        self.update_cookies: bool = True
        self.timeout = aiohttp.ClientTimeout(total=120000, connect=60000)

    async def _request(
        self,
        command: str,
        client_session: ClientSession,
        origin: ScrapeItem | URL | None = None,
        **kwargs,
    ) -> dict:
        """Base request function to call flaresolverr."""
        if not self.enabled:
            raise DDOSGuardError(message=NOT_CONFIGURED_MSG, origin=origin)

        if not (self.session_id or kwargs.get("session")):
            await self._create_session()

        headers = client_session.headers.copy()
        headers.update({"Content-Type": "application/json"})
        for key, value in kwargs.items():
            if isinstance(value, URL):
                kwargs[key] = str(value)

        data = {"cmd": command, "maxTimeout": 60000, "session": self.session_id} | kwargs

        async with client_session.post(
            self.flaresolverr_url / "v1",
            headers=headers,
            ssl=self.client_manager.ssl_context,
            proxy=self.client_manager.proxy,
            json=data,
        ) as response:
            json_obj: dict = await response.json()  # type: ignore

        return json_obj

    async def _create_session(self) -> None:
        """Creates a permanet flaresolverr session."""
        session_id = "cyberdrop-dl"
        async with ClientSession() as client_session:
            flaresolverr_resp = await self._request("sessions.create", client_session, session=session_id)
        status = flaresolverr_resp["status"]
        if status != "ok":
            raise DDOSGuardError(message=FAILED_SESSION_CREATE_MSG)
        self.session_id = session_id

    async def _destroy_session(self) -> None:
        if self.session_id:
            async with ClientSession() as client_session:
                await self._request("sessions.destroy", client_session, session=self.session_id)

    async def get(
        self,
        url: URL,
        client_session: ClientSession,
        origin: ScrapeItem | URL | None = None,
    ) -> FlaresolverrResponse:
        """Returns the resolved URL from the given URL."""
        json_resp: dict = await self._request("request.get", client_session, origin, url=url)

        try:
            fs_resp = FlaresolverrResponse.from_dict(json_resp)
        except (AttributeError, KeyError):
            raise DDOSGuardError(message="Invalid response from flaresolverr", origin=origin) from None

        if fs_resp.status != "ok":
            raise DDOSGuardError(message="Failed to resolve URL with flaresolverr", origin=origin)

        mismatch_msg = f"Config user_agent and flaresolverr user_agent do not match: \n  Cyberdrop-DL: {fs_resp.user_agent}\n  Flaresolverr: {fs_resp.user_agent}"

        user_agent = client_session.headers["User-Agent"].strip()
        if check.is_ddos_guard(fs_resp.soup):
            if not self.update_cookies:
                raise DDOSGuardError(message="Invalid response from flaresolverr", origin=origin)
            if fs_resp.user_agent != user_agent:
                raise DDOSGuardError(message=mismatch_msg, origin=origin)

        if self.update_cookies:
            if fs_resp.user_agent != user_agent:
                log(f"{mismatch_msg}\nResponse was successful but cookies will not be valid", 30)

            for cookie in fs_resp.cookies:
                self.client_manager.cookies.update_cookies(
                    {cookie["name"]: cookie["value"]}, URL(f"https://{cookie['domain']}")
                )

        return fs_resp


@dataclass(frozen=True, slots=True, kw_only=True)
class FlaresolverrResponse(GetRequestResponse):
    status: str
    cookies: dict
    user_agent: str

    @classmethod
    def from_dict(cls, flaresolverr_resp: dict) -> FlaresolverrResponse:
        status = flaresolverr_resp["status"]
        solution: dict = flaresolverr_resp["solution"]
        response = solution["response"]
        user_agent = solution["userAgent"].strip()
        url_str: str = solution["url"]
        cookies: dict = solution.get("cookies") or {}
        soup = BeautifulSoup(response, "html.parser")
        url = URL(url_str)
        return cls(
            status=status,
            cookies=cookies,
            user_agent=user_agent,
            soup=soup,
            response_url=url,
            response=None,  # type: ignore
            headers=solution,
        )
