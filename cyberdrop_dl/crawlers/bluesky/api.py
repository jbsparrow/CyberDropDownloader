from __future__ import annotations

import asyncio
from collections import deque
from typing import TYPE_CHECKING, Any, ClassVar

from cyberdrop_dl.crawlers.crawler import API
from cyberdrop_dl.url_objects import AbsoluteHttpURL

_BLOB_ENDPOINT = AbsoluteHttpURL("https://bsky.social/xrpc/com.atproto.sync.getBlob")

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Iterable

    from cyberdrop_dl.cache import TTLCacheAdapter
    from cyberdrop_dl.clients.http import HTTPClient, HTTPContext
    from cyberdrop_dl.config import Config


class BlueskyAPI(API):
    ENTRYPOINT: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://api.bsky.app/xrpc")

    def __init__(
        self,
        domain: str,
        config: Config,
        cache: TTLCacheAdapter[Any],
        client: HTTPClient,
        ctx: HTTPContext | None = None,
    ) -> None:
        super().__init__(domain, config, cache, client, ctx)
        self._handle_cache: dict[str, str] = {}
        self._handle_locks: dict[str, asyncio.Lock] = {}

    @staticmethod
    def blob_url(did: str, cid: str) -> AbsoluteHttpURL:
        params: dict[str, Any] = {"did": did, "cid": cid}
        return _BLOB_ENDPOINT.with_query(params)

    async def resolve_handle(self, actor: str) -> str:
        if actor.startswith("did:"):
            return actor

        if actor in self._handle_cache:
            return self._handle_cache[actor]

        lock = self._handle_locks.setdefault(actor, asyncio.Lock())

        async with lock:
            if actor in self._handle_cache:
                return self._handle_cache[actor]

            url = (self.ENTRYPOINT / "com.atproto.identity.resolveHandle").with_query(handle=actor)
            response: dict[str, str] = await self.request_json(url)
            did = response["did"]

            self._handle_cache[actor] = did
            self._handle_locks.pop(actor, None)

            return did

    async def profile(self, actor: str) -> dict[str, Any]:
        actor_did = await self.resolve_handle(actor)
        url = (self.ENTRYPOINT / "app.bsky.actor.getProfile").with_query(actor=actor_did)
        return await self.request_json(url)

    async def post_thread(
        self, actor: str, post_id: str, depth: int = 100, parent_height: int = 0
    ) -> list[dict[str, Any]]:
        actor_did = await self.resolve_handle(actor)
        url = (self.ENTRYPOINT / "app.bsky.feed.getPostThread").with_query(
            uri=f"at://{actor_did}/app.bsky.feed.post/{post_id}", depth=depth, parentHeight=parent_height
        )
        response: dict[str, Any] = await self.request_json(url)
        pending = deque()
        pending.append(response["thread"])

        def posts():
            while pending:
                thread = pending.popleft()
                if thread.get("$type") != "app.bsky.feed.defs#threadViewPost":
                    continue
                yield (thread["post"])
                pending.extend(thread.get("replies", ()))

        return posts()

    def author_feed(
        self, actor: str, feed_filter: str = "posts_with_media"
    ) -> AsyncGenerator[Iterable[dict[str, Any]]]:
        return self._paginate(
            "app.bsky.feed.getAuthorFeed",
            {"actor": actor, "filter": feed_filter},
        )

    async def _paginate(
        self, endpoint: str, params: dict[str, Any], *, key: str = "feed"
    ) -> AsyncGenerator[Iterable[dict[str, Any]]]:
        if "actor" in params:
            params["actor"] = await self.resolve_handle(params["actor"])

        while True:
            url = (self.ENTRYPOINT / endpoint).with_query(params)
            response: dict[str, Any] = await self.request_json(url)
            yield response.get(key, response.get("posts", ()))
            cursor = response.get("cursor")
            if not cursor:
                return
            params["cursor"] = cursor
