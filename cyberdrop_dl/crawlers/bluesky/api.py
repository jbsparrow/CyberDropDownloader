"""https://endpoints.bsky.app
https://github.com/bluesky-social/atproto
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Any, ClassVar

from cyberdrop_dl import aio
from cyberdrop_dl.crawlers.bluesky.types import FeedFilter, PostView
from cyberdrop_dl.crawlers.crawler import API
from cyberdrop_dl.url_objects import AbsoluteHttpURL

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator, Iterable


class BlueSkyCAPI(API):
    ENTRYPOINT: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://api.bsky.app/xrpc")
    BLOB_ENDPOINT: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://bsky.social/xrpc/com.atproto.sync.getBlob")

    def __post_init__(self) -> None:
        self._did_cache: dict[str, str] = {}
        self._did_locks: aio.WeakAsyncLocks[str] = aio.WeakAsyncLocks()

    @classmethod
    def get_blob(cls, did: str, cid: str) -> AbsoluteHttpURL:
        # did: desentralized ID, cid: content ID (hash)
        return cls.BLOB_ENDPOINT.with_query(did=did, cid=cid)

    async def xrpc(self, path: str, **params: Any) -> dict[str, Any]:
        url = (self.ENTRYPOINT / path).with_query(params)
        return await self.request_json(url)

    async def resolve_handle(self, handle_or_did: str) -> str:
        if handle_or_did.startswith("did:"):
            return handle_or_did
        try:
            return self._did_cache[handle_or_did]
        except LookupError:
            pass

        async with self._did_locks[handle_or_did]:
            try:
                return self._did_cache[handle_or_did]
            except LookupError:
                pass

            resp = await self.xrpc("com.atproto.identity.resolveHandle", handle=handle_or_did)
            did = self._did_cache[handle_or_did] = resp["did"]
            return did

    async def thread(
        self,
        actor: str,
        post_id: str,
        *,
        depth: int = 100,  # How many replies
        parent_height: int = 0,  # How many parent replies
    ) -> tuple[PostView, Generator[PostView]]:
        did = await self.resolve_handle(actor)
        resp = await self.xrpc(
            "app.bsky.feed.getPostThread",
            uri=f"at://{did}/app.bsky.feed.post/{post_id}",
            depth=depth,
            parentHeight=parent_height,
        )

        thread = resp["thread"]
        og_post = PostView.parse(thread["post"])

        thread_replies: deque[dict[str, Any]] = deque()
        thread_replies.extend(_filter_blocked_replies(thread.get("replies", ())))

        def replies() -> Generator[PostView]:
            while thread_replies:
                reply = thread_replies.popleft()
                yield PostView.parse(reply["post"])
                thread_replies.extend(_filter_blocked_replies(reply.get("replies", ())))

        return og_post, replies()

    async def author_feed(
        self,
        actor: str,
        feed_filter: FeedFilter = "posts_with_media",
    ) -> AsyncGenerator[PostView]:
        async for page in self.pager("app.bsky.feed.getAuthorFeed", actor=actor, filter=feed_filter):
            for post in page:
                yield PostView.parse(post["post"])

    async def pager(
        self,
        path: str,
        key: str = "feed",
        **params: Any,
    ) -> AsyncGenerator[list[dict[str, Any]]]:
        if "actor" in params:
            params["actor"] = await self.resolve_handle(params["actor"])

        params.setdefault("limit", 100)

        while True:
            resp = await self.xrpc(path, **params)
            yield resp[key]
            params["cursor"] = cursor = resp.get("cursor")
            if not cursor:
                return


def _filter_blocked_replies(replies: Iterable[dict[str, Any]]) -> Generator[dict[str, Any]]:
    for reply in replies:
        if reply.get("not_found") or reply.get("blocked") or reply.get("$type") != "app.bsky.feed.defs#threadViewPost":
            continue
        yield reply
