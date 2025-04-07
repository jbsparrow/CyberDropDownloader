from __future__ import annotations

import contextlib
import json
import re
import urllib
from typing import TYPE_CHECKING, NamedTuple

from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


UNAUTHORIZED_SELECTOR = "div.video-holder:contains('This video is a private video')"
JS_SELECTOR = "div.video-holder > script:contains('var flashvars')"
USER_NAME_SELECTOR = "div.headline > h2"
PUBLIC_VIDEOS_SELECTOR = "div#list_videos_public_videos_items"
PRIVATE_VIDEOS_SELECTOR = "div#list_videos_private_videos_items"
FAVOURITE_VIDEOS_SELECTOR = "div#list_videos_favourite_videos_items"
NEXT_PAGE_SELECTOR = "li.pagination-next > a"
VIDEOS_SELECTOR = "a.tumbpu"


class Format(NamedTuple):
    resolution: int | None
    url: URL


class ThisVidCrawler(Crawler):
    primary_base_domain = URL("https://thisvid.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "thisvid", "ThisVid")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "members" in scrape_item.url.parts:
            return await self.profile(scrape_item)
        elif "videos" in scrape_item.url.parts:
            return await self.video(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)
        user_name: str = soup.select_one(USER_NAME_SELECTOR).get_text().split("'s Profile")[0].strip()
        title = f"{user_name} [user]"
        title = self.create_title(title)
        scrape_item.setup_as_profile(title)

        if soup.select(PUBLIC_VIDEOS_SELECTOR):
            await self.iter_videos(scrape_item, "public_videos")
        if soup.select(FAVOURITE_VIDEOS_SELECTOR):
            await self.iter_videos(scrape_item, "favourite_videos")
        if soup.select(PRIVATE_VIDEOS_SELECTOR):
            await self.iter_videos(scrape_item, "private_videos")

    async def iter_videos(self, scrape_item: ScrapeItem, video_category: str = "") -> None:
        category_url: URL = scrape_item.url / video_category
        async for soup in self.web_pager(category_url):
            if videos := soup.select(VIDEOS_SELECTOR):
                for video in videos:
                    link: URL = URL(video.get("href"))
                    new_scrape_item = scrape_item.create_child(link, new_title_part=video_category)
                    self.manager.task_group.create_task(self.run(new_scrape_item))
                    scrape_item.add_children()

    async def web_pager(self, category_url: URL) -> AsyncGenerator[BeautifulSoup]:
        """Generator of website pages."""
        page_url: URL = category_url
        while True:
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup(self.domain, page_url)
            next_page = soup.select_one(NEXT_PAGE_SELECTOR)
            yield soup
            page_url_str: str | None = next_page.get("href") if next_page else None  # type: ignore
            if not page_url_str:
                break
            page_url = self.parse_url(page_url_str, self.primary_base_domain)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)
        if soup.select_one(UNAUTHORIZED_SELECTOR):
            raise ScrapeError(401, origin=scrape_item)
        script = soup.select_one(JS_SELECTOR)
        if script is None:
            raise ScrapeError(404, origin=scrape_item)
        flashvars: str = script.text[script.text.find("var flashvars") + 16 : script.text.find("kt_player")]
        flashvars = flashvars[: flashvars.rfind(";")]
        best_fmt = get_best_resolution(str(scrape_item.url), js_to_json(flashvars))
        title: str = soup.select_one("title").text.split("- ThisVid.com")[0].strip()
        filename, ext = get_filename_and_ext(best_fmt["url"])
        video_url: URL = URL(best_fmt["url"])
        custom_filename, _ = get_filename_and_ext(f"{title} [{video_url.parts[-3]}] [{best_fmt['format_id']}].{ext}")
        await self.handle_file(video_url, scrape_item, filename, ext, custom_filename=custom_filename)


