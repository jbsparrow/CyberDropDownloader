from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, TypeGuard

from cyberdrop_dl.crawlers.bluesky.api import BlueSkyAPI
from cyberdrop_dl.crawlers.bluesky.types import Media
from cyberdrop_dl.crawlers.crawler import Crawler, SupportedDomains, SupportedPaths
from cyberdrop_dl.mediaprops import Resolution
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import operators, traversal
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping

    from cyberdrop_dl.crawlers.bluesky.types import Blob, FeedFilter, LegacyBlob, PostView
    from cyberdrop_dl.url_objects import ScrapeItem


@Crawler.db_path_builder("path_qs")
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

        for media in _extract_media(post.record):
            self.create_eager_task(self._media(scrape_item, media, post.author.did))
            scrape_item.add_children()

    async def _media(self, scrape_item: ScrapeItem, media: Media, did: str) -> None:
        src = await self.api.get_blob(did, media.cid)
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


def _extract_media(record: Mapping[str, Any]) -> Generator[Media]:

    def is_blob(_: object, data: object) -> TypeGuard[Blob | LegacyBlob]:
        return type(data) is dict and (data.get("$type") == "blob" or data.keys() == {"cid", "mimeType"})

    for path, blob in traversal.traverse(record, is_blob):
        blob = _normalize_blob(blob)
        asset_path = path[:-1]
        asset = operators.nested_itemgetter(*asset_path)(record) if asset_path else record
        cid = blob["ref"]["$link"]
        yield Media(
            type=asset.get("$type") or str(asset_path or "<UNKNOWN>"),
            cid=cid,
            name=asset.get("alt") or cid,
            mime=blob["mimeType"],
            aspect_ratio=Resolution(**ratio) if (ratio := asset.get("aspectRatio")) else None,
        )


def _normalize_blob(blob: Blob | LegacyBlob) -> Blob:
    # https://atproto.com/specs/data-model#blob-type
    # https://atproto.com/specs/data-model#usage-and-implementation-guidelines
    if "cid" in blob:
        return {
            "$type": "blob",
            "ref": {
                "$link": blob["cid"],
            },
            "mimeType": blob["mimeType"],
            "size": -1,
        }
    return blob
