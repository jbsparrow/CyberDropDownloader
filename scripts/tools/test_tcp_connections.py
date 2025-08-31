# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "aiodns",
#     "aiohttp",
#     "certifi",
#     "requests",
#     "truststore",
# ]
# ///
from __future__ import annotations

import asyncio
import logging
import ssl
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import aiohttp
import aiohttp.abc
import certifi
import requests
import truststore

if TYPE_CHECKING:
    from collections.abc import Awaitable, Iterable


logger = logging.getLogger(__name__)


_ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
_ssl_context.load_verify_locations(cafile=certifi.where())
_aio_timeout = aiohttp.ClientTimeout(connect=30, sock_read=20)
_semaphore = asyncio.BoundedSemaphore(50)


def _setup_logger(log_level: int = logging.INFO) -> None:
    now = datetime.now().replace(microsecond=0).isoformat()
    script_path = Path(__file__).resolve()
    log_file_name = f"{script_path.stem}_{now.replace(':', '')}.log"
    log_file_path = script_path.with_name(log_file_name)
    logger.setLevel(log_level)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    def add_handler(handler: logging.Handler):
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    add_handler(logging.StreamHandler(sys.stdout))
    add_handler(logging.FileHandler(log_file_path, mode="w", encoding="utf-8"))


def _new_tcp_conn(resolver_cls: type[aiohttp.abc.AbstractResolver]) -> aiohttp.TCPConnector:
    conn = aiohttp.TCPConnector(ssl=_ssl_context, resolver=resolver_cls())
    return conn


async def _request(url) -> int:
    resp = await asyncio.to_thread(requests.get, url, timeout=(30, 20))
    return resp.status_code


async def _aio_request(url: str, tcp_conn: aiohttp.BaseConnector) -> int:
    async with aiohttp.request(
        "GET",
        url,
        ssl=_ssl_context,
        timeout=_aio_timeout,
        connector=tcp_conn,
    ) as resp:
        return resp.status


async def _run_test(name: str, coro: Awaitable[int]) -> None:
    try:
        status = await coro
        logger.info(f"{name} - status: {status}")
    except Exception as e:
        logger.error(f"{name} - Error: {e}")
    finally:
        _semaphore.release()


async def _test_resolvers(urls: Iterable[str]) -> None:
    _setup_logger()

    names = "requests", "aiohttp [ThreadedDNSResolver]", "aiohttp [AsyncDNSResolver]"
    names = [n.ljust(len(max(names, key=len))) for n in names]

    async with (
        _new_tcp_conn(aiohttp.AsyncResolver) as async_conn,
        _new_tcp_conn(aiohttp.ThreadedResolver) as threaded_conn,
        asyncio.TaskGroup() as tg,
    ):
        for url in urls:
            coros = _request(url), _aio_request(url, threaded_conn), _aio_request(url, async_conn)
            for name, coro in zip(names, coros, strict=True):
                await _semaphore.acquire()
                tg.create_task(_run_test(f"{name} - {url}", coro))


if __name__ == "__main__":
    urls = sys.argv[1:]
    if not urls:
        print(f"Usage: python {__file__} <URLS>")  # noqa: T201
        sys.exit(1)

    asyncio.run(_test_resolvers(urls))
