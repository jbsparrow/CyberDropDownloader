from __future__ import annotations

import asyncio
import contextlib
import ssl
from dataclasses import dataclass
from http import HTTPStatus
from http.cookiejar import MozillaCookieJar
from typing import TYPE_CHECKING, Any

import aiohttp
import certifi
from aiohttp import ClientResponse, ClientSession, ContentTypeError
from aiolimiter import AsyncLimiter
from bs4 import BeautifulSoup
from curl_cffi.requests.models import Response as CurlResponse
from yarl import URL

from cyberdrop_dl.clients.download_client import DownloadClient
from cyberdrop_dl.clients.errors import DDOSGuardError, DownloadError, ScrapeError
from cyberdrop_dl.clients.scraper_client import ScraperClient
from cyberdrop_dl.managers.download_speed_manager import DownloadSpeedLimiter
from cyberdrop_dl.ui.prompts.user_prompts import get_cookies_from_browsers
from cyberdrop_dl.utils.logger import log, log_spacer

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.scraper.crawler import ScrapeItem

DOWNLOAD_ERROR_ETAGS = {
    "d835884373f4d6c8f24742ceabe74946": "Imgur image has been removed",
    "65b7753c-528a": "SC Scrape Image",
    "5c4fb843-ece": "PixHost Removed Image",
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

CLOUDFLARE_CHALLENGE_TITLES = ["Simpcity Cuck Detection", "Attention Required! | Cloudflare"]
CLOUDFLARE_CHALLENGE_SELECTORS = ["captchawrapper", "cf-turnstile"]


class ClientManager:
    """Creates a 'client' that can be referenced by scraping or download sessions."""

    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        global_settings_data = manager.config_manager.global_settings_data
        self.connection_timeout = global_settings_data.rate_limiting_options.connection_timeout
        self.read_timeout = global_settings_data.rate_limiting_options.read_timeout
        self.rate_limit = global_settings_data.rate_limiting_options.rate_limit

        self.download_delay = global_settings_data.rate_limiting_options.download_delay
        self.user_agent = global_settings_data.general.user_agent
        self.verify_ssl = not global_settings_data.general.allow_insecure_connections
        self.simultaneous_per_domain = global_settings_data.rate_limiting_options.max_simultaneous_downloads_per_domain

        self.ssl_context = ssl.create_default_context(cafile=certifi.where()) if self.verify_ssl else False
        self.cookies = aiohttp.CookieJar(quote_cookie=False)
        self.proxy: URL | None = global_settings_data.general.proxy  # type: ignore

        self.domain_rate_limits = {
            "bunkrr": AsyncLimiter(5, 1),
            "cyberdrop": AsyncLimiter(5, 1),
            "coomer": AsyncLimiter(1, 1),
            "kemono": AsyncLimiter(1, 1),
            "pixeldrain": AsyncLimiter(10, 1),
            "gofile": AsyncLimiter(100, 60),
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
            self.manager.config_manager.global_settings_data.rate_limiting_options.max_simultaneous_downloads,
        )

        self.scraper_session = ScraperClient(self)
        self.downloader_session = DownloadClient(manager, self)
        self.speed_limiter = DownloadSpeedLimiter(manager)
        self.flaresolverr = Flaresolverr(self)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    def load_cookie_files(self) -> None:
        if self.manager.config_manager.settings_data.browser_cookies.auto_import:
            get_cookies_from_browsers(self.manager)
        cookie_files = sorted(self.manager.path_manager.cookies_dir.glob("*.txt"))
        if not cookie_files:
            return

        domains_seen = set()
        for file in cookie_files:
            cookie_jar = MozillaCookieJar(file)
            try:
                cookie_jar.load(ignore_discard=True)
            except OSError as e:
                log(f"Unable to load cookies from '{file.name}':\n  {e!s}", 40)
                continue
            current_cookie_file_domains = set()
            for cookie in cookie_jar:
                simplified_domain = cookie.domain.removeprefix(".")
                if simplified_domain not in current_cookie_file_domains:
                    log(f"Found cookies for {simplified_domain} in file '{file.name}'", 20)
                    current_cookie_file_domains.add(simplified_domain)
                    if simplified_domain in domains_seen:
                        log(f"Previous cookies for domain {simplified_domain} detected. They will be overwritten", 30)
                domains_seen.add(simplified_domain)
                self.cookies.update_cookies({cookie.name: cookie.value}, response_url=URL(f"https://{cookie.domain}"))  # type: ignore

        log_spacer(20, log_to_console=False)

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
        response: ClientResponse | CurlResponse,
        download: bool = False,
        origin: ScrapeItem | URL | None = None,
    ) -> None:
        """Checks the HTTP status code and raises an exception if it's not acceptable."""
        is_curl = isinstance(response, CurlResponse)
        status = response.status_code if is_curl else response.status
        headers = response.headers
        message = None

        e_tag = headers.get("ETag")
        if download and e_tag in DOWNLOAD_ERROR_ETAGS:
            message = DOWNLOAD_ERROR_ETAGS.get(e_tag)
            raise DownloadError(HTTPStatus.NOT_FOUND, message=message, origin=origin)

        if HTTPStatus.OK <= status < HTTPStatus.BAD_REQUEST:
            return

        if any(domain in response.url.host for domain in ("gofile", "imgur")):  # type: ignore
            with contextlib.suppress(ContentTypeError):
                JSON_Resp: dict = await response.json()
                status: str | int = JSON_Resp.get("status")  # type: ignore
                if status and isinstance(status, str) and "notFound" in status:
                    raise ScrapeError(404, origin=origin)
                data = JSON_Resp.get("data")
                if data and isinstance(data, dict) and "error" in data:
                    raise ScrapeError(status, data["error"], origin=origin)

        response_text = None
        with contextlib.suppress(UnicodeDecodeError):
            response_text = response.text if is_curl else await response.text()

        if response_text:
            soup = BeautifulSoup(response_text, "html.parser")
            if cls.check_ddos_guard(soup) or cls.check_cloudflare(soup):
                raise DDOSGuardError(origin=origin)

        raise DownloadError(status=status, message=message, origin=origin)

    @staticmethod
    def check_bunkr_maint(headers: dict):
        if headers.get("Content-Length") == "322509" and headers.get("Content-Type") == "video/mp4":
            raise DownloadError(status="Bunkr Maintenance", message="Bunkr under maintenance")

    @staticmethod
    def check_ddos_guard(soup: BeautifulSoup) -> bool:
        if soup.title:
            for title in DDOS_GUARD_CHALLENGE_TITLES:
                challenge_found = title.casefold() == soup.title.string.casefold()  # type: ignore
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
                challenge_found = title.casefold() == soup.title.string.casefold()  # type: ignore
                if challenge_found:
                    return True

        for selector in CLOUDFLARE_CHALLENGE_SELECTORS:
            challenge_found = soup.find(selector)
            if challenge_found:
                return True

        return False

    async def close(self) -> None:
        await self.flaresolverr._destroy_session()


