import asyncio
import datetime
from typing import Any

import aiohttp
import pytest

from cyberdrop_dl import env
from cyberdrop_dl.crawlers.kemono.kemono import _extract_urls, _has_ads
from cyberdrop_dl.crawlers.kemono.models import Embed, File, UserPostModel, _parse_tags

pytestmark = pytest.mark.http
pytestmark = pytest.mark.skipif(env.CI, reason="Skip requests")


def request_json(url: str) -> Any:
    async def fetch():
        async with aiohttp.request("GET", url) as resp:
            return await resp.json(encoding="utf8", content_type=None)

    return asyncio.run(fetch())


@pytest.fixture(scope="session")
def post_resp() -> dict[str, Any]:
    resp = request_json("https://pawchive.pw/api/v1/patreon/user/3295915/post/129540190/revisions")
    return next(p for p in resp if p["revision_id"] == 59409)


@pytest.fixture(scope="session")
def post_resp_w_embeds() -> dict[str, Any]:
    return request_json("https://pawchive.pw/api/v1/patreon/user/47101380/post/128071303")


@pytest.fixture
def post(post_resp: dict[str, Any]) -> UserPostModel:
    return UserPostModel.model_validate(post_resp)


def test_post_validation(post_resp: dict[str, Any]) -> None:
    post = UserPostModel.model_validate(post_resp)
    assert post.id == "129540190"
    assert post.content
    assert (
        "<p>Hey everyone! Its been a long time in the making. I'm really proud of this one and I hope you all like is as much as I do!"
        in post.content
    )
    assert post.file == File(
        path="/4f/3a/4f3a65f8e123dfc1fb0a91ae7f001b598c96135695e977701daf55d528145d74.png",
        name="Timeline 1_0242.00_08_06_14.Still002.png",
        server=None,
        deferred=False,
    )
    assert post.attachments == (
        File(
            path="/4f/3a/4f3a65f8e123dfc1fb0a91ae7f001b598c96135695e977701daf55d528145d74.png",
            name="Timeline 1_0242.00_08_06_14.Still002.png",
            server=None,
        ),
    )
    assert post.published == datetime.datetime(2025, 5, 21, 18, 11, 4, tzinfo=datetime.UTC)
    assert post.added
    assert post.added.date() >= datetime.date(2026, 6, 11)
    assert post.edited
    assert post.edited > datetime.datetime(2026, 7, 8, 3, 11, 18, tzinfo=datetime.UTC)
    assert post.timestamp == 1747851064
    assert post.tags == ("Animation", "Announcement")
    assert post.embed is None
    assert post.has_full is True
    assert post.service == "patreon"
    assert post.user_id == "3295915"
    assert post.title == "DANDADAN FULL ANIMATION!!"
    assert post.web_path_qs == "patreon/user/3295915/post/129540190"
    assert _has_ads(post) is False


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (
            "<p>Who would have through that good guys had a 'no killing' rule?...</p><p><a href=\"https://www.dropbox.com/scl/fi/wsgws25ma0hyqggfwkwcd/Harley-Quinn-4x01-4x02.mp4?rlkey=lqf7wqu7mj6uwjlysoewqg0fw&st=00z4mrmq&dl=0\">https://www.dropbox.com/scl/fi/wsgws25ma0hyqggfwkwcd/Harley-Quinn-4x01-4x02.mp4?rlkey=lqf7wqu7mj6uwjlysoewqg0fw&st=00z4mrmq&dl=0</a></p>",
            [
                "https://www.dropbox.com/scl/fi/wsgws25ma0hyqggfwkwcd/Harley-Quinn-4x01-4x02.mp4?rlkey=lqf7wqu7mj6uwjlysoewqg0fw&st=00z4mrmq&dl=0"
            ],
        ),
        (
            "<p>Hey everyone! Its been a long time in the making. I'm really proud of this one and I hope you all like is as much as I do! I really tried my</p><p>Hey everyone!</p><p>Its been a long time in the making. I'm really proud of this one and I hope you all like is as much as I do! I really tried my best to do the characters justice and add a bit more comedy in this one!</p><p>In the next week I'll be doing an update on the other projects and when they're projected to finish! Right now I just have Alya and Sono Bisque Doll in the making but I'll probably be planning another in the next month or so using a poll!</p><h3><strong>Here is the </strong><a href=\"https://www.dropbox.com/scl/fi/ze2v1bih3lwvdjqn9syde/DDN-PATRON-ONLY.mp4?rlkey=oidlzqufodhr0nra3jfrgguxx&st=urfuvf73&dl=0\">LINK </a><strong>to the full animation!</strong></h3><p>Thanks for your patience and everything!</p>",
            [
                "https://www.dropbox.com/scl/fi/ze2v1bih3lwvdjqn9syde/DDN-PATRON-ONLY.mp4?rlkey=oidlzqufodhr0nra3jfrgguxx&st=urfuvf73&dl=0"
            ],
        ),
    ],
)
def test_extract_urls_from_content(content: str, expected: list[str]) -> None:
    found = list(_extract_urls(content))
    assert found
    assert found == expected


def test_validation_of_post_not_archived_yet(post_resp_w_embeds: dict[str, Any]) -> None:
    post = UserPostModel.model_validate(post_resp_w_embeds)
    assert post.id == "128071303"
    assert post.content == ""
    assert post.file == File(
        path="/83/66/8366796e0d9fadd5e22ae8f8ea32d1b539d54e25e9da19f906fa36d1cf973cc2.jpg",
        name="461372899.jpg",
        server=None,
    )
    assert post.attachments == ()
    assert post.published == datetime.datetime(2025, 5, 3, 17, 12, 47, tzinfo=datetime.UTC)
    assert post.added
    assert post.added.date() == datetime.date(2026, 6, 10)
    assert post.edited is None
    assert post.timestamp == 1746292367
    assert post.tags == ("Naughty ASMR",)
    assert post.embed == Embed(
        url="https://u.pcloud.link/publink/show?code=XZDlYb5ZlyjdRy0vl0bJWMbT2L2cp5RbUCFX",
        subject="ASMR ~ Girl Next Door ~ Patreon EXCLUSIVE.mp4 - Shared with pCloud",
        description="Store videos in pCloud. Share them with just the right people. Access them on any device. Create a free account now!",
    )
    assert post.has_full is False
    assert post.service == "patreon"
    assert post.user_id == "47101380"
    assert post.title == "ASMR ~ Girl Next Door ~ Patreon EXCLUSIVE"


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        (
            '{animation,"animation 2d",anime,"fan animation",fanart,fedorartt,"genshin impact"}',
            ["animation", "animation 2d", "anime", "fan animation", "fanart", "fedorartt", "genshin impact"],
        ),
        (
            'animation,"animation 2d",anime,"fan animation",fanart,fedorartt,"genshin impact"',
            ["animation", "animation 2d", "anime", "fan animation", "fanart", "fedorartt", "genshin impact"],
        ),
        (
            ["animation", "animation 2d", "anime", "fan animation", "fanart", "fedorartt", "genshin impact"],
            ["animation", "animation 2d", "anime", "fan animation", "fanart", "fedorartt", "genshin impact"],
        ),
        ("null", ()),
        (None, ()),
    ],
)
def test_tags_validation(tags: object, expected: list[str]) -> None:
    result = _parse_tags(tags)
    assert result == expected
