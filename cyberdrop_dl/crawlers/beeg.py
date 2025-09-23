from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.mediaprops import Resolution
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


PRIMARY_URL = AbsoluteHttpURL("https://beeg.com/")
JSON_URL = AbsoluteHttpURL("https://store.externulls.com/facts/file/")
M3U8_URL = AbsoluteHttpURL("https://video.beeg.com/")


class Format(NamedTuple):
    resolution: Resolution
    url: AbsoluteHttpURL


class BeegComCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": (
            "/<video_id>",
            "/video/<video_id>",
        )
    }
    DOMAIN: ClassVar[str] = "beeg.com"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    _RATE_LIMIT = 4, 1

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if video_id := get_video_id(scrape_item.url):
            return await self.video(scrape_item, video_id)
        raise ValueError

    async def video(self, scrape_item: ScrapeItem, video_id: str) -> None:
        canonical_url = PRIMARY_URL / video_id
        if await self.check_complete_from_referer(canonical_url):
            return

        scrape_item.url = canonical_url
        json_resp: dict[str, Any] = await self.request_json(JSON_URL / video_id)
        facts: dict[str, Any] = min(json_resp["fc_facts"], key=lambda x: int(x["id"]))
        file: dict[str, Any] = json_resp["file"]
        title: str = next(data for data in file["data"] if data.get("cd_column") == "sf_name")["cd_value"]
        best_format = get_best_format(file["hls_resources"])
        scrape_item.possible_datetime = self.parse_iso_date(facts.get("fc_created", ""))
        m3u8 = await self.get_m3u8_from_index_url(best_format.url)
        filename, ext = self.get_filename_and_ext(best_format.url.name)
        custom_filename = self.create_custom_filename(title, ext, file_id=video_id, resolution=best_format.resolution)
        await self.handle_file(canonical_url, scrape_item, filename, ext, custom_filename=custom_filename, m3u8=m3u8)


def get_video_id(url: AbsoluteHttpURL) -> str | None:
    # https://beeg.com/-0983946056129650"
    # https://beeg.com/1277207756"

    index = 2 if "video" in url.parts else 1
    try:
        return str(int(url.parts[index].removeprefix("-")))
    except Exception:
        return


def get_best_format(sources: dict[str, str]) -> Format:
    def parse_sources():
        for name, uri in sources.items():
            try:
                yield Resolution.parse(name.removeprefix("fl_cdn_")), uri
            except ValueError:
                continue

    resolution, uri = max(parse_sources())
    return Format(resolution, M3U8_URL / uri)
