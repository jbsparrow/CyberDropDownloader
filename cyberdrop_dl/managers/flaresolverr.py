from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp import ClientSession
from bs4 import BeautifulSoup
from yarl import URL

from cyberdrop_dl.clients.errors import DDOSGuardError
from cyberdrop_dl.utils.logger import log

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.scraper.crawler import ScrapeItem


class Flaresolverr:
    """Class that handles communication with flaresolverr."""

    def __init__(self, manager: Manager) -> None:
        self.client_manager = manager.client_manager
        self.flaresolverr_url: URL = manager.config_manager.global_settings_data.general.flaresolverr  # type: ignore
        self.enabled = bool(self.flaresolverr_url)
        self.session_id = None

    async def _request(
        self,
        command: str,
        client_session: ClientSession,
        origin: ScrapeItem | URL | None = None,
        **kwargs,
    ) -> dict:
        """Base request function to call flaresolverr."""
        if not self.enabled:
            raise DDOSGuardError(message="FlareSolverr is not configured", origin=origin)

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
        status = flaresolverr_resp.get("status")
        if status != "ok":
            raise DDOSGuardError(message="Failed to create flaresolverr session")
        self.session_id = session_id

    async def _destroy_session(self):
        if self.session_id:
            async with ClientSession() as client_session:
                await self._request("sessions.destroy", client_session, session=self.session_id)

    async def get(
        self,
        url: URL,
        client_session: ClientSession,
        origin: ScrapeItem | URL | None = None,
        update_cookies: bool = True,
    ) -> tuple[BeautifulSoup, URL]:
        """Returns the resolved URL from the given URL."""
        flaresolverr_resp: dict = await self._request("request.get", client_session, origin, url=url)

        status = flaresolverr_resp.get("status")
        if status != "ok":
            raise DDOSGuardError(message="Failed to resolve URL with flaresolverr", origin=origin)

        solution: dict = flaresolverr_resp.get("solution")
        if not solution:
            raise DDOSGuardError(message="Invalid response from flaresolverr", origin=origin)

        response = BeautifulSoup(solution.get("response"), "html.parser")
        response_url_str: str = solution.get("url")
        response_url = URL(response_url_str, encoded="%" in response_url_str)
        cookies: list[dict] = solution.get("cookies")
        user_agent = client_session.headers.get("User-Agent").strip()
        flaresolverr_user_agent = solution.get("userAgent").strip()
        mismatch_msg = f"Config user_agent and flaresolverr user_agent do not match:\n  Cyberdrop-DL: {user_agent}\n  Flaresolverr: {flaresolverr_user_agent}"

        if self.client_manager.check_ddos_guard(response) or self.client_manager.check_cloudflare(response):
            if not update_cookies:
                raise DDOSGuardError(message="Invalid response from flaresolverr", origin=origin)
            if flaresolverr_user_agent != user_agent:
                raise DDOSGuardError(message=mismatch_msg, origin=origin)

        if update_cookies:
            if flaresolverr_user_agent != user_agent:
                msg = f"{mismatch_msg}\nResponse was successful but cookies will not be valid"
                log(msg, 30)

            for cookie in cookies:
                cookies_data = {cookie["name"]: cookie["value"]}, URL(f"https://{cookie['domain']}")
                self.client_manager.cookies.update_cookies(*cookies_data)

        return response, response_url