@dataclass(frozen=True, slots=True)
class FlaresolverrResponse:
    status: str
    cookies: dict
    user_agent: str
    soup: BeautifulSoup | None
    url: URL

    @classmethod
    def from_dict(cls, flaresolverr_resp: dict) -> FlaresolverrResponse:
        status = flaresolverr_resp["status"]
        solution: dict = flaresolverr_resp["solution"]
        response = solution["response"]
        user_agent = solution["userAgent"].strip()
        url_str: str = solution["url"]
        cookies: dict = solution.get("cookies") or {}
        soup = BeautifulSoup(response, "html.parser") if response else None
        url = URL(url_str)
        return cls(status, cookies, user_agent, soup, url)


class Flaresolverr:
    """Class that handles communication with flaresolverr."""

    def __init__(self, client_manager: ClientManager) -> None:
        self.client_manager = client_manager
        self.flaresolverr_host: URL = client_manager.manager.config_manager.global_settings_data.general.flaresolverr  # type: ignore
        self.enabled = bool(self.flaresolverr_host)
        self.session_id: str = ""
        self.session_create_timeout = aiohttp.ClientTimeout(total=5 * 60, connect=60)  # 5 minutes to create session
        self.timeout = client_manager.scraper_session._timeouts  # Config timeout for normal requests
        self.session_lock = asyncio.Lock()
        self.request_lock = asyncio.Lock()
        self.request_count = 0

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
        async with self.session_lock:
            if not (self.session_id or kwargs.get("session")):
                await self._create_session()
        return await self._make_request(command, client_session, **kwargs)

    async def _make_request(self, command: str, client_session: ClientSession, **kwargs) -> dict[str, Any]:
        timeout = self.timeout
        if command == "sessions.create":
            timeout = self.session_create_timeout

        headers = client_session.headers.copy()
        headers.update({"Content-Type": "application/json"})
        for key, value in kwargs.items():
            if isinstance(value, URL):
                kwargs[key] = str(value)

        data = {
            "cmd": command,
            "maxTimeout": 60_000,  # This timeout is in miliseconds (60s)
            "session": self.session_id,
        } | kwargs

        self.request_count += 1
        msg = f"Waiting For Flaresolverr Response [{self.request_count}]"
        async with (
            self.request_lock,
            self.client_manager.manager.progress_manager.show_status_msg(msg),
            client_session.post(
                self.flaresolverr_host / "v1",
                headers=headers,
                ssl=self.client_manager.ssl_context,
                proxy=self.client_manager.proxy,
                json=data,
                timeout=timeout,
            ) as response,
        ):
            json_obj: dict = await response.json()  # type: ignore

        return json_obj

    async def _create_session(self) -> None:
        """Creates a permanet flaresolverr session."""
        session_id = "cyberdrop-dl"
        async with ClientSession() as client_session:
            flaresolverr_resp = await self._make_request("sessions.create", client_session, session=session_id)
        status = flaresolverr_resp.get("status")
        if status != "ok":
            raise DDOSGuardError(message="Failed to create flaresolverr session")
        self.session_id = session_id

    async def _destroy_session(self):
        if self.session_id:
            async with ClientSession() as client_session:
                await self._make_request("sessions.destroy", client_session, session=self.session_id)
            self.session_id = ""

    async def get(
        self,
        url: URL,
        client_session: ClientSession,
        origin: ScrapeItem | URL | None = None,
        update_cookies: bool = True,
    ) -> tuple[BeautifulSoup | None, URL]:
        """Returns the resolved URL from the given URL."""
        json_resp: dict = await self._request("request.get", client_session, origin, url=url)

        try:
            fs_resp = FlaresolverrResponse.from_dict(json_resp)
        except (AttributeError, KeyError):
            raise DDOSGuardError(message="Invalid response from flaresolverr", origin=origin) from None

        if fs_resp.status != "ok":
            raise DDOSGuardError(message="Failed to resolve URL with flaresolverr", origin=origin)

        user_agent = client_session.headers["User-Agent"].strip()
        mismatch_msg = f"Config user_agent and flaresolverr user_agent do not match: \n  Cyberdrop-DL: {user_agent}\n  Flaresolverr: {fs_resp.user_agent}"
        if fs_resp.soup and (
            self.client_manager.check_ddos_guard(fs_resp.soup) or self.client_manager.check_cloudflare(fs_resp.soup)
        ):
            if not update_cookies:
                raise DDOSGuardError(message="Invalid response from flaresolverr", origin=origin)
            if fs_resp.user_agent != user_agent:
                raise DDOSGuardError(message=mismatch_msg, origin=origin)

        if update_cookies:
            if fs_resp.user_agent != user_agent:
                log(f"{mismatch_msg}\nResponse was successful but cookies will not be valid", 30)

            for cookie in fs_resp.cookies:
                self.client_manager.cookies.update_cookies(
                    {cookie["name"]: cookie["value"]}, URL(f"https://{cookie['domain']}")
                )

        return fs_resp.soup, fs_resp.url
