from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any, ClassVar, TypedDict, override

from cyberdrop_dl.cache import disk_cached_method
from cyberdrop_dl.clients.http import HTTPConfig
from cyberdrop_dl.crawlers.crawler import API, Crawler, SupportedPaths
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import dates
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator, Iterable

    from cyberdrop_dl.url_objects import ScrapeItem


class PinterestCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Pin": "/pin/<pin_id>",
        "Board": "/<user>/<slug>",
        "User Boards": "/<user>",
    }
    DOMAIN: ClassVar[str] = "pinterest"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://www.pinterest.com")
    DEFAULT_POST_TITLE_FORMAT: ClassVar[str] = "{id} - {date}"

    def __post_init__(self) -> None:
        self.api: PinterestAPI = PinterestAPI.from_crawler(self)

    @override
    async def __async_post_init__(self) -> None:
        if csrf_token := self.cookies.get("csrftoken"):
            self.api.csrf_token = csrf_token
            return

        with self.catch_errors(self.PRIMARY_URL), self.disable_on_error("Unable to get CSRF token"):
            self.api.csrf_token = await self._get_token()

    @disk_cached_method("csrftoken", ttl=86400 * 30 * 3)
    async def _get_token(self) -> str:
        _ = await self.request_text(self.PRIMARY_URL, impersonate="firefox")
        return self.cookies["csrftoken"]

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["pin", pin_id]:
                return await self.pin(scrape_item, pin_id)
            case [user, slug]:
                return await self.board(scrape_item, user, slug)
            case [user]:
                return await self.user(scrape_item, user)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def board(self, scrape_item: ScrapeItem, user: str, slug: str) -> None:
        board = await self.api.board(user, slug)
        await self._board(scrape_item, board)

    @error_handling_wrapper
    async def _board(self, scrape_item: ScrapeItem, board: dict[str, Any]) -> None:
        scrape_item.setup_as_album(self.create_title(board["owner"]["username"]))
        scrape_item.append_folders(self.create_title(board["name"], board["id"]))
        async for pins in self.api.board_feed(board["id"]):
            for pin in pins:
                url = self.PRIMARY_URL / "pin" / pin["id"]
                self._pin(scrape_item.create_child(url), pin)
                scrape_item.add_children()

    @error_handling_wrapper
    async def user(self, scrape_item: ScrapeItem, user: str) -> None:
        scrape_item.setup_as_profile("")
        async for boards in self.api.boards(user):
            for board in boards:
                url = self.parse_url(board["url"])
                await self._board(scrape_item.create_child(url), board)
                scrape_item.add_children()

    @error_handling_wrapper
    async def pin(self, scrape_item: ScrapeItem, pin_id: str) -> None:
        pin = await self.api.pin(pin_id)
        self._pin(scrape_item, pin)

    @error_handling_wrapper
    def _pin(self, scrape_item: ScrapeItem, pin: dict[str, Any]) -> None:
        scrape_item.setup_as_post(self.create_title(pin["id"]))
        scrape_item.upload_date = date = dates.parse_http(pin["created_at"])
        pin_title = self.create_separate_post_title(pin.get("title"), pin["id"], date)
        scrape_item.append_folders(pin_title)

        for media in _extract_media_from_pin(pin):
            self.create_eager_task(self._media(scrape_item, Media(media["id"], self.parse_url(media["url"]))))
            scrape_item.add_children()

    async def _media(self, scrape_item: ScrapeItem, media: Media) -> None:
        with self.catch_errors(media.url):
            if media.url.suffix == ".m3u8":
                return await self._m3u8_media(scrape_item, media)

            filename, ext = self.get_filename_and_ext(media.url.name)
            await self.handle_file(media.url, scrape_item, filename, ext)

    async def _m3u8_media(self, scrape_item: ScrapeItem, media: Media) -> None:
        m3u8, info = await self.request_m3u8_playlist(media.url)
        filename = self.create_custom_filename(
            media.url.name.removesuffix(".m3u8"),
            ext := ".mp4",
            resolution=info.resolution,
            video_codec=info.codecs.video,
        )
        await self.handle_file(media.url, scrape_item, filename, ext, m3u8=m3u8)


@dataclasses.dataclass(slots=True, order=True)
class Media:
    id: str
    url: AbsoluteHttpURL


class MediaDict(TypedDict):
    id: str
    url: str


