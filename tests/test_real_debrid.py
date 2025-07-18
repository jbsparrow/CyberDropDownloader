import pytest

from cyberdrop_dl.crawlers import realdebrid
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL


@pytest.mark.parametrize(
    "input_url_str, expected_url_str",
    [
        (
            "https://dropbox.com/video/my_video.mp4?rlkey=1234&download=1",
            "https://dropbox.com/video/my_video.mp4?rlkey=1234&download=1",
        ),
        (
            "https://real-debrid.com/dropbox.com/video/my_video.mp4/query/rlkey/1234/download/1",
            "https://dropbox.com/video/my_video.mp4?rlkey=1234&download=1",
        ),
        (
            "https://download.real-debrid.com/dropbox.com/video.mp4",
            "https://download.real-debrid.com/dropbox.com/video.mp4",
        ),
        (
            "https://real-debrid.com/rapidgator.net/video/my_video.mp4",
            "https://rapidgator.net/video/my_video.mp4",
        ),
        (
            "https://real-debrid.com/rapidgator.net/folder/4273255/Movie.html/query/sort/name.desc/page/52",
            "https://rapidgator.net/folder/4273255/Movie.html?sort=name.desc&page=52",
        ),
        (
            "https://real-debrid.com/rapidgator.net/folder/X1/query/sort_by/date/before/2025/frag/new",
            "https://rapidgator.net/folder/X1?sort_by=date&before=2025#new",
        ),
        (
            "https://real-debrid.com/docs.google.com/document/d/{file_id}/export/query/format/docx",
            "https://docs.google.com/document/d/{file_id}/export?format=docx",
        ),
        (
            "https://real-debrid.com/rapidgator.net/long/path/with/many/segments/query/foo/bar/baz/qux/frag/fragment",
            "https://rapidgator.net/long/path/with/many/segments?foo=bar&baz=qux#fragment",
        ),
        (
            "https://real-debrid.com/www.4shared.com/file/obY8DADjmm/LINE_MOVIE_1543474783049mp4.html",
            "https://www.4shared.com/file/obY8DADjmm/LINE_MOVIE_1543474783049mp4.html",
        ),
        (
            "https://real-debrid.com/katfile.com/f/ybeixmixf9qk7jq976ig4j507ansl2ts",
            "https://katfile.com/f/ybeixmixf9qk7jq976ig4j507ansl2ts",
        ),
        (
            # URL with duplicated query params
            "https://real-debrid.com/dropbox.com/video/my_video.mp4/query/rlkey/1234/download/1/download/2",
            "https://dropbox.com/video/my_video.mp4?rlkey=1234&download=1&download=2",
        ),
    ],
)
def test_decode_original_url(input_url_str: str, expected_url_str: str) -> None:
    input_url = AbsoluteHttpURL(input_url_str)
    expected_url = AbsoluteHttpURL(expected_url_str)
    decoded_url = realdebrid._reconstruct_original_url(input_url)
    assert decoded_url == expected_url


@pytest.mark.parametrize(
    "input_url_str, expected_url_str",
    [
        (
            "https://rapidgator.net/folder/5273235/Movie.html?sort=name.desc&page=52",
            "https://real-debrid.com/rapidgator.net/folder/5273235/Movie.html/query/sort/name.desc/page/52",
        ),
        (
            "https://alfafile.net/file/AYUx3e",
            "https://real-debrid.com/alfafile.net/file/AYUx3e",
        ),
        (
            "https://rapidgator.net/file/44699b531585433b7e232d5be6a50547a/video.mp4.html",
            "https://real-debrid.com/rapidgator.net/file/44699b531585433b7e232d5be6a50547a/video.mp4.html",
        ),
        (
            "https://mega.nz/#!Ue5VRSIQ!kC2E4a4JwfWWCWYNJovGFHlbz8G",
            "https://real-debrid.com/mega.nz/frag/!Ue5VRSIQ!kC2E4a4JwfWWCWYNJovGFHlbz8G",
        ),
        (
            "https://mega.nz/folder/oZZxyBrY#oU4jASLPpJVvqGHJIMRcgQ/file/IYZABDGY",
            "https://real-debrid.com/mega.nz/folder/oZZxyBrY/frag/oU4jASLPpJVvqGHJIMRcgQ/file/IYZABDGY",
        ),
        (
            "https://mega.nz/file/cH51DYDR#qH7QOfRcM-7N9riZWdSjsRq",
            "https://real-debrid.com/mega.nz/file/cH51DYDR/frag/qH7QOfRcM-7N9riZWdSjsRq",
        ),
        (
            "https://dropbox.com/video/my_video.mp4?rlkey=1234&download=1",
            "https://real-debrid.com/dropbox.com/video/my_video.mp4/query/rlkey/1234/download/1",
        ),
        (
            # URL with duplicated query params
            "https://dropbox.com/video/my_video.mp4?rlkey=1234&download=1&download=2",
            "https://real-debrid.com/dropbox.com/video/my_video.mp4/query/rlkey/1234/download/1/download/2",
        ),
    ],
)
def test_encode_url(input_url_str: str, expected_url_str: str) -> None:
    input_url = AbsoluteHttpURL(input_url_str)
    expected_url = AbsoluteHttpURL(expected_url_str)
    encoded_url = realdebrid._flatten_url(input_url, input_url.host)
    assert encoded_url == expected_url
