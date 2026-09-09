# https://docs.fxembed.com/api/twitter/
# https://github.com/FxEmbed/FxEmbed
from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, ClassVar, Final, Literal, Unpack

from cyberdrop_dl import env
from cyberdrop_dl.cache import disk_cached_method
from cyberdrop_dl.clients.http import HTTPConfig
from cyberdrop_dl.crawlers.crawler import API
from cyberdrop_dl.crawlers.twitter.models import Broadcast, Tweet
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.url_objects import AbsoluteHttpURL

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator

    from cyberdrop_dl.clients import HttpMethod
    from cyberdrop_dl.clients.request import RequestParams


@HTTPConfig(rate_limit=(3, 1))  # Actual limit is 1000 req/min (~ 16.7 req/s) per IP
class FXTwitterAPI(API):
    ENTRYPOINT: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://api.fxtwitter.com/2")
    cursor: ClassVar[ContextVar[str | None]] = ContextVar("cursor")
    since: ClassVar[ContextVar[int | None]] = ContextVar("since")

    def __post_init__(self) -> None:
        self.user: UserEndpoint = UserEndpoint(self)

    async def tweet(self, status_id: str) -> Tweet:
        url = self.ENTRYPOINT / "status" / status_id
        resp = await self.request_json(url)
        return Tweet.model_validate(resp)

    async def thread(self, status_id: str) -> map[Tweet]:
        url = self.ENTRYPOINT / "thread" / status_id
        resp = await self.request_json(url)
        # filter out deleted tweets ( "type" == "tombstone")
        tweets = (t for t in resp["thread"] if t["type"] == "status")
        return map(Tweet.model_validate, tweets)

    @classmethod
    def build_gql_search_query(
        cls,
        query: str | None = None,
        *,
        user_screen_name: str | None = None,
        max_tweet_id: str | None = None,
        include_retweets: bool = False,
        include_text_only: bool = False,
    ) -> str:
        def parts() -> Generator[str]:
            if user_screen_name:
                yield f"from:{user_screen_name}"
            if max_tweet_id:
                yield f"max_id:{max_tweet_id}"
            if include_retweets:
                yield "include:nativeretweets"
                yield "include:retweets"
            if not include_text_only:
                yield "filter:links"
            if query:
                yield query

        return " ".join(parts())

    def search(self, query: str, feed: Literal["latest", "top", "media"] = "latest") -> AsyncGenerator[map[Tweet]]:
        url = (self.ENTRYPOINT / "search").with_query(q=query, feed=feed)
        return self.pager(url)

    async def pager(self, url: AbsoluteHttpURL) -> AsyncGenerator[map[Tweet]]:
        url = url.update_query(count=100)
        if cursor := self.cursor.get():
            url = url.update_query(cursor=cursor)
        if since := self.since.get():
            url = url.update_query(since=since)

        empty_pages: int = 0
        while True:
            resp = await self.request_json(url)
            if resp["results"]:
                empty_pages = 0
                yield map(Tweet.model_validate, resp["results"])
            else:
                empty_pages += 1
            cursor = resp["cursor"].get("bottom")
            self.cursor.set(cursor)
            if not cursor or url.query.get("cursor") == cursor:
                break
            if empty_pages >= env.TWITTER_MAX_EMPTY_PAGES:
                self.log.warning("Stopping pagination on %s after %s empty responses", url, empty_pages)
                break
            url = url.update_query(cursor=cursor)


class UserEndpoint(API.Endpoint[FXTwitterAPI]):
    def media(self, user: str) -> AsyncGenerator[map[Tweet]]:
        url = self.api.ENTRYPOINT / "profile" / user / "media"
        return self.api.pager(url)

    def tweets(self, user: str) -> AsyncGenerator[map[Tweet]]:
        url = self.api.ENTRYPOINT / "profile" / user / "statuses"
        return self.api.pager(url)


_DEFAULT_CRED = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)


@HTTPConfig(
    headers={
        "Accept": "*/*",
        "Referer": "https://x.com/",
        "content-type": "application/json",
        "x-twitter-client-language": "en",
        "x-twitter-active-user": "yes",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Authorization": f"Bearer {_DEFAULT_CRED}",
    }
)
class TwitterAPI(API):
    ENTRYPOINT: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://api.x.com/1.1")

    def __post_init__(self) -> None:
        self.broadcast: BroadcastEndpoint = BroadcastEndpoint(self)

    @disk_cached_method("guest_token", ttl=3600)
    async def auth_guest(self) -> str:
        url = self.ENTRYPOINT / "guest/activate.json"
        resp = await self.request_json(url, "POST", data=b"")
        return resp["guest_token"]

    async def request_json(
        self,
        url: AbsoluteHttpURL,
        method: HttpMethod = "GET",
        auth: bool = False,  # noqa: FBT001, FBT002
        **kwargs: Unpack[RequestParams],
    ) -> Any:
        if morsel := self.client.cookies.filter_cookies(self.PRIMARY_URL).get("ct0"):
            self.__http_ctx__.headers["x-csrf-token"] = morsel.value

        if auth:
            kwargs.setdefault("headers", {})["x-guest-token"] = await self.auth_guest()

        async with self.request(url, method, **kwargs) as resp:
            return await resp.json(content_type=False)


class BroadcastEndpoint(API.Endpoint[TwitterAPI]):
    ENDED: Final = "ENDED"

    async def __call__(self, broadcast_id: str) -> Broadcast:
        url = (self.api.ENTRYPOINT / "broadcasts/show.json").with_query(ids=broadcast_id)
        resp = await self.api.request_json(url)
        return self._parse(resp["broadcasts"][broadcast_id])

    async def event(self, event_id: str) -> Broadcast:
        url = self.api.ENTRYPOINT / "live_event/1" / event_id / "timeline.json"
        resp = await self.api.request_json(url, auth=True)
        bds_entries: dict[str, dict[str, Any]] = resp["twitter_objects"]["broadcasts"]
        return self._parse(next(iter(bds_entries.values())))

    def _parse(self, bd: dict[str, Any]) -> Broadcast:
        if not bd:
            raise ScrapeError(404)
        state: str = bd.setdefault("state", self.ENDED)
        if state != self.ENDED:
            raise ScrapeError(422, f"{state} broadcasts are not supported")
        return Broadcast.model_validate(bd)

    async def stream(self, media_key: str) -> AbsoluteHttpURL:
        url = self.api.ENTRYPOINT / "live_video_stream/status" / media_key
        source = (await self.api.request_json(url))["source"]
        url = self.api.parse_url(source.get("noRedirectPlaybackUrl") or source["location"])
        if "geoblocked" in url.parts:
            raise ScrapeError(403, "Broadcast not available in this location")
        return url
