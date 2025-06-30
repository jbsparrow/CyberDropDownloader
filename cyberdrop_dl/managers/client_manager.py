from __future__ import annotations

import asyncio
import contextlib
import ssl
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.cookiejar import MozillaCookieJar
from typing import TYPE_CHECKING, Any

import aiohttp
import certifi
import truststore
from aiohttp import ClientResponse, ClientSession, ContentTypeError
from aiolimiter import AsyncLimiter
from bs4 import BeautifulSoup
from yarl import URL

from cyberdrop_dl.clients.download_client import DownloadClient
from cyberdrop_dl.clients.scraper_client import ScraperClient
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import DDOSGuardError, DownloadError, ScrapeError
from cyberdrop_dl.managers.download_speed_manager import DownloadSpeedLimiter
from cyberdrop_dl.ui.prompts.user_prompts import get_cookies_from_browsers
from cyberdrop_dl.utils.logger import log, log_spacer
from cyberdrop_dl.utils.utilities import get_soup_no_error

if TYPE_CHECKING:
    from collections.abc import Mapping

    from aiohttp_client_cache.response import CachedResponse
    from curl_cffi.requests.models import Response as CurlResponse

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager

DOWNLOAD_ERROR_ETAGS = {
    "d835884373f4d6c8f24742ceabe74946": "Imgur image has been removed",
    "65b7753c-528a": "SC Scrape Image",
    "5c4fb843-ece": "PixHost Removed Image",
    "637be5da-11d2b": "eFukt Video removed",
    "63a05f27-11d2b": "eFukt Video removed",
    "5a56b09d-1485eb": "eFukt Video removed",
}


class DDosGuard:
    TITLES = ("Just a moment...", "DDoS-Guard")
    SELECTORS = (
        "#cf-challenge-running",
        ".ray_id",
        ".attack-box",
        "#cf-please-wait",
        "#challenge-spinner",
        "#trk_jschal_js",
        "#turnstile-wrapper",
        ".lds-ring",
    )
    ALL_SELECTORS = ", ".join(SELECTORS)


