import pytest
from bs4 import BeautifulSoup

from cyberdrop_dl.crawlers import bunkr
from cyberdrop_dl.url_objects import AbsoluteHttpURL


def test_album_parser() -> None:
    album_js = """
    window.albumFiles = [
        {
            id: 25960373,
            name: "f7e8625e-b50b-42c3-93da-d74bce716c41-md8f1c79417cd16004-zU4LIum1.jpg",
            original: "f7e8625e-b50b-42c3-93da-d74bce716c41-md8f1c79417cd16004.jpg",
            slug: "wWEoCddlaatjj",
            type: "image/jpeg",
            extension: "Image",
            size: 96818,
            timestamp: "10:49:48 27/11/2023",
            thumbnail: "https://static.scdn.st/e2f8a4c6-3d7b-4e19-9a5c-8b1d6f0e3a7c/thumbs/f7e8625e-b50b-42c3-93da-d74bce716c41-md8f1c79417cd16004-zU4LIum1.png",
            cdnEndpoint: "/f7e8625e-b50b-42c3-93da-d74bce716c41-md8f1c79417cd16004-zU4LIum1.jpg"
        },
        {
            id: 25960332,
            name: "c44e4c1a-90d5-4eba-8a58-f71fe3dfaa4f-md4d01c011ab729eda-ZEpjlipI.jpg",
            original: "2023-02-04 - Position 🔞 BONUS.mp4.jpg",
            slug: "tR69eocGrklcG",
            type: "image/jpeg",
            extension: "Image",
            size: 162649,
            timestamp: "10:48:13 27/11/2023",
            thumbnail: "https://static.scdn.st/f4e2d6c8-9b1a-4d3f-8e7c-5a6b2c9d0e1f/thumbs/c44e4c1a-90d5-4eba-8a58-f71fe3dfaa4f-md4d01c011ab729eda-ZEpjlipI.png",
            cdnEndpoint: "/c44e4c1a-90d5-4eba-8a58-f71fe3dfaa4f-md4d01c011ab729eda-ZEpjlipI.jpg"
        },
        {
            id: 25960333,
            name: "caec7e08-8e56-47ac-a4d6-8f2207609ae5-mdb527c6183d37d159-BTEPNkqS.jpg",
            original: "caec7e08-8e56-47ac-a4d6-8f2207609ae5-mdb527c6183d37d159.jpg",
            slug: "irJr4wL1eJBWh",
            type: "image/jpeg",
            extension: "Image",
            size: 110179,
            timestamp: "10:48:13 27/11/2023",
            thumbnail: "https://static.scdn.st/f4e2d6c8-9b1a-4d3f-8e7c-5a6b2c9d0e1f/thumbs/caec7e08-8e56-47ac-a4d6-8f2207609ae5-mdb527c6183d37d159-BTEPNkqS.png",
            cdnEndpoint: "/caec7e08-8e56-47ac-a4d6-8f2207609ae5-mdb527c6183d37d159-BTEPNkqS.jpg"
        },


    ];
    console.log('Album files embedded:', window.albumFiles.length, 'files');
    """
    files = {f.id: f for f in bunkr._make_album_parser()(album_js)}
    assert len(files) == 3
    file_id = 25960332
    file = files[file_id]
    assert file == bunkr.File(
        id=file_id,
        name="c44e4c1a-90d5-4eba-8a58-f71fe3dfaa4f-md4d01c011ab729eda-ZEpjlipI.jpg",
        original="2023-02-04 - Position 🔞 BONUS.mp4.jpg",
        slug="tR69eocGrklcG",
        type="image/jpeg",
        extension="Image",
        size=162649,
        timestamp="10:48:13 27/11/2023",
        thumbnail="https://static.scdn.st/f4e2d6c8-9b1a-4d3f-8e7c-5a6b2c9d0e1f/thumbs/c44e4c1a-90d5-4eba-8a58-f71fe3dfaa4f-md4d01c011ab729eda-ZEpjlipI.png",
        cdnEndpoint="/c44e4c1a-90d5-4eba-8a58-f71fe3dfaa4f-md4d01c011ab729eda-ZEpjlipI.jpg",
    )


