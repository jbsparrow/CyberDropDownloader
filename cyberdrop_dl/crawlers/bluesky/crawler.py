from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Literal, cast

from cyberdrop_dl.crawlers.bluesky.api import BlueSkyAPI
from cyberdrop_dl.crawlers.bluesky.types import Media
from cyberdrop_dl.crawlers.crawler import Crawler, SupportedDomains, SupportedPaths
from cyberdrop_dl.mediaprops import Resolution
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Generator

    from cyberdrop_dl.crawlers.bluesky.types import Blob, FeedFilter, Image, MediaAsset, PostView, Video
    from cyberdrop_dl.url_objects import ScrapeItem


class BlueskyCrawler(Crawler):
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = "bsky.app", "bsky.social", "main.bsky.dev"
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Post": "/profile/<handle>/post/<post_id>",
        "Profile": "/profile/<handle>",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://bsky.app")
    DOMAIN: ClassVar[str] = "bluesky"
    FOLDER_DOMAIN: ClassVar[str] = "BlueSky"
    DEFAULT_POST_TITLE_FORMAT: ClassVar[str] = "{date:%Y-%m-%d} - {id}"

    def __post_init__(self) -> None:
        self.api: BlueSkyAPI = BlueSkyAPI.from_crawler(self)

    @property
    def separate_posts(self) -> bool:
        return True

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["profile", user, "post", post_id, *_]:
                await self.post(scrape_item, user, post_id)
            case ["profile", user]:
                await self.user(scrape_item, user, "posts_and_author_threads")
            case _:
                raise ValueError

    @error_handling_wrapper
    async def post(self, scrape_item: ScrapeItem, actor: str, post_id: str) -> None:
        post, replies = await self.api.thread(actor, post_id)
        self._post(scrape_item, post)
        for reply in replies:
            new_item = scrape_item.create_child(self.PRIMARY_URL / reply.web_path)
            self._post(new_item, reply)
            scrape_item.add_children()

    @error_handling_wrapper
    async def user(self, scrape_item: ScrapeItem, actor: str, feed_filter: FeedFilter) -> None:
        scrape_item.setup_as_profile("")
        async for post in self.api.author_feed(actor, feed_filter):
            new_item = scrape_item.create_child(self.PRIMARY_URL / post.web_path)
            self._post(new_item, post)
            scrape_item.add_children()

    @error_handling_wrapper
    def _post(self, scrape_item: ScrapeItem, post: PostView) -> None:
        scrape_item.setup_as_post(self.create_title(f"@{post.author.handle}"))
        scrape_item.uploaded_at = date = self.parse_iso_date(post.record["createdAt"])
        scrape_item.append_folders(self.create_separate_post_title(None, post.id, date))
        self.create_eager_task(self.write_metadata(scrape_item, f"post {post.id}", post))

        for media in _extract_media(post):
            self.create_eager_task(self._media(scrape_item, media, post.author.did))
            scrape_item.add_children()

    async def _media(self, scrape_item: ScrapeItem, media: Media, did: str) -> None:
        src = self.api.get_blob(did, media.cid)
        with self.catch_errors(src):
            name, ext = self.get_filename_and_ext(media.name, mime_type=media.mime)
            await self.handle_file(
                src,
                scrape_item,
                name,
                ext,
                custom_filename=name,
                metadata=media,
            )


def _extract_media(post: PostView) -> Generator[Media]:
    embed = post.record.get("embed")
    if not embed:
        return

    embed["type"] = embed["$type"]
    embed = cast("MediaAsset", embed)  # pyright: ignore[reportInvalidCast]

    match embed["type"]:
        case "app.bsky.embed.images":
            for img in embed["images"]:
                yield parse_asset(img, "image")
        case "app.bsky.embed.gallery":
            for item in embed["items"]:
                yield parse_asset(item, "image" if "image" in item else "video")
        case "app.bsky.embed.image":
            yield parse_asset(embed, "image")
        case "app.bsky.embed.video":
            yield parse_asset(embed, "video")
        case "app.bsky.embed.record" | "app.bsky.embed.recordWithMedia":
            # TODO: handle this
            pass
        case _:
            raise ValueError(embed)


def parse_asset(asset: Image | Video, key: Literal["image", "video"]) -> Media:
    # TODO: handle video captions
    res = Resolution(**ratio) if (ratio := asset.get("aspectRatio")) else None
    blob: Blob = asset[key]  # pyright: ignore[reportGeneralTypeIssues]
    cid = blob["ref"]["$link"]
    return Media(
        type=key,
        cid=cid,
        name=asset.get("alt") or cid,
        mime=blob["mimeType"],
        resolution=res,
    )
