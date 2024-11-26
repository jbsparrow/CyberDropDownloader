from __future__ import annotations

import asyncio
import contextlib
import ssl
from http import HTTPStatus
from typing import TYPE_CHECKING

import aiohttp
import certifi
from aiohttp import ClientResponse, ClientSession, ContentTypeError
from aiolimiter import AsyncLimiter
from bs4 import BeautifulSoup
from yarl import URL

from cyberdrop_dl.clients.download_client import DownloadClient
from cyberdrop_dl.clients.errors import DDOSGuardError, DownloadError, ScrapeError
from cyberdrop_dl.clients.scraper_client import ScraperClient
from cyberdrop_dl.managers.leaky import LeakyBucket
from cyberdrop_dl.utils.constants import CustomHTTPStatus
from cyberdrop_dl.utils.logger import log

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.scraper.crawler import ScrapeItem

DOWNLOAD_ERROR_ETAGS = {
    "d835884373f4d6c8f24742ceabe74946": "Imgur image has been removed",
    "65b7753c-528a": "SC Scrape Image",
}

DDOS_GUARD_CHALLENGE_TITLES = ["Just a moment...", "DDoS-Guard"]
DDOS_GUARD_CHALLENGE_SELECTORS = [
    "#cf-challenge-running",
    ".ray_id",
    ".attack-box",
    "#cf-please-wait",
    "#challenge-spinner",
    "#trk_jschal_js",
    "#turnstile-wrapper",
    ".lds-ring",
]

CLOUDFLARE_CHALLENGE_TITLES = ["Simpcity Cuck Detection"]
CLOUDFLARE_CHALLENGE_SELECTORS = ["captchawrapper", "cf-turnstile"]


class ClientManager:
    """Creates a 'client' that can be referenced by scraping or download sessions."""

    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self.connection_timeout = manager.config_manager.global_settings_data["Rate_Limiting_Options"][
            "connection_timeout"
        ]
        self.read_timeout = manager.config_manager.global_settings_data["Rate_Limiting_Options"]["read_timeout"]
        self.rate_limit = manager.config_manager.global_settings_data["Rate_Limiting_Options"]["rate_limit"]

        self.download_delay = manager.config_manager.global_settings_data["Rate_Limiting_Options"]["download_delay"]
        self.user_agent = manager.config_manager.global_settings_data["General"]["user_agent"]
        self.verify_ssl = not manager.config_manager.global_settings_data["General"]["allow_insecure_connections"]
        self.simultaneous_per_domain = manager.config_manager.global_settings_data["Rate_Limiting_Options"][
            "max_simultaneous_downloads_per_domain"
        ]

        self.ssl_context = ssl.create_default_context(cafile=certifi.where()) if self.verify_ssl else False
        self.cookies = aiohttp.CookieJar(quote_cookie=False)
        self.proxy = (
            manager.config_manager.global_settings_data["General"]["proxy"]
            if not manager.args_manager.proxy
            else manager.args_manager.proxy
        )

        self.domain_rate_limits = {
            "bunkrr": AsyncLimiter(5, 1),
            "cyberdrop": AsyncLimiter(5, 1),
            "coomer": AsyncLimiter(1, 1),
            "kemono": AsyncLimiter(1, 1),
            "pixeldrain": AsyncLimiter(10, 1),
            "other": AsyncLimiter(25, 1),
        }

        self.download_spacer = {
            "bunkr": 0.5,
            "bunkrr": 0.5,
            "cyberdrop": 0,
            "cyberfile": 0,
            "pixeldrain": 0,
            "coomer": 0.5,
            "kemono": 0.5,
        }

        self.global_rate_limiter = AsyncLimiter(self.rate_limit, 1)
        self.session_limit = asyncio.Semaphore(50)
        self.download_session_limit = asyncio.Semaphore(
            self.manager.config_manager.global_settings_data["Rate_Limiting_Options"]["max_simultaneous_downloads"],
        )

        self.scraper_session = ScraperClient(self)
        self.downloader_session = DownloadClient(manager, self)
        self._leaky_bucket = LeakyBucket(manager)
        self.flaresolverr = Flaresolverr(self)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def get_downloader_spacer(self, key: str) -> float:
        """Returns the download spacer for a domain."""
        if key in self.download_spacer:
            return self.download_spacer[key]
        return 0.1

    async def get_rate_limiter(self, domain: str) -> AsyncLimiter:
        """Get a rate limiter for a domain."""
        if domain in self.domain_rate_limits:
            return self.domain_rate_limits[domain]
        return self.domain_rate_limits["other"]

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @classmethod
    async def check_http_status(
        cls,
        response: ClientResponse,
        download: bool = False,
        origin: ScrapeItem | URL | None = None,
    ) -> None:
        """Checks the HTTP status code and raises an exception if it's not acceptable."""
        status = response.status
        headers = response.headers

        if download and headers.get("ETag") in DOWNLOAD_ERROR_ETAGS:
            message = DOWNLOAD_ERROR_ETAGS.get(headers.get("ETag"))
            raise DownloadError(HTTPStatus.NOT_FOUND, message=message, origin=origin)
        
        response_text = None
        with contextlib.suppress(UnicodeDecodeError):
            response_text = await response.text()

        if response_text:
            soup = BeautifulSoup(response_text, "html.parser")
            if cls.check_ddos_guard(soup) or cls.check_cloudflare(soup):
                raise DDOSGuardError(origin=origin)

        if HTTPStatus.OK <= status < HTTPStatus.BAD_REQUEST:
            return

        if any(domain in response.url.host for domain in ("gofile", "imgur")):
            with contextlib.suppress(ContentTypeError):
                JSON_Resp: dict = await response.json()
                if "status" in JSON_Resp and "notFound" in JSON_Resp["status"]:
                    raise ScrapeError(HTTPStatus.NOT_FOUND, origin=origin)
                if "data" in JSON_Resp and "error" in JSON_Resp["data"]:
                    raise ScrapeError(JSON_Resp["status"], JSON_Resp["data"]["error"], origin=origin)

        

        status = status if headers.get("Content-Type") else CustomHTTPStatus.IM_A_TEAPOT
        message = "No content-type in response header" if headers.get("Content-Type") else None

        raise DownloadError(status=status, message=message, origin=origin)


    @staticmethod
    def check_bunkr_maint(headers: dict):
        if headers.get("Content-Length") == "322509" and headers.get("Content-Type") == "video/mp4":
            raise DownloadError(status="Bunkr Maintenance", message="Bunkr under maintenance")

    async def check_bucket(self, size: float) -> None:
        await self._leaky_bucket.acquire(size)

    @staticmethod
    def check_ddos_guard(soup: BeautifulSoup) -> bool:
        if soup.title:
            for title in DDOS_GUARD_CHALLENGE_TITLES:
                challenge_found = title.casefold() == soup.title.string.casefold()
                if challenge_found:
                    return True

        for selector in DDOS_GUARD_CHALLENGE_SELECTORS:
            challenge_found = soup.find(selector)
            if challenge_found:
                return True

        return False

    @staticmethod
    def check_cloudflare(soup: BeautifulSoup) -> bool:
        if soup.title:
            for title in CLOUDFLARE_CHALLENGE_TITLES:
                challenge_found = title.casefold() == soup.title.string.casefold()
                if challenge_found:
                    return True

        for selector in CLOUDFLARE_CHALLENGE_SELECTORS:
            challenge_found = soup.find(selector)
            if challenge_found:
                return True

        return False

    async def close(self) -> None:
        await self.flaresolverr._destroy_session()


