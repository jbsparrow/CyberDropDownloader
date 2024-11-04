from __future__ import annotations

import json
import os
from functools import wraps
from typing import TYPE_CHECKING, Dict, Optional

import aiohttp
from aiohttp import ClientSession
from bs4 import BeautifulSoup
from multidict import CIMultiDictProxy
from yarl import URL

from cyberdrop_dl.clients.errors import InvalidContentTypeFailure, DDOSGuardFailure
from cyberdrop_dl.utils.utilities import log

if TYPE_CHECKING:
    from cyberdrop_dl.managers.client_manager import ClientManager
    from cyberdrop_dl.utils.dataclasses.url_objects import ScrapeItem


def limiter(func):
    """Wrapper handles limits for scrape session"""

    @wraps(func)
    async def wrapper(self: ScraperClient, *args, **kwargs):
        domain_limiter = await self.client_manager.get_rate_limiter(args[0])
        async with self.client_manager.session_limit:
            await self._global_limiter.acquire()
            await domain_limiter.acquire()

            async with aiohttp.ClientSession(headers=self._headers, raise_for_status=False,
                                            cookie_jar=self.client_manager.cookies, timeout=self._timeouts,
                                            trace_configs=self.trace_configs) as client:
                kwargs['client_session'] = client
                return await func(self, *args, **kwargs)

    return wrapper


class ScraperClient:
    """AIOHTTP operations for scraping"""

    def __init__(self, client_manager: ClientManager) -> None:
        self.client_manager = client_manager
        self._headers = {"user-agent": client_manager.user_agent}
        self._timeouts = aiohttp.ClientTimeout(total=client_manager.connection_timeout + 60,
                                            connect=client_manager.connection_timeout)
        self._global_limiter = self.client_manager.global_rate_limiter

        self.trace_configs = []
        if os.getenv("PYCHARM_HOSTED") is not None or 'TERM_PROGRAM' in os.environ.keys() and os.environ[
            'TERM_PROGRAM'] == 'vscode':
            async def on_request_start(session, trace_config_ctx, params):
                await log(f"Starting scrape {params.method} request to {params.url}", 10)

            async def on_request_end(session, trace_config_ctx, params):
                await log(f"Finishing scrape {params.method} request to {params.url}", 10)
                await log(f"Response status for {params.url}: {params.response.status}", 10)

            trace_config = aiohttp.TraceConfig()
            trace_config.on_request_start.append(on_request_start)
            trace_config.on_request_end.append(on_request_end)
            self.trace_configs.append(trace_config)

    @limiter
    async def flaresolverr(self, domain: str, url: URL, client_session: ClientSession,
                        origin: Optional[ScrapeItem | URL] = None, with_response_url: bool = False) -> str:
        """Returns the resolved URL from the given URL"""
        if not self.client_manager.flaresolverr:
            raise DDOSGuardFailure(message="FlareSolverr is not configured", origin=origin)

        headers = {**self._headers, **{"Content-Type": "application/json"}}
        data = {"cmd": "request.get", "url": str(url), "maxTimeout": 60000}

        async with client_session.post(f"http://{self.client_manager.flaresolverr}/v1", headers=headers,
                                    ssl=self.client_manager.ssl_context,
                                    proxy=self.client_manager.proxy, json=data) as response:
            json_obj: dict = await response.json()
            status = json_obj.get("status")
            if status != "ok":
                raise DDOSGuardFailure(message="Failed to resolve URL with flaresolverr", origin=origin)

            response = json_obj.get("solution").get("response")
            response_url = json_obj.get("solution").get("url")
            if with_response_url:
                return response , URL(response_url)
            return response


    @limiter
    async def get_BS4(self, domain: str, url: URL, client_session: ClientSession,
                    origin: Optional[ScrapeItem | URL] = None, with_response_url: bool = False) -> BeautifulSoup:
        """Returns a BeautifulSoup object from the given URL"""
        async with client_session.get(url, headers=self._headers, ssl=self.client_manager.ssl_context,
                                    proxy=self.client_manager.proxy) as response:
            try:
                await self.client_manager.check_http_status(response, origin=origin)
            except DDOSGuardFailure:
                response = await self.flaresolverr(domain, url, origin=origin, with_response_url=with_response_url)
                if with_response_url:
                    return BeautifulSoup(response[0], 'html.parser'), response[1]
                return BeautifulSoup(response, 'html.parser')
            
            content_type = response.headers.get('Content-Type')
            assert content_type is not None
            if not any(s in content_type.lower() for s in ("html", "text")):
                raise InvalidContentTypeFailure(message=f"Received {content_type}, was expecting text", origin=origin)
            text = await response.text()
            if with_response_url:
                return BeautifulSoup(text, 'html.parser'), URL(response.url)
            return BeautifulSoup(text, 'html.parser')

    async def get_BS4_and_return_URL(self, domain: str, url: URL,
                                    origin: Optional[ScrapeItem | URL] = None) -> tuple[
        BeautifulSoup, URL]:
        """Returns a BeautifulSoup object and response URL from the given URL"""
        return await self.get_BS4(domain, url, origin = origin, with_response_url = True)

    @limiter
    async def get_json(self, domain: str, url: URL, params: Optional[Dict] = None, headers_inc: Optional[Dict] = None,
                    client_session: ClientSession = None, origin: Optional[ScrapeItem | URL] = None) -> Dict:
        """Returns a JSON object from the given URL"""
        headers = {**self._headers, **headers_inc} if headers_inc else self._headers

        async with client_session.get(url, headers=headers, ssl=self.client_manager.ssl_context,
                                    proxy=self.client_manager.proxy, params=params) as response:
            await self.client_manager.check_http_status(response, origin=origin)
            content_type = response.headers.get('Content-Type')
            assert content_type is not None
            if 'json' not in content_type.lower():
                raise InvalidContentTypeFailure(message=f"Received {content_type}, was expecting JSON", origin=origin)
            return await response.json()

    @limiter
    async def get_text(self, domain: str, url: URL, client_session: ClientSession,
                    origin: Optional[ScrapeItem | URL] = None) -> str:
        """Returns a text object from the given URL"""
        async with client_session.get(url, headers=self._headers, ssl=self.client_manager.ssl_context,
                                    proxy=self.client_manager.proxy) as response:
            try:
                await self.client_manager.check_http_status(response, origin=origin)
            except DDOSGuardFailure:
                response_text = await self.flaresolverr(domain, url)
                return response_text
            text = await response.text()
            return text

    @limiter
    async def post_data(self, domain: str, url: URL, client_session: ClientSession, data: Dict,
                        req_resp: bool = True, raw: Optional[bool] = False,
                        origin: Optional[ScrapeItem | URL] = None) -> Dict:
        """Returns a JSON object from the given URL when posting data. If raw == True, returns raw binary data of response"""
        async with client_session.post(url, headers=self._headers, ssl=self.client_manager.ssl_context,
                                    proxy=self.client_manager.proxy, data=data) as response:
            await self.client_manager.check_http_status(response, origin=origin)
            if req_resp:
                content = await response.content.read()
                if raw:
                    return content
                return json.loads(content)
            else:
                return {}

    @limiter
    async def get_head(self, domain: str, url: URL, client_session: ClientSession) -> CIMultiDictProxy[str]:
        """Returns the headers from the given URL"""
        async with client_session.head(url, headers=self._headers, ssl=self.client_manager.ssl_context,
                                    proxy=self.client_manager.proxy) as response:
            return response.headers