"""~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""


# Code borrowed from yt-dlp
# https://github.com/yt-dlp/yt-dlp/blob/e1847535e28788414a25546a45bebcada2f34558/yt_dlp/extractor/generic.py
def kvs_get_license_token(license_code):
    license_code = license_code.replace("$", "")
    license_values = [int(char) for char in license_code]

    modlicense = license_code.replace("0", "1")
    center = len(modlicense) // 2
    fronthalf = int(modlicense[: center + 1])
    backhalf = int(modlicense[center:])
    modlicense = str(4 * abs(fronthalf - backhalf))[: center + 1]

    return [
        (license_values[index + offset] + current) % 10
        for index, current in enumerate(map(int, modlicense))
        for offset in range(4)
    ]


def kvs_get_real_url(video_url, license_code):
    if not video_url.startswith("function/0/"):
        return video_url  # not obfuscated

    parsed = urllib.parse.urlparse(video_url[len("function/0/") :])
    license_token = kvs_get_license_token(license_code)
    urlparts = parsed.path.split("/")

    HASH_LENGTH = 32
    hash_ = urlparts[3][:HASH_LENGTH]
    indices = list(range(HASH_LENGTH))

    # Swap indices of hash according to the destination calculated from the license token
    accum = 0
    for src in reversed(range(HASH_LENGTH)):
        accum += license_token[src]
        dest = (src + accum) % HASH_LENGTH
        indices[src], indices[dest] = indices[dest], indices[src]

    urlparts[3] = "".join(hash_[index] for index in indices) + urlparts[3][HASH_LENGTH:]
    return urllib.parse.urlunparse(parsed._replace(path="/".join(urlparts)))


def parse_resolution(s, *, lenient=False):
    if s is None:
        return {}

    if lenient:
        mobj = re.search(r"(?P<w>\d+)\s*[xX×,]\s*(?P<h>\d+)", s)  # noqa: RUF001
    else:
        mobj = re.search(r"(?<![a-zA-Z0-9])(?P<w>\d+)\s*[xX×,]\s*(?P<h>\d+)(?![a-zA-Z0-9])", s)  # noqa: RUF001
    if mobj:
        return {
            "width": int(mobj.group("w")),
            "height": int(mobj.group("h")),
        }

    mobj = re.search(r"(?<![a-zA-Z0-9])(\d+)[pPiI](?![a-zA-Z0-9])", s)
    if mobj:
        return {"height": int(mobj.group(1))}

    mobj = re.search(r"\b([48])[kK]\b", s)
    if mobj:
        return {"height": int(mobj.group(1)) * 540}

    return {}


def get_best_resolution(url, flashvars):
    url_keys = list(filter(re.compile(r"^video_(?:url|alt_url\d*)$").match, flashvars.keys()))
    formats = []
    for key in url_keys:
        if "/get_file/" not in flashvars[key]:
            continue
        format_id = flashvars.get(f"{key}_text", key)
        formats.append(
            {
                "url": urllib.parse.urljoin(url, kvs_get_real_url(flashvars[key], flashvars["license_code"])),
                "format_id": format_id,
                "ext": "mp4",
                **(parse_resolution(format_id) or parse_resolution(flashvars[key])),
            }
        )
        if not formats[-1].get("height"):
            formats[-1]["quality"] = 1
    higher_res: int = 0
    best_fmt: dict = None
    for fmt in formats:
        if fmt["format_id"] == "HQ":
            return fmt
        elif fmt["format_id"] == "video_url":
            fmt["format_id"] = "Unknown"
            return fmt
        else:
            res = int(fmt["format_id"].strip("p"))
            if res > higher_res:
                higher_res = res
                best_fmt = fmt

    return best_fmt


def js_to_json(code, vars={}, *, strict=False):  # noqa: B006
    # vars is a dict of var, val pairs to substitute
    STRING_QUOTES = "'\"`"
    STRING_RE = "|".join(rf"{q}(?:\\.|[^\\{q}])*{q}" for q in STRING_QUOTES)
    COMMENT_RE = r"/\*(?:(?!\*/).)*?\*/|//[^\n]*\n"
    SKIP_RE = rf"\s*(?:{COMMENT_RE})?\s*"
    INTEGER_TABLE = (
        (rf"(?s)^(0[xX][0-9a-fA-F]+){SKIP_RE}:?$", 16),
        (rf"(?s)^(0+[0-7]+){SKIP_RE}:?$", 8),
    )

    def process_escape(match):
        JSON_PASSTHROUGH_ESCAPES = R'"\bfnrtu'
        escape = match.group(1) or match.group(2)

        return (
            Rf"\{escape}"
            if escape in JSON_PASSTHROUGH_ESCAPES
            else R"\u00"
            if escape == "x"
            else ""
            if escape == "\n"
            else escape
        )

    def template_substitute(match):
        evaluated = js_to_json(match.group(1), vars, strict=strict)
        if evaluated[0] == '"':
            with contextlib.suppress(json.JSONDecodeError):
                return json.loads(evaluated)
        return evaluated

    def fix_kv(m):
        v = m.group(0)
        if v in ("true", "false", "null"):
            return v
        elif v in ("undefined", "void 0"):
            return "null"
        elif v.startswith(("/*", "//", "!")) or v == ",":
            return ""

        if v[0] in STRING_QUOTES:
            v = re.sub(r"(?s)\${([^}]+)}", template_substitute, v[1:-1]) if v[0] == "`" else v[1:-1]
            escaped = re.sub(r'(?s)(")|\\(.)', process_escape, v)
            return f'"{escaped}"'

        for regex, base in INTEGER_TABLE:
            im = re.match(regex, v)
            if im:
                i = int(im.group(1), base)
                return f'"{i}":' if v.endswith(":") else str(i)

        if v in vars:
            try:
                if not strict:
                    json.loads(vars[v])
            except json.JSONDecodeError:
                return json.dumps(vars[v])
            else:
                return vars[v]

        if not strict:
            return f'"{v}"'

        raise ValueError(f"Unknown value: {v}")

    def create_map(mobj):
        return json.dumps(dict(json.loads(js_to_json(mobj.group(1) or "[]", vars=vars))))

    code = re.sub(r"(?:new\s+)?Array\((.*?)\)", r"[\g<1>]", code)
    code = re.sub(r"new Map\((\[.*?\])?\)", create_map, code)
    if not strict:
        code = re.sub(rf"new Date\(({STRING_RE})\)", r"\g<1>", code)
        code = re.sub(r"new \w+\((.*?)\)", lambda m: json.dumps(m.group(0)), code)
        code = re.sub(r"parseInt\([^\d]+(\d+)[^\d]+\)", r"\1", code)
        code = re.sub(r'\(function\([^)]*\)\s*\{[^}]*\}\s*\)\s*\(\s*(["\'][^)]*["\'])\s*\)', r"\1", code)

    return json.loads(
        re.sub(
            rf"""(?sx)
        {STRING_RE}|
        {COMMENT_RE}|,(?={SKIP_RE}[\]}}])|
        void\s0|(?:(?<![0-9])[eE]|[a-df-zA-DF-Z_$])[.a-zA-Z_$0-9]*|
        \b(?:0[xX][0-9a-fA-F]+|0+[0-7]+)(?:{SKIP_RE}:)?|
        [0-9]+(?={SKIP_RE}:)|
        !+
        """,
            fix_kv,
            code,
        )
    )