class CloudflareTurnstile:
    TITLES = ("Simpcity Cuck Detection", "Attention Required! | Cloudflare", "Sentinel CAPTCHA")
    SELECTORS = (
        "captchawrapper",
        "cf-turnstile",
        "script[src*='challenges.cloudflare.com/turnstile']",
        "script:contains('Dont open Developer Tools')",
    )
    ALL_SELECTORS = ", ".join(SELECTORS)


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
        self.simultaneous_per_domain = global_settings_data.rate_limiting_options.max_simultaneous_downloads_per_domain

        ssl_context = global_settings_data.general.ssl_context
        if not ssl_context:
            self.ssl_context = False
        elif ssl_context == "certifi":
            self.ssl_context = ssl.create_default_context(cafile=certifi.where())
        elif ssl_context == "truststore":
            self.ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        elif ssl_context == "truststore+certifi":
            self.ssl_context = ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.load_verify_locations(cafile=certifi.where())

        self.cookies = aiohttp.CookieJar(quote_cookie=False)
        self.proxy: URL | None = global_settings_data.general.proxy  # type: ignore

        self.domain_rate_limits = {
            "bunkrr": AsyncLimiter(5, 1),
            "cyberdrop": AsyncLimiter(5, 1),
            "coomer": AsyncLimiter(1, 1),
            "kemono": AsyncLimiter(1, 1),
            "pixeldrain": AsyncLimiter(10, 1),
            "gofile": AsyncLimiter(100, 60),
            "hitomi.la": AsyncLimiter(3, 1),
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
            "nhentai.net": 1,
        }

        self.global_rate_limiter = AsyncLimiter(self.rate_limit, 1)
        self.session_limit = asyncio.Semaphore(50)
        self.download_session_limit = asyncio.Semaphore(
            self.manager.config_manager.global_settings_data.rate_limiting_options.max_simultaneous_downloads,
        )

        self.scraper_session = ScraperClient(self)
        self.speed_limiter = DownloadSpeedLimiter(manager)
        self.downloader_session = DownloadClient(manager, self)
        self.flaresolverr = Flaresolverr(self)

    def load_cookie_files(self) -> None:
        if self.manager.config_manager.settings_data.browser_cookies.auto_import:
            assert self.manager.config_manager.settings_data.browser_cookies.browser
            get_cookies_from_browsers(
                self.manager, browser=self.manager.config_manager.settings_data.browser_cookies.browser
            )
        cookie_files = sorted(self.manager.path_manager.cookies_dir.glob("*.txt"))
        if not cookie_files:
            return

        now = time.time()
        domains_seen = set()
        for file in cookie_files:
            cookie_jar = MozillaCookieJar(file)
            try:
                cookie_jar.load(ignore_discard=True)
            except OSError as e:
                log(f"Unable to load cookies from '{file.name}':\n  {e!s}", 40)
                continue
            current_cookie_file_domains: set[str] = set()
            expired_cookies_domains: set[str] = set()
            for cookie in cookie_jar:
                simplified_domain = cookie.domain.removeprefix(".")
                if simplified_domain not in current_cookie_file_domains:
                    log(f"Found cookies for {simplified_domain} in file '{file.name}'", 20)
                    current_cookie_file_domains.add(simplified_domain)
                    if simplified_domain in domains_seen:
                        log(f"Previous cookies for domain {simplified_domain} detected. They will be overwritten", 30)

                if (simplified_domain not in expired_cookies_domains) and cookie.is_expired(now):  # type: ignore
                    expired_cookies_domains.add(simplified_domain)

                domains_seen.add(simplified_domain)
                self.cookies.update_cookies({cookie.name: cookie.value}, response_url=URL(f"https://{cookie.domain}"))  # type: ignore

            for simplified_domain in expired_cookies_domains:
                log(f"Cookies for {simplified_domain} are expired", 30)

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

    @classmethod
    async def check_http_status(
        cls,
        response: ClientResponse | CurlResponse | CachedResponse,
        download: bool = False,
        origin: ScrapeItem | URL | None = None,
    ) -> BeautifulSoup | None:
        """Checks the HTTP status code and raises an exception if it's not acceptable.

        If the response is successful and has valid html, returns soup
        """
        status: int = response.status_code if hasattr(response, "status_code") else response.status  # type: ignore
        headers = response.headers
        url_host: str = AbsoluteHttpURL(response.url).host
        message = None

        def check_etag() -> None:
            if download and (e_tag := headers.get("ETag")) in DOWNLOAD_ERROR_ETAGS:
                message = DOWNLOAD_ERROR_ETAGS.get(e_tag)
                raise DownloadError(HTTPStatus.NOT_FOUND, message=message, origin=origin)

        async def check_ddos_guard() -> BeautifulSoup | None:
            if soup := await get_soup_no_error(response):
                if cls.check_ddos_guard(soup) or cls.check_cloudflare(soup):
                    raise DDOSGuardError(origin=origin)
                return soup

        async def check_json_status() -> None:
            if not any(domain in url_host for domain in ("gofile", "imgur")):
                return

            with contextlib.suppress(ContentTypeError):
                json_resp: dict[str, Any] | None = await response.json()
                if not json_resp:
                    return
                json_status: str | int | None = json_resp.get("status")
                if json_status and isinstance(status, str) and "notFound" in status:
                    raise ScrapeError(404, origin=origin)

                if (data := json_resp.get("data")) and isinstance(data, dict) and "error" in data:
                    raise ScrapeError(json_status or status, data["error"], origin=origin)

        check_etag()
        if HTTPStatus.OK <= status < HTTPStatus.BAD_REQUEST:
            # Check DDosGuard even on successful pages
            # await check_ddos_guard()
            return

        await check_json_status()
        await check_ddos_guard()
        raise DownloadError(status=status, message=message, origin=origin)

    @staticmethod
    def check_content_length(headers: Mapping[str, Any]) -> None:
        content_length, content_type = headers.get("Content-Length"), headers.get("Content-Type")
        if content_length is None or content_type is None:
            return
        if content_length == "322509" and content_type == "video/mp4":
            raise DownloadError(status="Bunkr Maintenance", message="Bunkr under maintenance")
        if content_length == "73003" and content_type == "video/mp4":
            raise DownloadError(410)  # Placeholder video with text "Video removed" (efukt)

    @staticmethod
    def check_ddos_guard(soup: BeautifulSoup) -> bool:
        if (title := soup.select_one("title")) and (title_str := title.string):
            if any(title.casefold() == title_str.casefold() for title in DDosGuard.TITLES):
                return True

        return bool(soup.select_one(DDosGuard.ALL_SELECTORS))

    @staticmethod
    def check_cloudflare(soup: BeautifulSoup) -> bool:
        if (title := soup.select_one("title")) and (title_str := title.string):
            if any(title.casefold() == title_str.casefold() for title in CloudflareTurnstile.TITLES):
                return True

        return bool(soup.select_one(CloudflareTurnstile.ALL_SELECTORS))

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
        ):
            response = await client_session.post(
                self.flaresolverr_host / "v1",
                headers=headers,
                ssl=self.client_manager.ssl_context,
                proxy=self.client_manager.proxy,
                json=data,
                timeout=timeout,
            )
            json_obj: dict[str, Any] = await response.json()

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
        mismatch_msg = f"Config user_agent and flaresolverr user_agent do not match: \n  Cyberdrop-DL: '{user_agent}'\n  Flaresolverr: '{fs_resp.user_agent}'"
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
