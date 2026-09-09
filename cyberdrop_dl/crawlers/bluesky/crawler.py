from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any, ClassVar

from cyberdrop_dl.crawlers.bluesky.api import BlueskyAPI
from cyberdrop_dl.crawlers.crawler import Crawler, SupportedDomains, SupportedPaths
from cyberdrop_dl.mediaprops import Resolution
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Generator

    from cyberdrop_dl.url_objects import ScrapeItem


@dataclasses.dataclass
class MediaInfo:
    source_url: AbsoluteHttpURL
    cid: str
    ext: str
    debrid_link: AbsoluteHttpURL | None


class BlueskyCrawler(Crawler):
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = ("bsky.app", "bsky.social", "main.bsky.dev")
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Post": "/profile/<handle>/post/<post_id>",
        "Profile": "/profile/<handle>",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://bsky.app")
    DOMAIN: ClassVar[str] = "bluesky"
    DEFAULT_POST_TITLE_FORMAT: ClassVar[str] = "{date:%Y-%m-%d} - {id}"

    def __post_init__(self) -> None:
        self.api: BlueskyAPI = BlueskyAPI.from_crawler(self)

    @property
    def separate_posts(self) -> bool:
        return True

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        parts = scrape_item.url.parts[1:]
        match parts:
            case ["profile", user, "post", post_id, *_]:
                await self.post(scrape_item, user, post_id)
            case ["profile", user]:
                await self.user(scrape_item, user, "posts_and_author_threads")
            case _:
                raise ValueError

    @error_handling_wrapper
    async def post(self, scrape_item: ScrapeItem, actor: str, post_id: str) -> None:
        original_post, replies = await self.api.post_thread(actor, post_id)
        self._post(scrape_item, original_post)
        for reply in replies:
            new_item = scrape_item.create_child(self._post_url(reply))
            self._post(new_item, reply)
            scrape_item.add_children()

    @error_handling_wrapper
    async def user(self, scrape_item: ScrapeItem, actor: str, feed_filter: str) -> None:
        scrape_item.setup_as_profile("")
        async for page in self.api.author_feed(actor, feed_filter):
            for entry in page:
                post = entry.get("post", entry)
                new_item = scrape_item.create_child(self.parse_url(self._post_url(post)))
                self._post(new_item, post)
                scrape_item.add_children()

    @error_handling_wrapper
    def _post(self, scrape_item: ScrapeItem, post: dict[str, Any]) -> None:
        record = post["record"]
        author = post["author"]
        post_id = post["uri"].rpartition("/")[2]
        scrape_item.setup_as_post(self.create_title(f"@{author['handle']}"))
        scrape_item.uploaded_at = date = self.parse_iso_date(record["createdAt"])
        scrape_item.append_folders(self.create_separate_post_title(None, post_id, date))
        self.create_eager_task(self.write_metadata(scrape_item, f"post {post_id}", post))

        embed = post.get("embed", {})
        self._extract_videos(scrape_item, embed, post_id)
        record_embed = record.get("embed", {})
        record_images = record_embed.get("images", record_embed.get("media", {}).get("images", ()))
        self._extract_images(scrape_item, embed, record_images, author["did"])

    def _extract_videos(self, scrape_item: ScrapeItem, embed: dict[str, Any], post_id: str) -> None:
        for media in self._media(embed):
            if playlist := media.get("playlist"):
                self.create_eager_task(self._video(scrape_item, playlist, post_id, media))
                scrape_item.add_children()

    def _extract_images(self, scrape_item: ScrapeItem, embed: dict[str, Any], record_images: Any, did: str) -> None:
        image_index = 0
        for media in self._media(embed):
            if "playlist" in media:
                continue
            record_image = record_images[image_index] if image_index < len(record_images) else {}
            self._extract_image(scrape_item, media, record_image, did)
            image_index += 1

    def _extract_image(
        self, scrape_item: ScrapeItem, media: dict[str, Any], record_image: dict[str, Any], did: str
    ) -> None:
        if fullsize := media.get("fullsize"):
            media_info: MediaInfo = self._prepare_fullsize_image(fullsize, record_image, did)
        else:
            media_info: MediaInfo = self._prepare_blob_image(media, did)

        self.create_eager_task(
            self.handle_file(
                media_info.source_url,
                scrape_item,
                media_info.cid + media_info.ext,
                media_info.ext,
                custom_filename=media_info.cid + media_info.ext,
                debrid_link=media_info.debrid_link,
            )
        )
        scrape_item.add_children()

    def _prepare_fullsize_image(self, fullsize: str, record_image: dict[str, Any], did: str) -> MediaInfo:
        blob = record_image.get("image", {})
        source_url = self.parse_url(fullsize, trim=False)
        cid = blob.get("ref", {}).get("$link") or source_url.name
        _, ext = self.get_filename_and_ext(cid, mime_type=blob.get("mimeType"))
        return MediaInfo(source_url, cid, ext, self.api.blob_url(did, cid))

    def _prepare_blob_image(self, media: dict[str, Any], did: str) -> MediaInfo:
        cid = media["ref"]["$link"] if "ref" in media else media["cid"]
        _, ext = self.get_filename_and_ext(cid, mime_type=media["mimeType"])
        return MediaInfo(self.api.blob_url(did, cid), cid, ext, None)

    async def _video(self, scrape_item: ScrapeItem, playlist: str, post_id: str, media: dict[str, Any]) -> None:
        playlist_url = self.parse_url(playlist, trim=False)
        with self.catch_errors(playlist_url):
            manifest, info = await self.request_m3u8(playlist_url)
            aspect_ratio = media.get("aspectRatio", {})
            resolution = (
                info.resolution
                if info
                else Resolution.parse(aspect_ratio.get("height") if aspect_ratio.get("width") else None)
            )
            filename = self.create_custom_filename(post_id, ext := ".mp4", resolution=resolution)
            await self.handle_file(
                playlist_url,
                scrape_item,
                post_id,
                ext,
                m3u8=manifest,
                custom_filename=filename,
            )

    @staticmethod
    def _media(embed: dict[str, Any]) -> Generator[dict[str, Any]]:
        media = embed.get("media", embed)
        if "playlist" in media:
            yield media
            return
        for image in media.get("images", ()):
            yield image.get("image", image)

        if video := media.get("video"):
            yield video

    def _post_url(self, post: dict[str, Any]) -> AbsoluteHttpURL:
        author = post["author"]["handle"]
        post_id = post["uri"].rpartition("/")[2]
        return self.PRIMARY_URL / "profile" / author / "post" / post_id