@pytest.mark.parametrize(
    "host",
    [
        "cdn3.bunkr.ru",
        "cdn12.bunkr.ru",
        "cdn8.bunkr.ru",
    ],
)
def test_is_stream_redirect(host: str) -> None:
    assert bunkr._is_stream_redirect(host)


@pytest.mark.parametrize(
    "host",
    [
        "static.scdn.st",
        "bunkr.ru",
        "bunkrr.org",
        "mlk-bk.cdn.gigachad-cdn.ru",
    ],
)
def test_is_not_stream_redirect(host: str) -> None:
    assert not bunkr._is_stream_redirect(host)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://c5bu-b.cdn.cr/storage/media/--------------------------------------------------Yd6RpuQ8.mp4?token=2e5afd9aeb9c1&ex=1780065095&n=%E5%A5%BD%.mp4",
            "/--------------------------------------------------Yd6RpuQ8.mp4",
        ),
        (
            "https://kebab.bunkr.cr/12345-5670.mp4",
            "/12345-5670.mp4",
        ),
    ],
)
def test_db_path(url: str, expected: str) -> None:
    result = bunkr.BunkrCrawler.__db_path__(AbsoluteHttpURL(url))
    assert result == expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://static.scdn.st/c7a9b5d3-1e4f-a6d8-3b7e9f0c2a1d/thumbs/sylph_red_5000-jX9bl.jpg.png",
            "https://static.scdn.st/c7a9b5d3-1e4f-a6d8-3b7e9f0c2a1d/thumbs/sylph_red_5000-jX9bl.png",
        ),
        (
            "https://static.scdn.st/027e12ae-683b-4e42-950f-2b3f12448931/thumbs/bebc5872-a051-476c-8eef-a75739d6e082.zip.png",
            None,
        ),
        (
            "https://static.scdn.st/027e12ae-683b-4e42-950f-2b3f148931/thumbs/bad0a9-2aa4-4ae3-8739-bd5e31418a60.mp4_grid.png",
            "https://static.scdn.st/027e12ae-683b-4e42-950f-2b3f148931/thumbs/bad0a9-2aa4-4ae3-8739-bd5e31418a60.mp4_grid.png",
        ),
    ],
)
def test_fix_tumb(url: str, expected: str | None) -> None:
    result = bunkr._fix_thumb(AbsoluteHttpURL(url))
    thumb = AbsoluteHttpURL(expected) if expected else None
    assert result == thumb


@pytest.mark.parametrize(
    ("js_value", "expected"),
    [
        (
            r'"https:\/\/c4ta-b.cdn.cr\/storage\/media\/Tom-\u0026-Jerry-AbCd1234.mp4"',
            "https://c4ta-b.cdn.cr/storage/media/Tom-&-Jerry-AbCd1234.mp4",
        ),
        (
            r'"https:\/\/c3pz-b.cdn.cr\/storage\/media\/My-Friend\u0027s-Video-AbCd1234.mp4"',
            "https://c3pz-b.cdn.cr/storage/media/My-Friend's-Video-AbCd1234.mp4",
        ),
        (
            r'"https:\/\/c4ta-b.cdn.cr\/storage\/media\/plain-AbCd1234.mp4"',
            "https://c4ta-b.cdn.cr/storage/media/plain-AbCd1234.mp4",
        ),
        (r"'https:\/\/x.cr\/a.mp4'", "https://x.cr/a.mp4"),
        ("123", "123"),
    ],
)
def test_extract_js_vars(js_value: str, expected: str) -> None:
    soup = BeautifulSoup(f"<script>var jsCDN = {js_value};</script>", "html.parser")
    assert bunkr._extract_js_vars(soup)["jsCDN"] == expected