@HTTPConfig(
    headers={
        "Accept": "application/json, q=0.01",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
        "X-APP-VERSION": "1df0da9",
        "X-Pinterest-AppState": "background",
        "X-Pinterest-Source-Url": "",
        "X-Pinterest-PWS-Handler": "www/[username]/[slug].js",
        "Alt-Used": "www.pinterest.com",
        "Referer": "https://www.pinterest.com",
    }
)
class PinterestAPI(API):
    "Access to Pinterest REST API for read-only operations (no OAuth required)"

    csrf_token: str

    async def pin(self, pin_id: str) -> dict[str, Any]:
        # "detailed" returns "original" entry for images
        options = {"id": pin_id, "field_set_key": "detailed"}
        data = await self.get_resource("Pin", options)
        return data["resource_response"]["data"]

    async def get_resource(self, resource: str, options: dict[str, Any]) -> dict[str, Any]:
        url = self.PRIMARY_URL / f"resource/{resource}Resource/get/"
        self.client.cookies.update_cookies({"csrftoken": self.csrf_token}, self.PRIMARY_URL)
        return await self.request_json(
            url,
            "POST",
            json={
                "data": {"options": options},
                "source_url": "",
            },
            headers={"X-CSRFToken": self.csrf_token},
        )

    async def pager(self, resource: str, options: dict[str, Any]) -> AsyncGenerator[list[dict[str, Any]]]:
        end_sentinel = "Y2JOb25lO"  # b64encode('cbNone')
        options.setdefault("page_size", 250)
        while True:
            resp = await self.get_resource(resource, options)
            data = resp["resource_response"]["data"]
            if not data:
                break
            yield data

            try:
                bookmarks = resp["resource"]["options"]["bookmarks"]
            except KeyError:
                break

            if not bookmarks or bookmarks[0] == "-end-" or bookmarks[0].startswith(end_sentinel):
                break
            options["bookmarks"] = bookmarks

    async def board(self, user: str, slug: str) -> dict[str, Any]:
        options = {"slug": slug, "username": user, "field_set_key": "detailed"}
        data = await self.get_resource("Board", options)
        return data["resource_response"]["data"]

    async def board_feed(self, board_id: str) -> AsyncGenerator[Generator[dict[str, Any]]]:
        options = {"board_id": board_id}
        async for items in self.pager("BoardFeed", options):
            # Filter "We think you'll love these" ads. They show up as autogenerated stories
            yield (item for item in items if item.get("type") == "pin")

    def boards(self, user: str) -> AsyncGenerator[list[dict[str, Any]]]:
        options = {
            "sort": "last_pinned_to",
            "field_set_key": "profile_grid_item",
            "privacy_filter": "all",
            "username": user,
            "include_archived": True,
        }
        return self.pager("Boards", options)


def _extract_media_from_story(story: dict[str, Any]) -> Generator[MediaDict]:
    for page in story["pages"]:
        block: dict[str, Any]
        for block in page["blocks"]:
            match block["type"]:
                case "story_pin_image_block":
                    yield _parse_image(block)

                case "story_pin_video_block":
                    yield _parse_video(block)

                case "story_pin_music_block":
                    yield _parse_audio(block)

                case "story_pin_product_sticker_block" | "story_pin_static_sticker_block" | "story_pin_paragraph_block":
                    continue

                case block_type:
                    raise ValueError(f"Unknown {block_type = }")


def _extract_media_from_pin(pin: dict[str, Any]) -> Iterable[MediaDict]:
    if story := pin.get("story_pin_data"):
        return _extract_media_from_story(story)

    if video := pin.get("videos"):
        return (_parse_video({"video": video}),)

    return ({"id": pin["image_signature"], "url": pin["images"]["orig"]["url"]},)


def _parse_audio(block: dict[str, Any]) -> MediaDict:
    audio = block["audio"]
    return {"id": audio["id"], "url": audio["audio_url"]}


def _parse_image(block: dict[str, Any]) -> MediaDict:
    return {"url": block["image"]["images"]["originals"]["url"], "id": block["image_signature"]}


def _parse_video(block: dict[str, Any]) -> MediaDict:
    video = block["video"]

    def score(fmt: tuple[str, dict[str, Any]]) -> tuple[int, int]:
        name, stream = fmt
        try:
            hls_score = ("V_HLSV3_MOBILE", "V_HLSV3_WEB", "V_HLSV4").index(name)
        except ValueError:
            hls_score = -1

        return hls_score, stream.get("height") or 0

    _, best_stream = max(video["video_list"].items(), key=score)
    return {"id": video["id"], "url": best_stream["url"]}
