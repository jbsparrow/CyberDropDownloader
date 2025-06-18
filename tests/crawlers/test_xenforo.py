from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest
from bs4 import BeautifulSoup

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


def _post(message_body: str, id: int = 12345, crawler: xenforo.XenforoCrawler | None = None) -> xenforo.ForumPost:
    crawler = crawler or TEST_CRAWLER
    html = _html(POST_TEMPLATE.format(id=id, message_body=message_body))
    soup = BeautifulSoup(html, "html.parser")
    return xenforo.ForumPost.new(soup, crawler.XF_SELECTORS.posts)


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
    ("url", "thread_part_name", "result", "canonical_url"),
    [
        [
            "https://simpcity.su/threads/general-support.208041/page-260#post-23934165",
            "threads",
            (
                "general-support",
                208041,
                260,
                23934165,
            ),
            "https://simpcity.su/threads/general-support.208041",
        ],
        [
            "https://celebforum.to/threads/infos-regelaenderungen.18821/page-3",
            "threads",
            (
                "infos-regelaenderungen",
                18821,
                3,
                0,
            ),
            "https://celebforum.to/threads/infos-regelaenderungen.18821",
        ],
        [
            "https://www.bellazon.com/main/topic/27120-the-official-victorias-secret-thread",
            "topic",
            (
                "the-official-victorias-secret-thread",
                27120,
                0,
                0,
            ),
            "https://www.bellazon.com/main/topic/27120-the-official-victorias-secret-thread",
        ],
        [
            "https://forums.socialmediagirls.com/threads/forum-rules.14/post-34",
            "threads",
            (
                "forum-rules",
                14,
                0,
                34,
            ),
            "https://forums.socialmediagirls.com/threads/forum-rules.14",
        ],
        [
            "https://forums.socialmediagirls.com/threads/should-we-ban-gofile-76-5-say-no.436901/post-3942103",
            "threads",
            (
                "should-we-ban-gofile-76-5-say-no",
                436901,
                0,
                3942103,
            ),
            "https://forums.socialmediagirls.com/threads/should-we-ban-gofile-76-5-say-no.436901",
        ],
        [
            "https://forums.socialmediagirls.com/threads/en-fr-tools-to-download-upload-content-websites-softwares-extensions.13930/page-11/#post-2070848",
            "threads",
            (
                "en-fr-tools-to-download-upload-content-websites-softwares-extensions",
                13930,
                11,
                2070848,
            ),
            "https://forums.socialmediagirls.com/threads/en-fr-tools-to-download-upload-content-websites-softwares-extensions.13930",
        ],
        [
            "https://f95zone.to/threads/mod-uploading-rules-12-02-2018.9236/post-2726083",
            "threads",
            (
                "mod-uploading-rules-12-02-2018",
                9236,
                0,
                2726083,
            ),
            "https://f95zone.to/threads/mod-uploading-rules-12-02-2018.9236",
        ],
    ],
)
def test_parse_thread_info(
    url: str, thread_part_name: str, result: tuple[str, int, int, int], canonical_url: str
) -> None:
    url_, canonical_url_ = AbsoluteHttpURL(url), AbsoluteHttpURL(canonical_url)
    result_ = xenforo.Thread(*result, canonical_url_)
    parsed = xenforo.parse_thread(url_, thread_part_name, "page", "post")
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
    assert xenforo.clean_link_str(link) == out


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
    assert xenforo.extract_embed_url(input_string) == expected_output


@pytest.mark.xfail  # regex can not handle URLs with commans in it (kvs)
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
    assert xenforo.extract_embed_url(input_string) == expected_output


def test_extract_embed_url_should_extract_only_one_url() -> None:
    input_str = r"first_url \/\/first.com/path second_url \/\/www.second.net/another"
    expected_output = "https://first.com/path"
    assert xenforo.extract_embed_url(input_str) == expected_output


def test_extract_embed_url_with_escaped_backslashes_and_double_slashes() -> None:
    input_str = r"some_path\\to\\file\/\/imagepond.net\/clip.mov"
    expected_output = "https://imagepond.net/clip.mov"
    assert xenforo.extract_embed_url(input_str) == expected_output


def test_extract_embed_url_absolute_url_no_scheme() -> None:
    input_str = r"\/\/jpg5.su"
    expected_output = r"https://jpg5.su"
    assert xenforo.extract_embed_url(input_str) == expected_output


def test_extract_embed_url_should_not_modify_absolute_urls() -> None:
    input_str = r"https://celebforum.to/maps"
    expected_output = "https://celebforum.to/maps"
    assert xenforo.extract_embed_url(input_str) == expected_output


def test_extract_embed_url_string_ends_with_url() -> None:
    input_str = r"some text https://www.reddit.com/"
    expected_output = "https://reddit.com/"
    assert xenforo.extract_embed_url(input_str) == expected_output


