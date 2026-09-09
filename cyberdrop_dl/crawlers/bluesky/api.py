from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Any, ClassVar

from cyberdrop_dl.crawlers.crawler import API
from cyberdrop_dl.url_objects import AbsoluteHttpURL

_PAGE_SIZE = 100
_BLOB_ENDPOINT = AbsoluteHttpURL("https://bsky.social/xrpc/com.atproto.sync.getBlob")

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Iterable


class BlueskyAPI(API):
    ENTRYPOINT: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://api.bsky.app/xrpc")

    @staticmethod
    def blob_url(did: str, cid: str) -> AbsoluteHttpURL:
        params: dict[str, Any] = {"did": did, "cid": cid}
        return _BLOB_ENDPOINT.with_query(params)

    async def resolve_handle(self, actor: str) -> str:
        if actor.startswith("did:"):
            return actor
        url = (self.ENTRYPOINT / "com.atproto.identity.resolveHandle").with_query(handle=actor)
        response: dict[str, str] = await self.request_json(url)
        return response["did"]

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
            {"actor": actor, "filter": feed_filter, "limit": _PAGE_SIZE},
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
