from __future__ import annotations

import base64
import codecs
import dataclasses
import json
import re
from collections import Counter
from typing import TYPE_CHECKING, Any, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedDomains, SupportedPaths, auto_task_id
from cyberdrop_dl.data_structures import AbsoluteHttpURL
from cyberdrop_dl.data_structures.mediaprops import Resolution
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import m3u8, open_graph
from cyberdrop_dl.utils.utilities import error_handling_wrapper, parse_url

if TYPE_CHECKING:
    from collections.abc import Generator

    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


_find_js_redirect = re.compile(
    r'(?:window\.location\.href\s*=\s*["\'])([^"\']+)["\']|(?:window\.location\s*=\s*["\'])([^"\']+)["\']',
    re.IGNORECASE,
).search

_ISO639_MAP = {
    "arabic": "ara",
    "english": "eng",
    "french": "fre",
    "german": "ger",
    "italian": "ita",
    "portuguese": "por",
    "russian": "rus",
    "spanish": "spa",
    "chinese": "chi",
    "korean": "kor",
    "thai": "tha",
    "indonesian": "ind",
}


_HEADERS: dict[str, str] = {
    "User-Agent":  # Force firefox on linux to get high res mp4 formats as "fallbacks"
    "Mozilla/5.0 (X11; Linux x86_64; rv:143.0) Gecko/20100101 Firefox/143.0"
}


@dataclasses.dataclass(frozen=True, slots=True)
class VoeSubtitle:
    label: str
    lang_code: str
    suffix: str
    url: AbsoluteHttpURL


@dataclasses.dataclass(slots=True)
class VoeVideo:
    id: str
    title: str
    url: AbsoluteHttpURL
    resolution: Resolution | None
    hls_url: AbsoluteHttpURL | None
    subtitles: tuple[VoeSubtitle, ...]


class VoeSxCrawler(Crawler):
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = (
        "alejandrocenturyoil.com",
        "diananatureforeign.com",
        "heatherwholeinvolve.com",
        "jennifercertaindevelopment.com",
        "jilliandescribecompany.com",
        "jonathansociallike.com",
        "mariatheserepublican.com",
        "maxfinishseveral.com",
        "nathanfromsubject.com",
        "richardsignfish.com",
        "robertordercharacter.com",
        "sarahnewspaperbeat.com",
        "voe.sx",
    )
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Embed": "/e/video_id",
    }

    DOMAIN: ClassVar[str] = "voe.sx"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://voe.sx")

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["e", video_id]:
                return await self.embed(scrape_item, video_id)
            case [video_id, "download"]:
                return await self.embed(scrape_item, video_id)
            case [video_id]:
                return await self.embed(scrape_item, video_id)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def embed(self, scrape_item: ScrapeItem, video_id: str) -> None:
        origin = scrape_item.url.origin()
        embed_url = origin / "e" / video_id
        if await self.check_complete(embed_url, embed_url):
            return

        async with self.request(embed_url, headers=_HEADERS) as resp:
            text = await resp.text()
            if match := _find_js_redirect(text):
                scrape_item.url = self.parse_url(match.group(1), origin)
                self.create_task(self.redirect(scrape_item))
                return

        soup = await resp.soup()
        video = extract_voe_video(soup, origin)
        if not video.id:
            video.id = video_id
        scrape_item.url = embed_url
        await self._video(scrape_item, video)

    async def _video(self: Crawler, scrape_item: ScrapeItem, video: VoeVideo) -> None:
        m3u8 = None
        if video.resolution == (0, 0) and video.hls_url:
            msg = f"Unable to extract high resolution MP4 formats for {scrape_item.url}. Falling back to HLS"
            self.log(msg, 30)

            m3u8 = await self.get_m3u8_from_index_url(video.hls_url, headers=_HEADERS)

        VoeSxCrawler._handle_video(self, scrape_item, video, m3u8)

    def _handle_video(
        self: Crawler, scrape_item: ScrapeItem, video: VoeVideo, m3u8: m3u8.RenditionGroup | None
    ) -> None:
        custom_filename = self.create_custom_filename(
            video.title.removesuffix(video.url.suffix),
            video.url.suffix,
            file_id=video.id,
            resolution=video.resolution,
        )
        self.create_task(
            self.handle_file(
                scrape_item.url,
                scrape_item,
                video.url.name,
                video.url.suffix,
                custom_filename=custom_filename,
                debrid_link=video.url,
                m3u8=m3u8,
            )
        )
        video_stem = custom_filename.removesuffix(video.url.suffix)
        for sub in video.subtitles:
            sub_name, ext = self.get_filename_and_ext(f"{video_stem}.{sub.suffix}")
            self.create_task(
                self.handle_file(
                    sub.url,
                    scrape_item,
                    sub.label,
                    ext,
                    custom_filename=sub_name,
                )
            )

    redirect = auto_task_id(fetch)


