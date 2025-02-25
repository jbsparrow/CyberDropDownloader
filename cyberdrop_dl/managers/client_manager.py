from __future__ import annotations

import asyncio
import ssl
from contextlib import asynccontextmanager
from http.cookiejar import MozillaCookieJar
from typing import TYPE_CHECKING

import aiohttp
import certifi
from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.download_client import DownloadClient
from cyberdrop_dl.clients.flaresolverr import Flaresolverr
from cyberdrop_dl.clients.scraper_client import ScraperClient
from cyberdrop_dl.ui.prompts.user_prompts import get_cookies_from_browsers
from cyberdrop_dl.utils.logger import log, log_spacer

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.scraper.crawler import Crawler


class DownloadSpeedLimiter(AsyncLimiter):
    def __init__(self, manager: Manager) -> None:
        self.download_speed_limit = (
            manager.config_manager.global_settings_data.rate_limiting_options.download_speed_limit
        )
        self.chunk_size = 1024 * 1024 * 10  # 10MB
        if self.download_speed_limit:
            self.chunk_size = min(self.chunk_size, self.download_speed_limit)
        super().__init__(self.download_speed_limit, 1)

    async def acquire(self, amount: float | None = None) -> None:
        if self.download_speed_limit <= 0:
            return
        if not amount:
            amount = self.chunk_size
        await super().acquire(amount)


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
                simplified_domain = cookie.domain.removeprefix(".")
                if simplified_domain not in current_cookie_file_domains:
                    log(f"Found cookies for {simplified_domain} in file '{file.name}'", 20)
                    current_cookie_file_domains.add(simplified_domain)
                    if simplified_domain in domains_seen:
                        log(f"Previous cookies for domain {simplified_domain} detected. They will be overwritten", 30)
                domains_seen.add(simplified_domain)
                self.cookies.update_cookies({cookie.name: cookie.value}, response_url=URL(f"https://{cookie.domain}"))  # type: ignore

        log_spacer(20, log_to_console=False)
