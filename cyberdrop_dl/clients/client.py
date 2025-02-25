from __future__ import annotations

import typing
from functools import wraps

import aiohttp
from aiohttp_client_cache.session import CachedSession

from cyberdrop_dl.utils.logger import log_debug

if typing.TYPE_CHECKING:
    from collections.abc import Callable

    from cyberdrop_dl.managers.client_manager import ClientManager


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

    def __init__(self, client_manager: ClientManager) -> None:
        self.manager = client_manager.manager
        self.client_manager = client_manager
        self.headers: dict = {"user-agent": self.client_manager.user_agent}
        self.trace_configs: list[aiohttp.TraceConfig] = []
        assert self.request_log_hooks_name, "Subclasses must override hooks name"
        add_request_log_hooks(self.trace_configs, self.request_log_hooks_name)

    @property
    def request_params(self) -> dict:
        return {"headers": self.headers, "ssl": self.client_manager.ssl_context, "proxy": self.client_manager.proxy}


def add_request_log_hooks(trace_configs: list[aiohttp.TraceConfig], name: str) -> None:
    async def on_request_start(*args):
        params: aiohttp.TraceRequestStartParams = args[2]
        log_debug(f"Starting {name} {params.method} request to {params.url}")

    async def on_request_end(*args):
        params: aiohttp.TraceRequestEndParams = args[2]
        msg = f"Finishing {name}  {params.method} request to {params.url}"
        msg += f" -> response status: {params.response.status}"
        log_debug(msg)

    trace_config = aiohttp.TraceConfig()
    trace_config.on_request_start.append(on_request_start)
    trace_config.on_request_end.append(on_request_end)
    trace_configs.append(trace_config)
