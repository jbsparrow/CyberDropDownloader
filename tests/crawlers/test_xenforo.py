from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest
from bs4 import BeautifulSoup

from cyberdrop_dl.crawlers import _forum
from cyberdrop_dl.crawlers import xenforo as crawlers
from cyberdrop_dl.crawlers.xenforo import xenforo
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL, ScrapeItem
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.managers.manager import Manager

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path


def _item(url: str) -> ScrapeItem:
    return ScrapeItem(url=AbsoluteHttpURL(url))


class MockProgress:
    scraping_progress = None


manager = Manager()
scrape_item = _item("https://xenforo.com/community")
manager.progress_manager = MockProgress()  # type: ignore
crawler_instances = {crawler: crawler(manager) for crawler in crawlers.XF_CRAWLERS}
TEST_CRAWLER = crawler_instances[crawlers.CelebForumCrawler]


def _html(string: str) -> str:
    return f"""
    <html>
    <body>
    {string}
    </body>
    </html>
    """


def _post(
    message_body: str = "",
    message_attachments: str = "",
    id: int = 12345,
    crawler: xenforo.XenforoCrawler | None = None,
) -> _forum.ForumPost:
    crawler = crawler or TEST_CRAWLER
    html = _html(POST_TEMPLATE.format(id=id, message_body=message_body, message_attachments=message_attachments))
    article = BeautifulSoup(html, "html.parser").select("article")[0]
    return _forum.ForumPost.new(article, crawler.SELECTORS.posts)


def _item_call(value: Any) -> mock._Call:
    return mock.call(scrape_item, value)


def _any_item_call(value: Any) -> mock._Call:
    return mock.call(mock.ANY, value)


def _amock(func: str = "process_child", crawler: xenforo.XenforoCrawler | None = None) -> mock._patch[mock.AsyncMock]:
    crawler = crawler or TEST_CRAWLER
    return mock.patch.object(crawler, func, new_callable=mock.AsyncMock)


