from __future__ import annotations

import json
import os
from functools import wraps
from typing import TYPE_CHECKING, Dict, Optional

import aiohttp
from aiohttp_client_cache import CachedSession as ClientSession
from aiohttp_client_cache.response import CachedStreamReader
from bs4 import BeautifulSoup
from multidict import CIMultiDictProxy
from yarl import URL

from cyberdrop_dl.clients.errors import InvalidContentTypeFailure, DDOSGuardFailure, ScrapeFailure
from cyberdrop_dl.utils.utilities import log, log_request_type

if TYPE_CHECKING:
    from cyberdrop_dl.managers.client_manager import ClientManager


def limiter(func):
    """Wrapper handles limits for scrape session"""

    @wraps(func)
    async def wrapper(self: ScraperClient, *args, **kwargs):
        domain_limiter = await self.client_manager.get_rate_limiter(args[0])
        async with self.client_manager.session_limit:
            await self._global_limiter.acquire()
            await domain_limiter.acquire()

            async with ClientSession(headers=self._headers, raise_for_status=False,
                                             cookie_jar=self.client_manager.cookies, timeout=self._timeouts,
                                             trace_configs=self.trace_configs, cache=self.client_manager.manager.cache_manager.request_cache) as client:
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
    async def flaresolverr(self, domain: str, url: URL, client_session: ClientSession) -> str:
        """Returns the resolved URL from the given URL"""
        if not self.client_manager.flaresolverr:
            raise ScrapeFailure(status="DDOS-Guard", message="FlareSolverr is not configured")

        headers = {**self._headers, **{"Content-Type": "application/json"}}
        data = {"cmd": "request.get", "url": str(url), "maxTimeout": 60000}

        flaresolverr_server = URL(self.client_manager.flaresolverr)
        if not flaresolverr_server.scheme:
            flaresolverr_server = URL(f"http://{self.client_manager.flaresolverr}")

        async with client_session.disabled():
            async with client_session.post(flaresolverr_server / "v1", headers=headers,
                                       ssl=self.client_manager.ssl_context,
                                       proxy=self.client_manager.proxy, json=data) as response:
                json_obj = await response.json()
                status = json_obj.get("status")
                if status != "ok":
                    raise ScrapeFailure(status="DDOS-Guard", message="Failed to resolve URL with flaresolverr")

            # Update cookies
            for cookie in json_obj.get("solution").get("cookies"):
                self.client_manager.cookies.update_cookies({cookie["name"]: cookie["value"]}, response_url=cookie["domain"])
            # Update User-Agent for future requests
            self._headers["User-Agent"] = json_obj.get("solution").get("userAgent")

            return json_obj.get("solution").get("response")

    @limiter
    async def get_BS4(self, domain: str, url: URL, client_session: ClientSession, filter_fn: function = lambda x: True ) -> BeautifulSoup:
        """Returns a BeautifulSoup object from the given URL"""
        client_session.cache.filter_fn = filter_fn
        async with client_session.get(url, headers=self._headers, ssl=self.client_manager.ssl_context,
                                      proxy=self.client_manager.proxy) as response:
            await log_request_type(url,response.from_cache)
            try:
                await self.client_manager.check_http_status(response)
            except DDOSGuardFailure:
                response_text = await self.flaresolverr(domain, url)
                return BeautifulSoup(response_text, 'html.parser')
            content_type = response.headers.get('Content-Type')
            assert content_type is not None
            if not any(s in content_type.lower() for s in ("html", "text")):
                raise InvalidContentTypeFailure(message=f"Received {content_type}, was expecting text")
            text = await CachedStreamReader(await response.read()).read()
            bs4 = BeautifulSoup(text, 'html.parser')
            return bs4

    @limiter
    async def get_BS4_and_return_URL(self, domain: str, url: URL, client_session: ClientSession, filter_fn: function = lambda x: True) -> tuple[
        BeautifulSoup, URL]:
        """Returns a BeautifulSoup object and response URL from the given URL"""
        client_session.cache.filter_fn = filter_fn
        async with client_session.get(url, headers=self._headers, ssl=self.client_manager.ssl_context,
                                      proxy=self.client_manager.proxy) as response:
            await log_request_type(url,response.from_cache)
            await self.client_manager.check_http_status(response)
            content_type = response.headers.get('Content-Type')
            assert content_type is not None
            if not any(s in content_type.lower() for s in ("html", "text")):
                raise InvalidContentTypeFailure(message=f"Received {content_type}, was expecting text")
            text = await CachedStreamReader(await response.read()).read()
            return BeautifulSoup(text, 'html.parser'), URL(response.url)

    @limiter
    async def get_json(self, domain: str, url: URL, params: Optional[Dict] = None, headers_inc: Optional[Dict] = None,
                       client_session: ClientSession = None, filter_fn: function = lambda x: True) -> Dict:
        """Returns a JSON object from the given URL"""
        client_session.cache.filter_fn = filter_fn
        headers = {**self._headers, **headers_inc} if headers_inc else self._headers

        async with client_session.get(url, headers=headers, ssl=self.client_manager.ssl_context,
                                      proxy=self.client_manager.proxy, params=params) as response:
            await log_request_type(url,response.from_cache)
            await self.client_manager.check_http_status(response)
            content_type = response.headers.get('Content-Type')
            assert content_type is not None
            if 'json' not in content_type.lower():
                raise InvalidContentTypeFailure(message=f"Received {content_type}, was expecting JSON")
            return await response.json()

    @limiter
    async def get_text(self, domain: str, url: URL, client_session: ClientSession, filter_fn: function = lambda x: True) -> str:
        """Returns a text object from the given URL"""
        client_session.cache.filter_fn = filter_fn
        async with client_session.get(url, headers=self._headers, ssl=self.client_manager.ssl_context,
                                      proxy=self.client_manager.proxy) as response:
            await log_request_type(url,response.from_cache)
            try:
                await self.client_manager.check_http_status(response)
            except DDOSGuardFailure:
                response_text = await self.flaresolverr(domain, url)
                return response_text
            text = await CachedStreamReader(await response.read()).read()
            return text.decode('utf8')

    @limiter
    async def post_data(self, domain: str, url: URL, client_session: ClientSession, data: Dict,
                        req_resp: bool = True, filter_fn: function = lambda x: True) -> Dict:
        """Returns a JSON object from the given URL when posting data"""
        client_session.cache.filter_fn = filter_fn
        async with client_session.post(url, headers=self._headers, ssl=self.client_manager.ssl_context,
                                       proxy=self.client_manager.proxy, data=data) as response:
            await self.client_manager.check_http_status(response)
            if req_resp:
                return await response.json()
            else:
                return {}

    @limiter
    async def get_head(self, domain: str, url: URL, client_session: ClientSession, filter_fn: function = lambda x: True) -> CIMultiDictProxy[str]:
        """Returns the headers from the given URL"""
        client_session.cache.filter_fn = filter_fn
        async with client_session.head(url, headers=self._headers, ssl=self.client_manager.ssl_context,
                                       proxy=self.client_manager.proxy) as response:
            return response.headers
