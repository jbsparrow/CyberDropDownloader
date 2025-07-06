from __future__ import annotations

import warnings
from contextlib import nullcontext
from typing import TYPE_CHECKING

from aiohttp import ClientResponse, ClientSession
from aiohttp_client_cache.backends import get_valid_kwargs
from aiohttp_client_cache.session import CacheMixin
from aiohttp_client_cache.signatures import extend_signature

if TYPE_CHECKING:
    from aiohttp.typedefs import StrOrURL
    from aiolimiter import AsyncLimiter

    MIXIN_BASE = ClientSession

else:
    MIXIN_BASE = object

with warnings.catch_warnings():
    warnings.simplefilter("ignore")

    class LimiterMixin(MIXIN_BASE):
        """A mixin class for `aiohttp.ClientSession` that adds async limiter support by headers"""

        @extend_signature(ClientSession.__init__)
        def __init__(
            self,
            base_url: StrOrURL | None = None,
            *,
            crawler_limiters: dict[str, AsyncLimiter] | None = None,
            **kwargs,
        ) -> None:
            self._crawler_limiters = crawler_limiters or {}
            self._null_cdl_limiter = nullcontext()
            session_kwargs = get_valid_kwargs(super().__init__, {**kwargs, "base_url": base_url})
            super().__init__(**session_kwargs)

        @extend_signature(ClientSession._request)
        async def _request(
            self,
            method: str,
            str_or_url: StrOrURL,
            **kwargs,
        ) -> ClientResponse:
            headers = self._prepare_headers(kwargs.get("headers"))
            if domain := headers.pop("CDL_DOMAIN", None):
                limiter = self._crawler_limiters[domain]
            else:
                limiter = self._null_cdl_limiter

            kwargs["headers"] = headers
            async with limiter:
                return await super()._request(method, str_or_url, **kwargs)

    class CDLCachedSession(CacheMixin, LimiterMixin, ClientSession):
        async def __aenter__(self) -> CDLCachedSession:
            return self