@pytest.fixture(name="manager")
async def post_startup_manager(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[Manager]:
    appdata = str(tmp_path)
    downloads = str(tmp_path / "Downloads")
    monkeypatch.chdir(tmp_path)
    manager = Manager(("--appdata-folder", appdata, "-d", downloads))
    manager.startup()
    manager.path_manager.startup()
    manager.log_manager.startup()
    await manager.async_startup()
    yield manager
    await manager.async_db_close()
    await manager.close()


@pytest.mark.parametrize(
    ("url", "thread_name_and_id", "result", "canonical_url"),
    [
        [
            "https://simpcity.su/threads/general-support.208041/page-260#post-23934165",
            "general-support.208041",
            (
                208041,
                "general-support",
                260,
                23934165,
            ),
            "https://simpcity.su/threads/general-support.208041",
        ],
        [
            "https://celebforum.to/threads/infos-regelaenderungen.18821/page-3",
            "infos-regelaenderungen.18821",
            (
                18821,
                "infos-regelaenderungen",
                3,
                None,
            ),
            "https://celebforum.to/threads/infos-regelaenderungen.18821",
        ],
        [
            "https://www.bellazon.com/main/topic/27120-the-official-victorias-secret-thread",
            "27120-the-official-victorias-secret-thread",
            (
                27120,
                "the-official-victorias-secret-thread",
                1,
                None,
            ),
            "https://www.bellazon.com/main/topic/27120-the-official-victorias-secret-thread",
        ],
        [
            "https://forums.socialmediagirls.com/threads/forum-rules.14/post-34",
            "forum-rules.14",
            (
                14,
                "forum-rules",
                1,
                34,
            ),
            "https://forums.socialmediagirls.com/threads/forum-rules.14",
        ],
        [
            "https://forums.socialmediagirls.com/threads/should-we-ban-gofile-76-5-say-no.436901/post-3942103",
            "should-we-ban-gofile-76-5-say-no.436901",
            (
                436901,
                "should-we-ban-gofile-76-5-say-no",
                1,
                3942103,
            ),
            "https://forums.socialmediagirls.com/threads/should-we-ban-gofile-76-5-say-no.436901",
        ],
        [
            "https://forums.socialmediagirls.com/threads/en-fr-tools-to-download-upload-content-websites-softwares-extensions.13930/page-11/#post-2070848",
            "en-fr-tools-to-download-upload-content-websites-softwares-extensions.13930",
            (
                13930,
                "en-fr-tools-to-download-upload-content-websites-softwares-extensions",
                11,
                2070848,
            ),
            "https://forums.socialmediagirls.com/threads/en-fr-tools-to-download-upload-content-websites-softwares-extensions.13930",
        ],
        [
            "https://f95zone.to/threads/mod-uploading-rules-12-02-2018.9236/post-2726083",
            "mod-uploading-rules-12-02-2018.9236",
            (
                9236,
                "mod-uploading-rules-12-02-2018",
                1,
                2726083,
            ),
            "https://f95zone.to/threads/mod-uploading-rules-12-02-2018.9236",
        ],
        [
            "https://650f.bike/threads/central-stand-honda-cb650r-constands-power-evo.3093/page-2",
            "central-stand-honda-cb650r-constands-power-evo.3093",
            (
                3093,
                "central-stand-honda-cb650r-constands-power-evo",
                2,
                None,
            ),
            "https://650f.bike/threads/central-stand-honda-cb650r-constands-power-evo.3093",
        ],
        [
            "https://arstechnica.com/civis/threads/the-new-perpetual-photo-accessory-thread.1274775/page-3#post-29155063",
            "the-new-perpetual-photo-accessory-thread.1274775",
            (
                1274775,
                "the-new-perpetual-photo-accessory-thread",
                3,
                29155063,
            ),
            "https://arstechnica.com/civis/threads/the-new-perpetual-photo-accessory-thread.1274775",
        ],
        [
            "https://www.laneros.com/temas/iphone-16-16e-16-plus-16-pro-16-promax.256047/page-64#post-7512404",
            "iphone-16-16e-16-plus-16-pro-16-promax.256047",
            (
                256047,
                "iphone-16-16e-16-plus-16-pro-16-promax",
                64,
                7512404,
            ),
            "https://www.laneros.com/temas/iphone-16-16e-16-plus-16-pro-16-promax.256047",
        ],
    ],
)
def test_parse_thread(url: str, thread_name_and_id: str, result: tuple[int, str, int, int], canonical_url: str) -> None:
    url_, canonical_url_ = AbsoluteHttpURL(url), AbsoluteHttpURL(canonical_url)
    result_ = _forum.Thread(*result, canonical_url_)
    parsed = TEST_CRAWLER.parse_thread(url_, thread_name_and_id)
    assert result_ == parsed


@pytest.mark.parametrize(
    "link, out",
    [
        (
            "https://media.imagepond.net/media/IMG_2153a940fb5680979a52.jpg",
            "https://media.imagepond.net/media/IMG_2153a940fb5680979a52.jpg",
        ),
        (
            "https://media.imagepond.net/media/IMG_2153a940fb5680979a52.th.jpg",
            "https://media.imagepond.net/media/IMG_2153a940fb5680979a52.jpg",
        ),
        (
            "https://media.imagepond.net/media/IMG_2153a940fb5680979a52.md.jpg",
            "https://media.imagepond.net/media/IMG_2153a940fb5680979a52.jpg",
        ),
        (
            "https://simp6.jpg5.su/images3/20250612_051526cd1f36d75c763fe4.md.jpg",
            "https://simp6.jpg5.su/images3/20250612_051526cd1f36d75c763fe4.jpg",
        ),
        (
            "https://jpg5.su/img/aDNRwDH",
            "https://jpg5.su/img/aDNRwDH",
        ),
        (
            "https://saint2.cr/embed/M8XwlvJUlW-",
            "https://saint2.cr/embed/M8XwlvJUlW-",
        ),
        (
            "https://saint2.cr/ifr/M8XwlvJUlW-",
            "https://saint2.cr/watch/M8XwlvJUlW-",
        ),
    ],
)
def test_clean_link_url(link: str, out: str) -> None:
    assert _forum.clean_link_str(link) == out


def test_parse_login_form_success() -> None:
    html = _html("""
    <form id="loginForm">
        <input type="text" name="username" value="testuser">
        <input type="password" name="password" value="testpass">
        <input type="hidden" name="csrf_token" value="some_token_123">
        <input type="submit" value="Login">
        <input type="text" id="noName" value="shouldBeIgnored">
        <input type="text" name="noValue">
    </form>
    <form id="anotherForm">
        <input type="text" name="anotherField" value="anotherValue">
    </form>
    """)
    expected_data = {
        "username": "testuser",
        "password": "testpass",
        "csrf_token": "some_token_123",
    }
    parsed_data = xenforo.parse_login_form(html)
    assert parsed_data == expected_data


def test_parse_login_form_no_form_should_fail() -> None:
    with pytest.raises(ScrapeError):
        xenforo.parse_login_form("")


def test_parse_login_form_inputs_without_name_or_value_should_be_ignored() -> None:
    html = _html("""
    <form>
        <input type="text" value="somevalue">
        <input type="text" name="someName">
        <input type="text" name="validField" value="validValue">
    </form>
    """)
    expected_data = {"validField": "validValue"}
    parsed_data = xenforo.parse_login_form(html)
    assert parsed_data == expected_data


def test_parse_login_form_no_input_form_should_fail() -> None:
    html = _html("""
    <form>
        <div>Some content</div>
        <p>More content</p>
    </form>
    """)
    with pytest.raises(ScrapeError):
        xenforo.parse_login_form(html)


@pytest.mark.parametrize(
    "input_string, expected_output",
    [
        (
            r"some_text_before \/\/simpcity.su/path/to/resource.mp4 some_text_after",
            "https://simpcity.su/path/to/resource.mp4",
        ),
        (
            r"prefix \/\/celebforum.to/search?q=test suffix",
            "https://celebforum.to/search?q=test",
        ),
        (
            r"only_url \/\/sub.domain.co.uk/file.pdf",
            "https://sub.domain.co.uk/file.pdf",
        ),
        (
            r"http://simpcity.su/some_page",
            "http://simpcity.su/some_page",
        ),
        (
            r"text with no slashes http://xenforo.com",
            "http://xenforo.com",
        ),
        (
            r"text with no slashes https://xenforo.com/path",
            "https://xenforo.com/path",
        ),
        # Test cases where no URL is found
        (
            "just some plain text",
            "just some plain text",
        ),
        ("", ""),
        (
            "no\\url\\here",
            "nourlhere",
        ),  # check if backslashes are removed
        (
            "//invalid.c",
            "//invalid.c",
        ),  # too short domain suffix
        (
            "ftp://simpcity.su/file",
            "ftp://simpcity.su/file",
        ),  # unsupported protocol
        (
            "www.simpcity.su",
            "www.simpcity.su",
        ),  # missing http/https
        (
            "simpcity.su",
            "simpcity.su",
        ),  # missing http/https
        (
            "text with https: //simpcity.su/ (space after colon)",
            "text with https: //simpcity.su/ (space after colon)",
        ),
        (
            "text with unicode \u00a9 characters",
            "text with unicode \u00a9 characters",
        ),
    ],
)
def test_extract_embed_url(input_string: str, expected_output: str) -> None:
    assert _forum.extract_embed_url(input_string) == expected_output


@pytest.mark.xfail  # regex can not handle URLs with commands in it (kvs)
@pytest.mark.parametrize(
    ("input_string", "expected_output"),
    [
        (
            r"start \/\/media.jp5.net/videos/2023/clip_id-123.mp4?autoplay=true&loop=false#t=10s end",
            "https://media.jp5.net/videos/2023/clip_id-123.mp4?autoplay=true&loop=false#t=10s",
        ),
        (
            r"start \/\/jupiter4.thisvid.com/key=SEtXHaueMU2PByWg4GNMnw,end=1750179436/speed=1.4/buffer=5.0/12702000/12702535/12702535.mp4 other",
            "https://jupiter4.thisvid.com/key=SEtXHaueMU2PByWg4GNMnw,end=1750179436/speed=1.4/buffer=5.0/12702000/12702535/12702535.mp4",
        ),
    ],
)
def test_extract_embed_url_complex_path(input_string: str, expected_output: str) -> None:
    assert _forum.extract_embed_url(input_string) == expected_output


def test_extract_embed_url_should_extract_only_one_url() -> None:
    input_str = r"first_url \/\/first.com/path second_url \/\/www.second.net/another"
    expected_output = "https://first.com/path"
    assert _forum.extract_embed_url(input_str) == expected_output


def test_extract_embed_url_with_escaped_backslashes_and_double_slashes() -> None:
    input_str = r"some_path\\to\\file\/\/imagepond.net\/clip.mov"
    expected_output = "https://imagepond.net/clip.mov"
    assert _forum.extract_embed_url(input_str) == expected_output


def test_extract_embed_url_absolute_url_no_scheme() -> None:
    input_str = r"\/\/jpg5.su"
    expected_output = r"https://jpg5.su"
    assert _forum.extract_embed_url(input_str) == expected_output


def test_extract_embed_url_should_not_modify_absolute_urls() -> None:
    input_str = r"https://celebforum.to/maps"
    expected_output = "https://celebforum.to/maps"
    assert _forum.extract_embed_url(input_str) == expected_output


def test_extract_embed_url_string_ends_with_url() -> None:
    input_str = r"some text https://www.reddit.com/"
    expected_output = "https://reddit.com/"
    assert _forum.extract_embed_url(input_str) == expected_output


def test_lazy_load_embeds() -> None:
    post = _post("""
    <div class="generic2wide-iframe-div" onclick="loadMedia(this, '//redgifs.com/ifr/downrightcluelesswirm');">
        <span data-s9e-mediaembed="redgifs">
            <span class="iframe-wrapper-redgifs" style="">
                <span class="iframe-wrapper-redgifs-info">Click here to load redgifs media</span>
            </span>
        </span>
    </div>""")
    result = list(TEST_CRAWLER._lazy_load_embeds(post))
    assert len(result) == 1
    assert "//redgifs.com/ifr/downrightcluelesswirm" == result[0]


@pytest.mark.parametrize(
    ("cls", "post_content", "expected_result"),
    [
        (
            crawlers.AllPornComixCrawler,
            """
                <a href="https://jpg5.su/img/aqDYT6c" target="_blank" class="link link--external" rel="nofollow ugc noopener">
                    <img
                        src="https://simp6.jpg5.su/images3/issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg"
                        data-url="https://simp6.jpg5.su/images3/issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg"
                        class="bbImage"
                        loading="lazy"
                        alt="issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg"
                        title="issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg"
                        style=""
                        width=""
                        height=""
                    />
                </a>""",
            ["https://simp6.jpg5.su/images3/issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg"],
        ),
        (
            crawlers.SimpCityCrawler,
            """
                <a href="https://jpg5.su/img/aqDYT6c" target="_blank" class="link link--external" rel="nofollow ugc noopener">
                    <img
                        src="https://simp6.jpg5.su/images3/issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg"
                        data-url="https://simp6.jpg5.su/images3/issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg"
                        class="bbImage"
                        loading="lazy"
                        alt="issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg"
                        title="issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg"
                        style=""
                        width=""
                        height=""
                    />
                </a>
                <a href="https://jpg5.su/img/aqDYZAt" target="_blank" class="link link--external" rel="nofollow ugc noopener">
                    <img
                        src="https://simp6.jpg5.su/images3/issfanfan-20250129-0001ef763780833ed714.md.jpg"
                        data-url="https://simp6.jpg5.su/images3/issfanfan-20250129-0001ef763780833ed714.md.jpg"
                        class="bbImage"
                        loading="lazy"
                        alt="issfanfan-20250129-0001ef763780833ed714.md.jpg"
                        title="issfanfan-20250129-0001ef763780833ed714.md.jpg"
                        style=""
                        width=""
                        height=""
                    />
                </a>
            </div>""",
            [
                "https://simp6.jpg5.su/images3/issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg",
                "https://simp6.jpg5.su/images3/issfanfan-20250129-0001ef763780833ed714.md.jpg",
            ],
        ),
        (
            crawlers.SimpCityCrawler,
            """
                <a href="https://jpg5.su/img/aqDYT6c" target="_blank" class="link link--external" rel="nofollow ugc noopener">
                    <img
                        src="https://simp6.jpg5.su/images3/issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg"
                        data-url="https://simp6.jpg5.su/images3/issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg"
                        class="bbImage"
                        loading="lazy"
                        alt="issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg"
                        title="issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg"
                        style=""
                        width=""
                        height=""
                    />
                </a>
                <a href="https://jpg5.su/img/aqDYZAt" target="_blank" class="link link--external" rel="nofollow ugc noopener">
                    <img
                        src="https://simp6.jpg5.su/images3/issfanfan-20250129-0001ef763780833ed714.md.jpg"
                        data-url="https://simp6.jpg5.su/images3/issfanfan-20250129-0001ef763780833ed714.md.jpg"
                        class="bbImage"
                        loading="lazy"
                        alt="issfanfan-20250129-0001ef763780833ed714.md.jpg"
                        title="issfanfan-20250129-0001ef763780833ed714.md.jpg"
                        style=""
                        width=""
                        height=""
                    />
                </a>
            </div>""",
            [
                "https://simp6.jpg5.su/images3/issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg",
                "https://simp6.jpg5.su/images3/issfanfan-20250129-0001ef763780833ed714.md.jpg",
            ],
        ),
        (
            crawlers.SimpCityCrawler,
            """
                <a href="https://jpg5.su/img/aqDYT6c" target="_blank" class="link link--external" rel="nofollow ugc noopener">
                    <img
                        src="https://simp6.jpg5.su/images3/issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg"
                        data-url="https://simp6.jpg5.su/images3/issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg"
                        class="bbImage"
                        loading="lazy"
                        alt="issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg"
                        title="issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg"
                        style=""
                        width=""
                        height=""
                    />
                </a>
                <a href="https://jpg5.su/img/aqDYZAt" target="_blank" class="link link--external" rel="nofollow ugc noopener">
                    <img
                        src="https://simp6.jpg5.su/images3/issfanfan-20250129-0001ef763780833ed714.md.jpg"
                        data-url="https://simp6.jpg5.su/images3/issfanfan-20250129-0001ef763780833ed714.md.jpg"
                        class="bbImage"
                        loading="lazy"
                        alt="issfanfan-20250129-0001ef763780833ed714.md.jpg"
                        title="issfanfan-20250129-0001ef763780833ed714.md.jpg"
                        style=""
                        width=""
                        height=""
                    />
                </a>
            </div>""",
            [
                "https://simp6.jpg5.su/images3/issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg",
                "https://simp6.jpg5.su/images3/issfanfan-20250129-0001ef763780833ed714.md.jpg",
            ],
        ),
        (
            crawlers.SimpCityCrawler,
            """
                <a href="https://jpg5.su/img/aqDYT6c" target="_blank" class="link link--external" rel="nofollow ugc noopener">
                    <img
                        src="https://simp6.jpg5.su/images3/issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg"
                        data-url="https://simp6.jpg5.su/images3/issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg"
                        class="bbImage"
                        loading="lazy"
                        alt="issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg"
                        title="issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg"
                        style=""
                        width=""
                        height=""
                    />
                </a>
                <a href="https://jpg5.su/img/aqDYZAt" target="_blank" class="link link--external" rel="nofollow ugc noopener">
                    <img
                        src="https://simp6.jpg5.su/images3/issfanfan-20250129-0001ef763780833ed714.md.jpg"
                        data-url="https://simp6.jpg5.su/images3/issfanfan-20250129-0001ef763780833ed714.md.jpg"
                        class="bbImage"
                        loading="lazy"
                        alt="issfanfan-20250129-0001ef763780833ed714.md.jpg"
                        title="issfanfan-20250129-0001ef763780833ed714.md.jpg"
                        style=""
                        width=""
                        height=""
                    />
                </a>
            </div>""",
            [
                "https://simp6.jpg5.su/images3/issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg",
                "https://simp6.jpg5.su/images3/issfanfan-20250129-0001ef763780833ed714.md.jpg",
            ],
        ),
        (
            crawlers.SimpCityCrawler,
            """
                <a href="https://jpg5.su/img/aqDYT6c" target="_blank" class="link link--external" rel="nofollow ugc noopener">
                    <img
                        src="https://simp6.jpg5.su/images3/issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg"
                        data-url="https://simp6.jpg5.su/images3/issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg"
                        class="bbImage"
                        loading="lazy"
                        alt="issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg"
                        title="issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg"
                        style=""
                        width=""
                        height=""
                    />
                </a>
                <a href="https://jpg5.su/img/aqDYZAt" target="_blank" class="link link--external" rel="nofollow ugc noopener">
                    <img
                        src="https://simp6.jpg5.su/images3/issfanfan-20250129-0001ef763780833ed714.md.jpg"
                        data-url="https://simp6.jpg5.su/images3/issfanfan-20250129-0001ef763780833ed714.md.jpg"
                        class="bbImage"
                        loading="lazy"
                        alt="issfanfan-20250129-0001ef763780833ed714.md.jpg"
                        title="issfanfan-20250129-0001ef763780833ed714.md.jpg"
                        style=""
                        width=""
                        height=""
                    />
                </a>
            </div>""",
            [
                "https://simp6.jpg5.su/images3/issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg",
                "https://simp6.jpg5.su/images3/issfanfan-20250129-0001ef763780833ed714.md.jpg",
            ],
        ),
        (
            crawlers.SimpCityCrawler,
            """
                <a href="https://jpg5.su/img/aqDYT6c" target="_blank" class="link link--external" rel="nofollow ugc noopener">
                    <img
                        src="https://simp6.jpg5.su/images3/issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg"
                        data-url="https://simp6.jpg5.su/images3/issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg"
                        class="bbImage"
                        loading="lazy"
                        alt="issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg"
                        title="issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg"
                        style=""
                        width=""
                        height=""
                    />
                </a>
                <a href="https://jpg5.su/img/aqDYZAt" target="_blank" class="link link--external" rel="nofollow ugc noopener">
                    <img
                        src="https://simp6.jpg5.su/images3/issfanfan-20250129-0001ef763780833ed714.md.jpg"
                        data-url="https://simp6.jpg5.su/images3/issfanfan-20250129-0001ef763780833ed714.md.jpg"
                        class="bbImage"
                        loading="lazy"
                        alt="issfanfan-20250129-0001ef763780833ed714.md.jpg"
                        title="issfanfan-20250129-0001ef763780833ed714.md.jpg"
                        style=""
                        width=""
                        height=""
                    />
                </a>
            </div>""",
            [
                "https://simp6.jpg5.su/images3/issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg",
                "https://simp6.jpg5.su/images3/issfanfan-20250129-0001ef763780833ed714.md.jpg",
            ],
        ),
        (
            crawlers.SimpCityCrawler,
            """
                <a href="https://jpg5.su/img/aqDYT6c" target="_blank" class="link link--external" rel="nofollow ugc noopener">
                    <img
                        src="https://simp6.jpg5.su/images3/issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg"
                        data-url="https://simp6.jpg5.su/images3/issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg"
                        class="bbImage"
                        loading="lazy"
                        alt="issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg"
                        title="issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg"
                        style=""
                        width=""
                        height=""
                    />
                </a>
                <a href="https://jpg5.su/img/aqDYZAt" target="_blank" class="link link--external" rel="nofollow ugc noopener">
                    <img
                        src="https://simp6.jpg5.su/images3/issfanfan-20250129-0001ef763780833ed714.md.jpg"
                        data-url="https://simp6.jpg5.su/images3/issfanfan-20250129-0001ef763780833ed714.md.jpg"
                        class="bbImage"
                        loading="lazy"
                        alt="issfanfan-20250129-0001ef763780833ed714.md.jpg"
                        title="issfanfan-20250129-0001ef763780833ed714.md.jpg"
                        style=""
                        width=""
                        height=""
                    />
                </a>
            </div>""",
            [
                "https://simp6.jpg5.su/images3/issfanfan-20250129-0002b2b2fa9a5390f521.md.jpg",
                "https://simp6.jpg5.su/images3/issfanfan-20250129-0001ef763780833ed714.md.jpg",
            ],
        ),
    ],
)
def test_post_images(cls: type[xenforo.XenforoCrawler], post_content: str, expected_result: list[str]) -> None:
    crawler = crawler_instances[cls]
    post = _post(post_content, crawler=crawler)
    results = list(crawler._images(post))
    count, expected_count = len(results), len(expected_result)
    assert count == expected_count, f"Found {count} links, expected {expected_count} links"
    assert results == expected_result


def test_embeds_can_extract_google_drive_links() -> None:
    # https://github.com/jbsparrow/CyberDropDownloader/issues/775
    crawler = crawler_instances[crawlers.SimpCityCrawler]
    content = """
    <div itemprop="text">
        <div class="bbWrapper">
            Got this video From her.<br />
            <span data-s9e-mediaembed="googledrive">
                <iframe allowfullscreen="" scrolling="no" src="//drive.google.com/file/d/1gfDjCbNXgJafY6ILQIrgbnuptSCFbM0J/preview" loading="eager"></iframe></span>
            </span>
        </div>
    </div>

    <div class="js-selectToQuoteEnd">&nbsp;</div>
    """
    post = _post(content, crawler=crawler)
    expected_result = "//drive.google.com/file/d/1gfDjCbNXgJafY6ILQIrgbnuptSCFbM0J/preview"
    results = list(crawler._embeds(post))
    assert len(results) == 1
    assert results[0] == expected_result


def test_post_smg_extract_attachments() -> None:
    # https://github.com/jbsparrow/CyberDropDownloader/issues/1070
    attachments = """
    <h4 class="block-textHeader">Attachments</h4>
        <ul class="attachmentList">
            <li class="file file--linked">
                <a class="u-anchorTarget" id="attachment-3494354"></a>

                <a
                    class="file-preview js-lbImage"
                    href="https://smgmedia2.socialmediagirls.com/forum/2022/04/33E3EDFF-B0ED-4AE3-8D5D-4D2BC6D7EFD4_3526918.jpeg"
                    target="_blank"
                    data-fancybox="lb-thread-111099"
                    style="cursor: pointer;"
                    data-caption='<h4>33E3EDFF-B0ED-4AE3-8D5D-4D2BC6D7EFD4.jpeg</h4><p><a href="https:&amp;#x2F;&amp;#x2F;forums.socialmediagirls.com&amp;#x2F;threads&amp;#x2F;loalux.111099&amp;#x2F;#post-1707346" class="js-lightboxCloser">Ixvvxi · Apr 23, 2022 at 10:10 PM</a></p>'
                >
                    <img
                        src="https://smgmedia2.socialmediagirls.com/forum/2022/04/thumb/33E3EDFF-B0ED-4AE3-8D5D-4D2BC6D7EFD4_3526918.jpeg"
                        alt="33E3EDFF-B0ED-4AE3-8D5D-4D2BC6D7EFD4.jpeg"
                        width="250"
                        height="425"
                        loading="lazy"
                    />
                </a>

                <div class="file-content">
                    <div class="file-info">
                        <span class="file-name" title="33E3EDFF-B0ED-4AE3-8D5D-4D2BC6D7EFD4.jpeg">33E3EDFF-B0ED-4AE3-8D5D-4D2BC6D7EFD4.jpeg</span>
                        <div class="file-meta">
                            1.3 MB · Views: 0
                        </div>
                    </div>
                </div>
            </li>

            <li class="file file--linked">
                <a class="u-anchorTarget" id="attachment-3494355"></a>

                <a
                    class="file-preview js-lbImage"
                    href="https://smgmedia2.socialmediagirls.com/forum/2022/04/3663188F-00C6-4C90-AB4D-D8C6E7859286_3526919.png"
                    target="_blank"
                    data-fancybox="lb-thread-111099"
                    style="cursor: pointer;"
                    data-caption='<h4>3663188F-00C6-4C90-AB4D-D8C6E7859286.png</h4><p><a href="https:&amp;#x2F;&amp;#x2F;forums.socialmediagirls.com&amp;#x2F;threads&amp;#x2F;loalux.111099&amp;#x2F;#post-1707346" class="js-lightboxCloser">Ixvvxi · Apr 23, 2022 at 10:10 PM</a></p>'
                >
                    <img src="https://smgmedia2.socialmediagirls.com/forum/2022/04/thumb/3663188F-00C6-4C90-AB4D-D8C6E7859286_3526919.png" alt="3663188F-00C6-4C90-AB4D-D8C6E7859286.png" width="364" height="250" loading="lazy" />
                </a>

                <div class="file-content">
                    <div class="file-info">
                        <span class="file-name" title="3663188F-00C6-4C90-AB4D-D8C6E7859286.png">3663188F-00C6-4C90-AB4D-D8C6E7859286.png</span>
                        <div class="file-meta">
                            1.6 MB · Views: 0
                        </div>
                    </div>
                </div>
            </li>
        </ul>
    """
    crawler = crawler_instances[crawlers.SocialMediaGirlsCrawler]
    post = _post(message_attachments=attachments, crawler=crawler)
    expected_result = [
        "https://smgmedia2.socialmediagirls.com/forum/2022/04/33E3EDFF-B0ED-4AE3-8D5D-4D2BC6D7EFD4_3526918.jpeg",
        "https://smgmedia2.socialmediagirls.com/forum/2022/04/3663188F-00C6-4C90-AB4D-D8C6E7859286_3526919.png",
    ]

    result = list(crawler._attachments(post))
    count, expected_count = len(result), len(expected_result)
    assert count == expected_count, f"Found {count} links, expected {expected_count} links"
    assert result == expected_result


def test_post_celebforum_should_use_href_for_images() -> None:
    # https://github.com/jbsparrow/CyberDropDownloader/issues/1093
    content = """
    <a href="https://celebforum.to/attachments/jc6huqrju9-jpg.321620/" target="_blank"><img alt="JC6HUqrju9" class="bbImage"
        height="200" loading="lazy"
        src="https://celebforum.to/data/attachments/321/321141-2d66067afbf5cd3d546479380c08929d.jpg" style=""
        title="JC6HUqrju9" width="150" /></a>
    """
    crawler = crawler_instances[crawlers.CelebForumCrawler]
    post = _post(content, crawler=crawler)
    expected_result = ["https://celebforum.to/attachments/jc6huqrju9-jpg.321620/"]
    result = list(crawler._images(post))
    count, expected_count = len(result), len(expected_result)
    assert count == expected_count, f"Found {count} links, expected {expected_count} links"
    assert result == expected_result


def test_get_post_title_thread_w_prefixes() -> None:
    html = _html("""
    <div class="p-title ">
        <h1 class="p-title-value">
            <a href="/forums/requests.7/?prefix_id=2" class="labelLink" rel="nofollow">
                 <span class="label label--requests" dir="auto">Request</span></a>
                 <span class="label-append">&nbsp;</span><a href="/forums/requests.7/?prefix_id=8" class="labelLink" rel="nofollow">
                 <span class="label label--youtube" dir="auto">Youtube</span></a><span class="label-append">&nbsp;</span>
            <a href="/forums/requests.7/?prefix_id=3" class="labelLink" rel="nofollow">
                 <span class="label label--onlyfans" dir="auto">OnlyFans</span></a>
                 <span class="label-append">&nbsp;</span><a href="/forums/requests.7/?prefix_id=7" class="labelLink" rel="nofollow">
                 <span class="label label--insta" dir="auto">Instagram</span></a>
                 <span class="label-append">&nbsp;</span>GunplaMeli</h1>
    </div>
    """)
    soup = BeautifulSoup(html, "html.parser")
    title = _forum.get_post_title(soup, xenforo.XenforoCrawler.SELECTORS)
    assert title == "GunplaMeli"


def test_get_post_title_thread_w_no_prefixes() -> None:
    html = """
    <div class="p-title">
        <h1 class="p-title-value">Staged/Fake Japanese Candid Videos from Gcolle/Pcolle or FC2</h1>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    title = _forum.get_post_title(soup, xenforo.XenforoCrawler.SELECTORS)
    assert title == "Staged/Fake Japanese Candid Videos from Gcolle/Pcolle or FC2"


def test_get_post_title_no_title_found() -> None:
    html = _html("")
    soup = BeautifulSoup(html, "html.parser")
    with pytest.raises(ScrapeError) as exc_info:
        _forum.get_post_title(soup, xenforo.XenforoCrawler.SELECTORS)

    assert exc_info.value.status == 429
    assert exc_info.value.message == "Invalid response from forum. You may have been rate limited"


def test_get_post_title_empty_title_block() -> None:
    html = _html("""<h1 class="p-title-value"></h1>""")
    soup = BeautifulSoup(html, "html.parser")
    with pytest.raises(ScrapeError):
        _forum.get_post_title(soup, xenforo.XenforoCrawler.SELECTORS)


def test_get_post_title_non_english_chars() -> None:
    html = _html("""
    <div class="p-title">
        <h1 class="p-title-value">
            ㊙️Hcupりおの極秘えち任務🙊💗 (りお❤️❤️❤️) / りお@Rio / rio_hcup_fantia
        </h1>
    </div>
    """)
    soup = BeautifulSoup(html, "html.parser")
    title = _forum.get_post_title(soup, xenforo.XenforoCrawler.SELECTORS)
    assert title == "㊙️Hcupりおの極秘えち任務🙊💗 (りお❤️❤️❤️) / りお@Rio / rio_hcup_fantia"


def test_get_post_title_should_strip_new_lines() -> None:
    html = _html("""
    <div class="p-title">
        <h1 class="p-title-value">
            ㊙️Hcupりおの極秘えち任務🙊💗 (りお❤️❤️❤️)
            / りお@Rio /
              rio_hcup_fantia
        </h1>
    </div>
    """)
    soup = BeautifulSoup(html, "html.parser")
    title = _forum.get_post_title(soup, xenforo.XenforoCrawler.SELECTORS)
    assert title == "㊙️Hcupりおの極秘えち任務🙊💗 (りお❤️❤️❤️) / りお@Rio / rio_hcup_fantia"


def test_is_attachment_should_handle_none() -> None:
    assert TEST_CRAWLER.is_attachment(None) is False  # type: ignore


@pytest.mark.parametrize(
    "link_str",
    [
        "https://media.imagepond.net/media/golden-hour86caaa9858726a64.jpg",
        "https://simp6.jpg5.su/images3/1752x1172_a682e9c85a276121e82018b4031206b9be2e64efe5bc8004.md.jpg",
        "https://jpg5.su/img/aDDJbdK",
        "https://simp6.jpg5.su/attachment/1752x1172_a682e9c85a276121e82018b4031206b9be2e64efe5bc8004.md.jpg",  # No exact 'attachment' part
        "http://celebforum.to/attachments",  # missing file slug
    ],
)
def test_is_attachment_string_false(link_str: str) -> None:
    assert TEST_CRAWLER.is_attachment(link_str) is False


def test_is_attachment_empty_string_should_be_false() -> None:
    assert TEST_CRAWLER.is_attachment("") is False


class TestCheckPostId:
    @pytest.mark.parametrize(
        "init_post_id, current_post_id, scrape_single_forum_post, expected_continue_scraping, expected_scrape_this_post",
        [
            # init_post_id > current_post_id
            (100, 90, True, True, False),
            (100, 90, False, True, False),
            # init_post_id == current_post_id
            (100, 100, True, False, True),
            (100, 100, False, True, True),
            # init_post_id < current_post_id
            (100, 110, True, False, False),
            (100, 110, False, True, True),
        ],
    )
    def test_init_post_id_was_provided(
        self,
        init_post_id: int,
        current_post_id: int,
        scrape_single_forum_post: bool,
        expected_continue_scraping: bool,
        expected_scrape_this_post: bool,
    ) -> None:
        continue_scraping, scrape_this_post = _forum.check_post_id(
            init_post_id, current_post_id, scrape_single_forum_post
        )
        assert continue_scraping == expected_continue_scraping
        assert scrape_this_post == expected_scrape_this_post

    def test_no_init_post_id_and_scrape_single_post_false(self) -> None:
        init_post_id = None
        current_post_id = 100
        scrape_single_forum_post = False
        continue_scraping, scrape_this_post = _forum.check_post_id(
            init_post_id, current_post_id, scrape_single_forum_post
        )
        assert continue_scraping is True
        assert scrape_this_post is True

    def test_no_init_post_id_and_scrape_single_post_true_raises_error(self) -> None:
        init_post_id = None
        current_post_id = 100
        scrape_single_forum_post = True

        with pytest.raises(AssertionError):
            _forum.check_post_id(init_post_id, current_post_id, scrape_single_forum_post)


# og_post_id = 23549340
POST_TEMPLATE = """
<article class="message message--post js-post js-inlineModContainer" data-author="" data-content="post-{id}" id="js-post-{id}" itemscope="" itemtype="https://schema.org/Comment" itemid="https://simpcity.su/posts/{id}/">
    <meta itemprop="parentItem" itemscope="" itemid="https://xenforocomunity.com/threads/fanfan.33077/" />

    <span class="u-anchorTarget" id="post-{id}"></span>

    <div class="message-inner">
        <div class="message-cell message-cell--user">
            <section class="message-user" itemprop="author" itemscope="" itemtype="https://schema.org/Person" itemid="https://xenforocomunity.com/members/mrspike.5160076/">
                <meta itemprop="url" content="https://xenforocomunity.com/members/mrspike.5160076/" />

                <div class="message-avatar">
                    <div class="message-avatar-wrapper">
                        <a href="/members/mrspike.5160076/" class="avatar avatar--m" data-user-id="5160076" data-xf-init="member-tooltip" id="js-XFUniqueId10">
                            <img
                                src="http://simp6.jpg5.su/simpo/data/avatars/m/5160/5160076.jpg?1746748029"
                                srcset="http://simp6.jpg5.su/simpo/data/avatars/l/5160/5160076.jpg?1746748029 2x"
                                alt=""
                                class="avatar-u5160076-m"
                                width="96"
                                height="96"
                                loading="lazy"
                                itemprop="image"
                            />
                        </a>
                    </div>
                </div>
                <div class="message-userDetails">
                    <h4 class="message-name">
                        <a href="/members/mrspike.5160076/" class="username" dir="auto" data-user-id="5160076" data-xf-init="member-tooltip" id="js-XFUniqueId11"><span itemprop="name"></span></a>
                    </h4>
                    <h5 class="userTitle message-userTitle" dir="auto" itemprop="jobTitle">Bathwater Drinker</h5>
                    <div class="userBanner banner--simp message-userBanner" itemprop="jobTitle"><span class="userBanner-before"></span><strong>⠀Simp⠀</strong><span class="userBanner-after"></span></div>
                </div>

                <div class="message-userExtras">
                    <dl class="pairs pairs--justified">
                        <dt>
                            <i class="fa--xf far fa-user">
                                <svg xmlns="http://www.w3.org/2000/svg" role="img" aria-hidden="true"><use href="/data/local/icons/regular.svg?v=1750411220#user"></use></svg>
                            </i>
                        </dt>
                        <dd>Aug 1, 2024</dd>
                    </dl>

                    <dl class="pairs pairs--justified">
                        <dt>
                            <i class="fa--xf far fa-comment">
                                <svg xmlns="http://www.w3.org/2000/svg" role="img" aria-hidden="true"><use href="/data/local/icons/regular.svg?v=1750411220#comment"></use></svg>
                            </i>
                        </dt>
                        <dd>38</dd>
                    </dl>

                    <dl class="pairs pairs--justified">
                        <dt>
                            <i class="fa--xf far fa-thumbs-up">
                                <svg xmlns="http://www.w3.org/2000/svg" role="img" aria-hidden="true"><use href="/data/local/icons/regular.svg?v=1750411220#thumbs-up"></use></svg>
                            </i>
                        </dt>
                        <dd>3,783</dd>
                    </dl>
                </div>

                <span class="message-userArrow"></span>
            </section>
        </div>

        <div class="message-cell message-cell--main">
            <div class="message-main js-quickEditTarget">
                <header class="message-attribution message-attribution--split">
                    <ul class="message-attribution-main listInline">
                        <li class="u-concealed">
                            <a href="/threads/fanfan.33077/post-{id}" rel="nofollow" itemprop="url">
                                <time
                                    class="u-dt"
                                    dir="auto"
                                    datetime="2025-06-09T17:30:10-0500"
                                    data-timestamp="1749508210"
                                    data-date="Jun 9, 2025"
                                    data-time="5:30 PM"
                                    data-short="12d"
                                    title="Jun 9, 2025 at 5:30 PM"
                                    itemprop="datePublished"
                                >
                                    Jun 9, 2025
                                </time>
                            </a>
                        </li>
                    </ul>

                    <ul class="message-attribution-opposite message-attribution-opposite--list">
                        <li>
                            <a href="/threads/fanfan.33077/post-{id}" class="message-attribution-gadget" data-xf-init="share-tooltip" data-href="/posts/{id}/share" aria-label="Share" rel="nofollow" id="js-XFUniqueId41">
                                <i class="fa--xf far fa-share-alt">
                                    <svg xmlns="http://www.w3.org/2000/svg" role="img" aria-hidden="true"><use href="/data/local/icons/regular.svg?v=1750411220#share-alt"></use></svg>
                                </i>
                            </a>
                        </li>

                        <li class="u-hidden js-embedCopy">
                            <a
                                href="javascript:"
                                data-xf-init="copy-to-clipboard"
                                data-copy-text='<div class="js-xf-embed" data-url="https://xenforocomunity.com" data-content="post-{id}"></div><script defer src="https://xenforocomunity.com/js/xf/external_embed.js?_v=dc874496"></script>'
                                data-success="Embed code HTML copied to clipboard."
                                class=""
                            >
                                <i class="fa--xf far fa-code">
                                    <svg xmlns="http://www.w3.org/2000/svg" role="img" aria-hidden="true"><use href="/data/local/icons/regular.svg?v=1750411220#code"></use></svg>
                                </i>
                            </a>
                        </li>

                        <li>
                            <a
                                href="/posts/{id}/bookmark"
                                class="bookmarkLink message-attribution-gadget bookmarkLink--highlightable"
                                title="Add bookmark"
                                data-xf-click="bookmark-click"
                                data-label=".js-bookmarkText"
                                data-sk-bookmarked="addClass:is-bookmarked, titleAttr:sync"
                                data-sk-bookmarkremoved="removeClass:is-bookmarked, titleAttr:sync"
                            >
                                <span class="js-bookmarkText u-srOnly">Add bookmark</span>
                            </a>
                        </li>

                        <li>
                            <a href="/threads/fanfan.33077/post-{id}" rel="nofollow">
                                #282
                            </a>
                        </li>
                    </ul>
                </header>

                <div class="message-content js-messageContent">
                    <div class="message-userContent lbContainer js-lbContainer" data-lb-id="post-{id}" data-lb-caption-desc=" · Jun 9, 2025 at 5:30 PM">
                        <article class="message-body js-selectToQuote">
                            {message_body}
                            <div class="js-selectToQuoteEnd">&nbsp;</div>
                        </article>
                    </div>

                    <aside class="message-signature">
                        <div class="bbWrapper">Cant post to Bunkr. Mirrors are always appreciated.</div>
                    </aside>
                </div>

				<div class="message-attachments">
                    {message_attachments}
                </div>

                <footer class="message-footer">
                    <div class="message-microdata" itemprop="interactionStatistic" itemtype="https://schema.org/InteractionCounter" itemscope="">
                        <meta itemprop="userInteractionCount" content="160" />
                        <meta itemprop="interactionType" content="https://schema.org/LikeAction" />
                    </div>

                    <div class="message-actionBar actionBar">
                        <div class="actionBar-set actionBar-set--external">
                            <a
                                href="/posts/{id}/react?reaction_id=1"
                                class="reaction reaction--small actionBar-action actionBar-action--reaction reaction--imageHidden reaction--1"
                                data-reaction-id="1"
                                data-xf-init="reaction"
                                data-reaction-list="< .js-post | .js-reactionsList"
                                id="js-XFUniqueId12"
                            >
                                <i aria-hidden="true"></i><img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" loading="lazy" class="reaction-sprite js-reaction" alt="Like" title="Like" />
                                <span class="reaction-text js-reactionText"><bdi>Like</bdi></span>
                            </a>

                            <a href="/threads/fanfan.33077/reply?quote={id}" class="actionBar-action actionBar-action--mq u-jsOnly js-multiQuote" title="Toggle multi-quote" rel="nofollow" data-message-id="{id}" data-mq-action="add">
                                Quote
                            </a>

                            <a
                                href="/threads/fanfan.33077/reply?quote={id}"
                                class="actionBar-action actionBar-action--reply"
                                title="Reply, quoting this message"
                                rel="nofollow"
                                data-xf-click="quote"
                                data-quote-href="/posts/{id}/quote"
                            >
                                Reply
                            </a>
                        </div>

                        <div class="actionBar-set actionBar-set--internal">
                            <a href="/posts/{id}/report" class="actionBar-action actionBar-action--report" data-xf-click="overlay" data-cache="false">Report</a>
                        </div>
                    </div>

                    <div class="reactionsBar js-reactionsList is-active">
                        <ul class="reactionSummary">
                            <li>
                                <span class="reaction reaction--small reaction--1" data-reaction-id="1">
                                    <i aria-hidden="true"></i><img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" loading="lazy" class="reaction-sprite js-reaction" alt="Like" title="Like" />
                                </span>
                            </li>
                            <li>
                                <span class="reaction reaction--small reaction--33" data-reaction-id="33">
                                    <i aria-hidden="true"></i><img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" loading="lazy" class="reaction-sprite js-reaction" alt="PeepoLove" title="PeepoLove" />
                                </span>
                            </li>
                            <li>
                                <span class="reaction reaction--small reaction--50" data-reaction-id="50">
                                    <i aria-hidden="true"></i><img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" loading="lazy" class="reaction-sprite js-reaction" alt="PeepoWew" title="PeepoWew" />
                                </span>
                            </li>
                        </ul>

                        <span class="u-srOnly">Reactions:</span>
                        <a class="reactionsBar-link" href="/posts/{id}/reactions" data-xf-click="overlay" data-cache="false" rel="nofollow"><bdi>DDDICKS</bdi>, <bdi>cachow</bdi>, <bdi>StubbornOne</bdi> and 145 others</a>
                    </div>

                    <div class="js-historyTarget message-historyTarget toggleTarget" data-href="trigger-href"></div>
                </footer>
            </div>
        </div>
    </div>
</article>

"""