async def test_test_hidden_redgifs() -> None:
    post = _post("""
    <div class="generic2wide-iframe-div" onclick="loadMedia(this, '//redgifs.com/ifr/downrightcluelesswirm');">
        <span data-s9e-mediaembed="redgifs">
            <span class="iframe-wrapper-redgifs" style="">
                <span class="iframe-wrapper-redgifs-info">Click here to load redgifs media</span>
            </span>
        </span>
    </div>""")
    expected_output = "//redgifs.com/ifr/downrightcluelesswirm"
    with _amock() as mocked:
        await TEST_CRAWLER._lazy_load_embeds(scrape_item, post)
        mocked.assert_called_once_with(scrape_item, expected_output, embeds=True)


@pytest.mark.parametrize(
    ("cls", "post_content", "expected_result"),
    [
        (
            crawlers.SimpCityCrawler,
            """
    <div class="bbWrapper">
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
        )
    ],
)
async def test_post_images(cls: type[xenforo.XenforoCrawler], post_content: str, expected_result: list[str]) -> None:
    crawler = crawler_instances[cls]
    post = _post(post_content, crawler=crawler)
    with _amock(crawler=crawler) as mocked:
        await crawler._images(scrape_item, post)
        count, expected_count = mocked.call_count, len(expected_result)
        assert count == expected_count, f"Found {count} links, expected {expected_count} links"
        for result, expected in zip(mocked.call_args_list, expected_result, strict=True):
            assert result.args[1] == expected


async def test_embeds_can_extract_google_drive_links() -> None:
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
    with _amock(crawler=crawler) as mocked:
        await crawler._embeds(scrape_item, post)
        mocked.assert_called_once()
        assert mocked.call_args.args[1] == expected_result


async def test_post_smg_extract_attachments() -> None:
    # https://agithub.com/jbsparrow/CyberDropDownloader/issues/1070
    content = """
    <section class="message-attachments">
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
                    <img src="https://smgmedia2.socialmediagirls.com/forum/2022/04/thumb/33E3EDFF-B0ED-4AE3-8D5D-4D2BC6D7EFD4_3526918.jpeg" alt="33E3EDFF-B0ED-4AE3-8D5D-4D2BC6D7EFD4.jpeg" width="250" height="425" loading="lazy" />
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
    </section>
    """
    crawler = crawler_instances[crawlers.SocialMediaGirlsCrawler]
    post = _post(content, crawler=crawler)
    expected_result = [
        "https://smgmedia2.socialmediagirls.com/forum/2022/04/33E3EDFF-B0ED-4AE3-8D5D-4D2BC6D7EFD4_3526918.jpeg",
        "https://smgmedia2.socialmediagirls.com/forum/2022/04/3663188F-00C6-4C90-AB4D-D8C6E7859286_3526919.png",
    ]
    with _amock(crawler=crawler) as mocked:
        await crawler._attachments(scrape_item, post)
        count, expected_count = mocked.call_count, len(expected_result)
        assert count == expected_count, f"Found {count} links, expected {expected_count} links"
        for result, expected in zip(mocked.call_args_list, expected_result, strict=True):
            assert result.args[1] == expected


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
    title = xenforo.get_post_title(soup, xenforo.XenforoCrawler.XF_SELECTORS)
    assert title == "GunplaMeli"


def test_get_post_title_thread_w_no_prefixes() -> None:
    html = """
    <div class="p-title">
        <h1 class="p-title-value">Staged/Fake Japanese Candid Videos from Gcolle/Pcolle or FC2</h1>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    title = xenforo.get_post_title(soup, xenforo.XenforoCrawler.XF_SELECTORS)
    assert title == "Staged/Fake Japanese Candid Videos from Gcolle/Pcolle or FC2"


def test_get_post_title_no_title_found() -> None:
    html = _html("")
    soup = BeautifulSoup(html, "html.parser")
    with pytest.raises(ScrapeError) as exc_info:
        xenforo.get_post_title(soup, xenforo.XenforoCrawler.XF_SELECTORS)

    assert exc_info.value.status == 429
    assert exc_info.value.message == "Invalid response from forum. You may have been rate limited"


def test_get_post_title_empty_title_block() -> None:
    html = _html("""<h1 class="p-title-value"></h1>""")
    soup = BeautifulSoup(html, "html.parser")
    with pytest.raises(ScrapeError):
        xenforo.get_post_title(soup, xenforo.XenforoCrawler.XF_SELECTORS)


def test_get_post_title_non_english_chars() -> None:
    html = _html("""
    <div class="p-title">
        <h1 class="p-title-value">
            ㊙️Hcupりおの極秘えち任務🙊💗 (りお❤️❤️❤️) / りお@Rio / rio_hcup_fantia
        </h1>
    </div>
    """)
    soup = BeautifulSoup(html, "html.parser")
    title = xenforo.get_post_title(soup, xenforo.XenforoCrawler.XF_SELECTORS)
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
    title = xenforo.get_post_title(soup, xenforo.XenforoCrawler.XF_SELECTORS)
    assert title == "㊙️Hcupりおの極秘えち任務🙊💗 (りお❤️❤️❤️) / りお@Rio / rio_hcup_fantia"


def test_is_attachment_should_handle_none() -> None:
    assert TEST_CRAWLER.is_attachment(None) is False


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


POST_TEMPLATE = """
<article class="message message--post js-post js-inlineModContainer" data-author="MrSpike" data-content="post{id}" id="js-post{id}" itemscope="" itemtype="https://schema.org/Comment" itemid="https://xenforo.com/posts/23549340/">
    <meta itemprop="parentItem" itemscope="" itemid="https://xenforo.com/threads/fanfan.33077/" />

    <span class="u-anchorTarget" id="post{id}"></span>

    <div class="message-inner">
        <div class="message-cell message-cell--main">
            <div class="message-main js-quickEditTarget">
                <header class="message-attribution message-attribution--split">
                    <ul class="message-attribution-main listInline">
                        <li class="u-concealed">
                            <a href="/threads/fanfan.33077/post{id}" rel="nofollow" itemprop="url">
                                <time
                                    class="u-dt"
                                    dir="auto"
                                    datetime="2025-06-09T17:30:10-0500"
                                    data-timestamp="1749508210"
                                    data-date="Jun 9, 2025"
                                    data-time="5:30 PM"
                                    data-short="7d"
                                    title="Jun 9, 2025 at 5:30 PM"
                                    itemprop="datePublished"
                                >
                                    Jun 9, 2025
                                </time>
                            </a>
                        </li>
                    </ul>
                </header>

                <div class="message-content js-messageContent">
                    <div class="message-userContent lbContainer js-lbContainer" data-lb-id="post{id}" data-lb-caption-desc="MrSpike · Jun 9, 2025 at 5:30 PM">
                        <article class="message-body js-selectToQuote">
                            {message_body}
                            <div class="js-selectToQuoteEnd">&nbsp;</div>
                        </article>
                    </div>

                    <aside class="message-signature">
                        <div class="bbWrapper">Can't post to Bunkr. Mirrors are always appreciated.</div>
                    </aside>
                </div>

                <footer class="message-footer">
                    <div class="message-microdata" itemprop="interactionStatistic" itemtype="https://schema.org/InteractionCounter" itemscope="">
                        <meta itemprop="userInteractionCount" content="154" />
                        <meta itemprop="interactionType" content="https://schema.org/LikeAction" />
                    </div>

                    <div class="message-actionBar actionBar">
                        <div class="actionBar-set actionBar-set--external">
                            <a
                                href="/posts/23549340/react?reaction_id=1"
                                class="reaction reaction--small actionBar-action actionBar-action--reaction reaction--imageHidden reaction--1"
                                data-reaction-id="1"
                                data-xf-init="reaction"
                                data-reaction-list="< .js-post | .js-reactionsList"
                                id="js-XFUniqueId13"
                            >
                                <i aria-hidden="true"></i><img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" loading="lazy" class="reaction-sprite js-reaction" alt="Like" title="Like" />
                                <span class="reaction-text js-reactionText"><bdi>Like</bdi></span>
                            </a>

                            <a href="/threads/fanfan.33077/reply?quote=23549340" class="actionBar-action actionBar-action--mq u-jsOnly js-multiQuote" title="Toggle multi-quote" rel="nofollow" data-message-id="23549340" data-mq-action="add">
                                Quote
                            </a>

                            <a
                                href="/threads/fanfan.33077/reply?quote=23549340"
                                class="actionBar-action actionBar-action--reply"
                                title="Reply, quoting this message"
                                rel="nofollow"
                                data-xf-click="quote"
                                data-quote-href="/posts/23549340/quote"
                            >
                                Reply
                            </a>
                        </div>

                        <div class="actionBar-set actionBar-set--internal">
                            <a href="/posts/23549340/report" class="actionBar-action actionBar-action--report" data-xf-click="overlay" data-cache="false">Report</a>
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
                                <span class="reaction reaction--small reaction--91" data-reaction-id="91">
                                    <i aria-hidden="true"></i><img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" loading="lazy" class="reaction-sprite js-reaction" alt="PepeClown" title="PepeClown" />
                                </span>
                            </li>
                        </ul>

                        <span class="u-srOnly">Reactions:</span>
                        <a class="reactionsBar-link" href="/posts/23549340/reactions" data-xf-click="overlay" data-cache="false" rel="nofollow"><bdi>xigxagxion</bdi>, <bdi>Feistee</bdi>, <bdi>kradpmis</bdi> and 140 others</a>
                    </div>

                    <div class="js-historyTarget message-historyTarget toggleTarget" data-href="trigger-href"></div>
                </footer>
            </div>
        </div>
    </div>
</article>

"""
