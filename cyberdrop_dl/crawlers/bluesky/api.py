"https://endpoints.bsky.app"

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from cyberdrop_dl import aio
from cyberdrop_dl.crawlers.crawler import API
from cyberdrop_dl.url_objects import AbsoluteHttpURL

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator


class BlueSkyCAPI(API):
    ENTRYPOINT: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://api.bsky.app/xrpc")
    BLOB_ENDPOINT: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://bsky.social/xrpc/com.atproto.sync.getBlob")

    def __post_init__(self) -> None:
        self._did_cache: dict[str, str] = {}
        self._did_locks: aio.WeakAsyncLocks[str] = aio.WeakAsyncLocks()

    @classmethod
    def blob_url(cls, did: str, cid: str) -> AbsoluteHttpURL:
        return cls.BLOB_ENDPOINT.with_query(did=did, cid=cid)

    async def xrpc(self, path: str, **params: Any) -> dict[str, Any]:
        url = (self.ENTRYPOINT / path).with_query(params)
        return await self.request_json(url)

    async def resolve_handle(self, handle: str) -> str:
        if handle.startswith("did:"):
            return handle
        try:
            return self._did_cache[handle]
        except LookupError:
            pass

        async with self._did_locks[handle]:
            try:
                return self._did_cache[handle]
            except LookupError:
                pass

            resp = await self.xrpc("com.atproto.identity.resolveHandle", handle=handle)
            did = self._did_cache[handle] = resp["did"]
            return did

    async def thread(
        self,
        actor: str,
        post_id: str,
        *,
        depth: int = 100,  # How many replies
        parent_height: int = 0,  # How many parent replies
    ) -> tuple[dict[str, Any], Generator[dict[str, Any], None, None]]:
        did = await self.resolve_handle(actor)
        resp = await self.xrpc(
            "app.bsky.feed.getPostThread",
            uri=f"at://{did}/app.bsky.feed.post/{post_id}",
            depth=depth,
            parentHeight=parent_height,
        )

        thread = resp["thread"]
        original_post = thread["post"]

        pending: deque[dict[str, Any]] = deque()
        pending.extend(thread.get("replies", ()))

        def replies():
            while pending:
                node = pending.popleft()
                if node.get("$type") == "app.bsky.feed.defs#threadViewPost":
                    yield node["post"]
                    pending.extend(node.get("replies", ()))

        return original_post, replies()

    def author_feed(
        self,
        actor: str,
        filter: Literal[  # noqa: A002
            "posts_with_replies",
            "posts_no_replies",
            "posts_with_media",
            "posts_and_author_threads",
            "posts_with_video",
        ] = "posts_with_media",
    ) -> AsyncGenerator[list[dict[str, Any]]]:
        return self._paginate("app.bsky.feed.getAuthorFeed", actor=actor, filter=filter)

    async def _paginate(
        self,
        path: str,
        key: str = "feed",
        **params: Any,
    ) -> AsyncGenerator[list[dict[str, Any]]]:
        if "actor" in params:
            params["actor"] = await self.resolve_handle(params["actor"])

        params.setdefault("limit", 100)

        while True:
            resp: dict[str, Any] = await self.xrpc(path, *params)
            yield resp[key]
            params["cursor"] = cursor = resp.get("cursor")
            if not cursor:
                return