class Flaresolverr:
    """Class that handles communication with flaresolverr."""

    def __init__(self, client_manager: ClientManager) -> None:
        self.client_manager = client_manager
        self.flaresolverr_host = (
            client_manager.manager.args_manager.flaresolverr
            or client_manager.manager.config_manager.global_settings_data["General"]["flaresolverr"]
        )
        self.enabled = bool(self.flaresolverr_host)
        if "http" not in self.flaresolverr_host:
            self.flaresolverr_host = f"http://{self.flaresolverr_host}"
        self.session_id = None
        self.flaresolverr_host = URL(self.flaresolverr_host)

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
            self.flaresolverr_host / "v1",
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
        response_url = URL(solution.get("url"))
        cookies: list[dict] = solution.get("cookies")
        user_agent = client_session.headers.get("User-Agent").strip()
        flaresolverr_user_agent = solution.get("userAgent").strip()
        mismatch_msg = f"Config user_agent and flaresolverr user_agent do not match:\n  Cyberdrop-DL: {user_agent}\n  Flaresolverr: {flaresolverr_user_agent}"

        if self.client_manager.check_ddos_guard(response):
            if not update_cookies:
                raise DDOSGuardError(message="Invalid response from flaresolverr", origin=origin)
            if flaresolverr_user_agent != user_agent:
                raise DDOSGuardError(message=mismatch_msg, origin=origin)

        if update_cookies:
            if flaresolverr_user_agent != user_agent:
                log(f"{mismatch_msg}\nResponse was successful but cookies will not be valid", 30)

            for cookie in cookies:
                self.client_manager.cookies.update_cookies(
                    {cookie["name"]: cookie["value"]}, URL(f"https://{cookie['domain']}")
                )

        return response, response_url
