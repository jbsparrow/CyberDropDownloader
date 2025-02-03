from __future__ import annotations

import asyncio
import contextlib
import ssl
from contextlib import asynccontextmanager
from http import HTTPStatus
from http.cookiejar import MozillaCookieJar
from typing import TYPE_CHECKING

import aiohttp
import certifi
from aiohttp import ClientResponse, ContentTypeError
from aiolimiter import AsyncLimiter
from bs4 import BeautifulSoup
from yarl import URL

from cyberdrop_dl.clients.errors import DDOSGuardError, DownloadError, ScrapeError
from cyberdrop_dl.clients.http.download_client import DownloadClient
from cyberdrop_dl.clients.http.scraper_client import ScraperClient
from cyberdrop_dl.managers.download_speed_manager import DownloadSpeedLimiter
from cyberdrop_dl.ui.prompts.user_prompts import get_cookies_from_browsers
from cyberdrop_dl.utils.constants import CustomHTTPStatus
from cyberdrop_dl.utils.logger import log, log_spacer

from .flaresolverr import Flaresolverr

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.scraper.crawler import Crawler, ScrapeItem

DOWNLOAD_ERROR_ETAGS = {
    "d835884373f4d6c8f24742ceabe74946": "Imgur image has been removed",
    "65b7753c-528a": "SC Scrape Image",
    "5c4fb843-ece": "PixHost Removed Image",
}


CLOUDFLARE_CHALLENGE_TITLES = ["Simpcity Cuck Detection", "Attention Required! | Cloudflare"]
CLOUDFLARE_CHALLENGE_SELECTORS = ["captchawrapper", "cf-turnstile"]
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


class ClientManager:
    """Creates a 'client' that can be referenced by scraping or download sessions."""

    def __init__(self, manager: Manager) -> None:
        global_settings_data = manager.config_manager.global_settings_data
        rate_limiting_options = global_settings_data.rate_limiting_options
        verify_ssl = not global_settings_data.general.allow_insecure_connections
        read_timeout = rate_limiting_options.read_timeout
        connection_timeout = rate_limiting_options.connection_timeout
        total_timeout = read_timeout + connection_timeout

        self.manager = manager
        self.ssl_context = ssl.create_default_context(cafile=certifi.where()) if verify_ssl else False
        self.user_agent = global_settings_data.general.user_agent
        self.auto_import_cookies = self.manager.config_manager.settings_data.browser_cookies.auto_import
        self.cookies = aiohttp.CookieJar(quote_cookie=False)
        self.proxy: URL | None = global_settings_data.general.proxy  # type: ignore
        self.timeout = aiohttp.ClientTimeout(total=total_timeout, connect=connection_timeout)

        self.DEFAULT_LIMITER = AsyncLimiter(25, 1)
        self.request_limiters = {}
        self.download_spacers = {}
        self.download_slots = {}

        self.global_request_limiter = AsyncLimiter(rate_limiting_options.rate_limit, 1)
        self.global_request_semaphore = asyncio.Semaphore(50)

        self.scraper_client = ScraperClient(self)
        self.downloader_client = DownloadClient(self)
        self.download_speed_limiter = DownloadSpeedLimiter(manager)
        self.flaresolverr = Flaresolverr(manager)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    def register(self, crawler: Crawler) -> None:
        domain = crawler.domain
        assert domain not in self.request_limiters, f"{domain} is already registered"
        self.request_limiters.update({domain: crawler.request_limiter})
        self.download_spacers.update({domain: crawler.download_spacer})
        self.download_slots.update({domain: crawler.max_concurrent_downloads})

    @asynccontextmanager
    async def limiter(self, domain: str):
        domain_request_limiter = self.request_limiters.get(domain, self.DEFAULT_LIMITER)
        async with (
            self.global_request_semaphore,
            self.global_request_limiter,
            domain_request_limiter,
        ):
            yield

    async def close(self) -> None:
        await self.flaresolverr._destroy_session()

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @staticmethod
    def check_bunkr_maint(headers: dict):
        if headers.get("Content-Length") == "322509" and headers.get("Content-Type") == "video/mp4":
            raise DownloadError(status="Bunkr Maintenance", message="Bunkr under maintenance")

    @staticmethod
    def check_ddos_guard(soup: BeautifulSoup) -> bool:
        return check_soup(soup, DDOS_GUARD_CHALLENGE_TITLES, DDOS_GUARD_CHALLENGE_SELECTORS)

    @staticmethod
    def check_cloudflare(soup: BeautifulSoup) -> bool:
        return check_soup(soup, CLOUDFLARE_CHALLENGE_TITLES, CLOUDFLARE_CHALLENGE_SELECTORS)

    def load_cookie_files(self) -> None:
        if self.auto_import_cookies:
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
                simplified_domain = cookie.domain[1:] if cookie.domain.startswith(".") else cookie.domain
                if simplified_domain not in current_cookie_file_domains:
                    log(f"Found cookies for {simplified_domain} in file '{file.name}'", 20)
                    current_cookie_file_domains.add(simplified_domain)
                    if simplified_domain in domains_seen:
                        log(f"Previous cookies for domain {simplified_domain} detected. They will be overwritten", 30)
                domains_seen.add(simplified_domain)
                self.cookies.update_cookies({cookie.name: cookie.value}, response_url=URL(f"https://{cookie.domain}"))  # type: ignore

        log_spacer(20, log_to_console=False)

    @classmethod
    async def check_http_status(
        cls, response: ClientResponse, download: bool = False, origin: ScrapeItem | URL | None = None
    ) -> None:
        """Checks the HTTP status code and raises an exception if it's not acceptable."""
        status = response.status
        headers = response.headers

        e_tag = headers.get("ETag")
        if download and e_tag and e_tag in DOWNLOAD_ERROR_ETAGS:
            message = DOWNLOAD_ERROR_ETAGS.get(e_tag)
            raise DownloadError(HTTPStatus.NOT_FOUND, message=message, origin=origin)

        if HTTPStatus.OK <= status < HTTPStatus.BAD_REQUEST:
            return

        assert response.url.host
        if any(domain in response.url.host for domain in ("gofile", "imgur")):
            with contextlib.suppress(ContentTypeError):
                JSON_Resp: dict = await response.json()
                status_str: str = JSON_Resp.get("status")  # type: ignore
                if status_str and isinstance(status, str) and "notFound" in status_str:
                    raise ScrapeError(404, origin=origin)
                data = JSON_Resp.get("data")
                if data and isinstance(data, dict) and "error" in data:
                    raise ScrapeError(status_str, data["error"], origin=origin)

        response_text = None
        with contextlib.suppress(UnicodeDecodeError):
            response_text = await response.text()

        if response_text:
            soup = BeautifulSoup(response_text, "html.parser")
            if cls.check_ddos_guard(soup) or cls.check_cloudflare(soup):
                raise DDOSGuardError(origin=origin)
        status: str | int = status if headers.get("Content-Type") else CustomHTTPStatus.IM_A_TEAPOT
        message = None if headers.get("Content-Type") else "No content-type in response header"

        raise DownloadError(status=status, message=message, origin=origin)


def check_soup(soup: BeautifulSoup, titles: list[str], selectors: list[str]) -> bool:
    if soup.title:
        for title in titles:
            challenge_found = title.casefold() == soup.title.text.casefold()
            if challenge_found:
                return True

    for selector in selectors:
        challenge_found = soup.find(selector)
        if challenge_found:
            return True

    return False
