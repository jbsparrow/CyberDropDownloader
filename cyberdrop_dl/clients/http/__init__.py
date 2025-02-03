from __future__ import annotations

import typing
from functools import wraps

import aiohttp
from aiohttp_client_cache.session import CachedSession

from cyberdrop_dl.utils import constants
from cyberdrop_dl.utils.logger import log

if typing.TYPE_CHECKING:
    from collections.abc import Callable

    from multidict import CIMultiDictProxy
    from yarl import URL

    from cyberdrop_dl.managers.manager import Manager


def create_session(_, arg: Callable = str) -> Callable:
    """Wrapper handles client session creation to pass cookies."""
    func = _
    if typing.TYPE_CHECKING:
        func = arg

    @wraps(func)
    async def wrapper(self: Client, *args, **kwargs):
        async with CachedSession(
            headers=self.headers,
            cookie_jar=self.client_manager.cookies,
            timeout=self.client_manager.timeout,
            trace_configs=self.trace_configs,
            cache=self.client_manager.manager.cache_manager.request_cache,
        ) as client:
            kwargs["client_session"] = client
            return await func(self, *args, **kwargs)

    return wrapper


class Client:
    """AIOHTTP operations."""

    request_log_hooks_name = ""

    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self.client_manager = manager.client_manager
        self.headers: dict = {"user-agent": self.client_manager.user_agent}
        self.trace_configs: list[aiohttp.TraceConfig] = []
        if constants.DEBUG_VAR:
            self.add_request_log_hooks()

    def add_request_log_hooks(self) -> None:
        assert self.request_log_hooks_name, "Subclasses must override hooks name"

        async def on_request_start(*args):
            params: aiohttp.TraceRequestStartParams = args[2]
            log(f"Starting {self.request_log_hooks_name} {params.method} request to {params.url}", 10)

        async def on_request_end(*args):
            params: aiohttp.TraceRequestEndParams = args[2]
            msg = f"Finishing {self.request_log_hooks_name}  {params.method} request to {params.url}"
            msg += f" -> response status: {params.response.status}"
            log(msg, 10)

        trace_config = aiohttp.TraceConfig()
        trace_config.on_request_start.append(on_request_start)
        trace_config.on_request_end.append(on_request_end)
        self.trace_configs.append(trace_config)

    @property
    def request_params(self) -> dict:
        params = {"headers": self.headers, "ssl": self.client_manager.ssl_context, "proxy": self.client_manager.proxy}
        return params

    @create_session
    async def get_head(self, url: URL, client_session: CachedSession) -> CIMultiDictProxy[str]:
        """Returns the headers from the given URL."""
        async with client_session.head(url, **self.request_params) as response:
            return response.headers