def extract_voe_video(soup: BeautifulSoup, origin: AbsoluteHttpURL) -> VoeVideo:
    for js_script in soup.select("script[type='application/json']"):
        script_text = js_script.decode_contents()
        video_info: dict[str, Any] | None = _load_json(script_text)
        if video_info:
            break
    else:
        raise ScrapeError(422)

    res, src = max(_extract_mp4_urls(video_info, origin))
    return VoeVideo(
        id=video_info.get("file_code", ""),
        title=video_info.get("title") or open_graph.title(soup),
        resolution=res,
        url=src,
        subtitles=tuple(_parse_subs(video_info, origin)),
        hls_url=parse_url(url, origin) if (url := video_info.get("source")) else None,
    )


def _load_json(json_content: str) -> Any:
    if not json_content:
        return

    try:
        data = json.loads(json_content)
        if isinstance(data, list) and len(data) == 1:
            return _decrypt_json(data[0])
        return data
    except json.JSONDecodeError:
        return


def _decrypt_json(encrypted_json: str) -> Any:
    def b64_decode(b64_string: str) -> str | None:
        if pad := len(b64_string) % 4:
            b64_string += "=" * (4 - pad)
        try:
            return base64.b64decode(b64_string).decode("utf-8", errors="replace")
        except ValueError:
            return

    def shift(string: str, n: int) -> str:
        return "".join(chr(ord(char) - n) for char in string)

    step_1 = codecs.decode(encrypted_json, "rot13")
    step_2 = b64_decode(step_1)
    if not step_2:
        return
    step_3 = shift(step_2, n=3)
    step_4 = b64_decode(step_3[::-1])
    if not step_4:
        return
    try:
        return json.loads(step_4)
    except json.JSONDecodeError:
        return


def _extract_mp4_urls(
    video_info: dict[str, Any], origin: AbsoluteHttpURL
) -> Generator[tuple[Resolution, AbsoluteHttpURL]]:
    for fallback in video_info.get("fallback", []):
        if fallback["type"] == "mp4":
            res = Resolution.parse(fallback["label"])
            yield res, parse_url(fallback["file"], origin)

    if url := video_info.get("direct_access_url"):
        yield Resolution.unknown(), parse_url(url, origin)


def _parse_subs(video_info: dict[str, Any], origin: AbsoluteHttpURL) -> Generator[VoeSubtitle]:
    counter = Counter()
    for track in video_info.get("captions", []):
        if track["kind"] != "captions":
            continue

        url = parse_url(track["file"], origin)
        label: str = track["label"]
        lang_code = _parse_lang_code(url.name.removesuffix(url.suffix), label)
        counter[lang_code] += 1
        if (count := counter[lang_code]) > 1:
            suffix = f"{lang_code}.{count}{url.suffix}"
        else:
            suffix = f"{lang_code}{url.suffix}"

        yield VoeSubtitle(label, lang_code, suffix, url)


def _parse_lang_code(stem: str, label: str) -> str:
    code = stem.rpartition("_")[-1]
    if len(code) in (2, 3):
        return code

    label = label.casefold()
    if code := _ISO639_MAP.get(label):
        return code

    for lang, code in _ISO639_MAP.items():
        if label.startswith(lang):
            return code

    return "unk"
