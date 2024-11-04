from __future__ import annotations

import asyncio
import ssl
from http import HTTPStatus
from typing import TYPE_CHECKING, Optional

import aiohttp
import certifi
from aiohttp import ClientResponse, ContentTypeError
from aiolimiter import AsyncLimiter

from cyberdrop_dl.clients.download_client import DownloadClient
from cyberdrop_dl.clients.errors import DownloadFailure, DDOSGuardFailure, ScrapeFailure
from cyberdrop_dl.clients.scraper_client import ScraperClient
from cyberdrop_dl.managers.leaky import LeakyBucket
from cyberdrop_dl.utils.utilities import CustomHTTPStatus

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.scraper.crawler import ScrapeItem
    from yarl import URL

DOWNLOAD_ERROR_ETAGS = {
    "d835884373f4d6c8f24742ceabe74946": "Imgur image has been removed",
    "65b7753c-528a": "SC Scrape Image"
}


class ClientManager:
    """Creates a 'client' that can be referenced by scraping or download sessions"""

    def __init__(self, manager: Manager):
        self.manager = manager
        self.connection_timeout = manager.config_manager.global_settings_data['Rate_Limiting_Options'][
            'connection_timeout']
        self.read_timeout = manager.config_manager.global_settings_data['Rate_Limiting_Options']['read_timeout']
        self.rate_limit = manager.config_manager.global_settings_data['Rate_Limiting_Options']['rate_limit']

        self.download_delay = manager.config_manager.global_settings_data['Rate_Limiting_Options']['download_delay']
        self.user_agent = manager.config_manager.global_settings_data['General']['user_agent']
        self.verify_ssl = not manager.config_manager.global_settings_data['General']['allow_insecure_connections']
        self.simultaneous_per_domain = manager.config_manager.global_settings_data['Rate_Limiting_Options'][
            'max_simultaneous_downloads_per_domain']

        self.ssl_context = ssl.create_default_context(cafile=certifi.where()) if self.verify_ssl else False
        self.cookies = aiohttp.CookieJar(quote_cookie=False)
        self.proxy = manager.config_manager.global_settings_data['General'][
            'proxy'] if not manager.args_manager.proxy else manager.args_manager.proxy
        self.flaresolverr = manager.config_manager.global_settings_data['General'][
            'flaresolverr'] if not manager.args_manager.flaresolverr else manager.args_manager.flaresolverr

        self.domain_rate_limits = {
            "bunkrr": AsyncLimiter(5, 1),
            "cyberdrop": AsyncLimiter(5, 1),
            "coomer": AsyncLimiter(1, 1),
            "kemono": AsyncLimiter(1, 1),
            "pixeldrain": AsyncLimiter(10, 1),
            "other": AsyncLimiter(25, 1)
        }

        self.download_spacer = {'bunkr': 0.5, 'bunkrr': 0.5, 'cyberdrop': 0, 'cyberfile': 0, "pixeldrain": 0,
                                "coomer": 0.5, "kemono": 0.5}

        self.global_rate_limiter = AsyncLimiter(self.rate_limit, 1)
        self.session_limit = asyncio.Semaphore(50)
        self.download_session_limit = asyncio.Semaphore(
            self.manager.config_manager.global_settings_data['Rate_Limiting_Options']['max_simultaneous_downloads'])

        self.scraper_session = ScraperClient(self)
        self.downloader_session = DownloadClient(manager, self)
        self._leaky_bucket = LeakyBucket(manager)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def get_downloader_spacer(self, key: str) -> float:
        """Returns the download spacer for a domain"""
        if key in self.download_spacer:
            return self.download_spacer[key]
        return 0.1

    async def get_rate_limiter(self, domain: str) -> AsyncLimiter:
        """Get a rate limiter for a domain"""
        if domain in self.domain_rate_limits:
            return self.domain_rate_limits[domain]
        return self.domain_rate_limits["other"]

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @staticmethod
    async def check_http_status(response: ClientResponse, download: bool = False,
                                origin: Optional[ScrapeItem | URL] = None) -> None:
        """Checks the HTTP status code and raises an exception if it's not acceptable"""
        status = response.status
        headers = response.headers

        if download and headers.get('ETag') in DOWNLOAD_ERROR_ETAGS:
            message = DOWNLOAD_ERROR_ETAGS.get(headers.get('ETag'))
            raise DownloadFailure(HTTPStatus.NOT_FOUND, message=message, origin=origin)

        if HTTPStatus.OK <= status < HTTPStatus.BAD_REQUEST:
            return

        if any({domain in response.url.host.lower() for domain in ("gofile", "imgur")}):
            try:
                JSON_Resp: dict = await response.json()
                if "status" in JSON_Resp:
                    if "notFound" in JSON_Resp["status"]:
                        raise ScrapeFailure(HTTPStatus.NOT_FOUND, origin=origin)
                    if JSON_Resp.get('data') and 'error' in JSON_Resp['data']:
                        raise ScrapeFailure(JSON_Resp['status'], JSON_Resp['data']['error'], origin=origin)
            except ContentTypeError:
                pass

        try:
            response_text = await response.text()
            if "<title>DDoS-Guard</title>" in response_text:
                raise DDOSGuardFailure(origin=origin)
        except UnicodeDecodeError:
            pass

        if not headers.get('Content-Type'):
            raise DownloadFailure(status=CustomHTTPStatus.IM_A_TEAPOT, message="No content-type in response header",
                                origin=origin)

        raise DownloadFailure(status=status, origin=origin)

    @staticmethod
    async def check_bunkr_maint(headers):
        if headers.get('Content-Length') == "322509" and headers.get('Content-Type') == "video/mp4":
            raise DownloadFailure(status="Bunkr Maintenance", message="Bunkr under maintenance")

    async def check_bucket(self, size):
        await  self._leaky_bucket.acquire(size)
