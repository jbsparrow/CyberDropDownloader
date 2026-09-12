from __future__ import annotations

import platform
import sys
from pathlib import Path
from typing import Any

import pytest

from cyberdrop_dl.exceptions import InvalidExtensionError, NoExtensionError
from cyberdrop_dl.filepath import get_filename_and_ext
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import file_browser, operators, text_editor
from cyberdrop_dl.utils._url import fix_multi_slashes, matches_any_host, parse_http_url


class TestGetFilenameAndExt:
    _file = Path("Cyberdrop-DL.v8.4.0.zip")

    def _ext(self, *args: Any, **kwargs: Any) -> str:
        return get_filename_and_ext(*args, **kwargs)[1]

    def _name(self, *args: Any, **kwargs: Any) -> str:
        return get_filename_and_ext(*args, **kwargs)[0]

    def test_ext_should_always_be_lowercase(self) -> None:
        exts = [self._ext(self._file.with_suffix(ext).name) for ext in (".zip", ".Zip", ".zIP", ".ziP")]
        assert exts == [".zip"] * len(exts)

    def test_ext_should_not_include_multiple_suffixes(self) -> None:
        file = self._file.name + ".rar"
        assert self._ext(file) == ".rar"

    @pytest.mark.parametrize(
        ("name", "mimetype", "expected_ext"),
        [
            ("archive", "application/zip", ".zip"),
            ("Katalina Kyle, Savanah Storm - What If She Hears Us!", "video/mp4", ".mp4"),
        ],
    )
    def test_mime_type_fallback(self, name: str, mimetype: str, expected_ext: str) -> None:
        filename, ext = get_filename_and_ext(name, mime_type=mimetype)
        assert ext == expected_ext
        assert filename == name + expected_ext

    @pytest.mark.skipif(platform.system() in {"Windows", "Darwin"}, reason="Emojis are stripped on Windows and MacOS")
    @pytest.mark.parametrize(
        ("name", "expected_name", "expected_ext"),
        [
            ("Vídeo de verificación [uvfdtpm4c2a]/video.MP4", "Vídeo de verificación [uvfdtpm4c2a]-video.mp4", ".mp4"),
            (
                "Katalina Kyle, Savanah Storm - “What If She Hears Us! 🍕”.mp4",
                "Katalina Kyle, Savanah Storm - “What If She Hears Us! 🍕”.mp4",
                ".mp4",
            ),
        ],
    )
    def test_complex_name(self, name: str, expected_name: str, expected_ext: str) -> None:
        name, ext = get_filename_and_ext(name)
        assert ext == expected_ext
        assert name == expected_name

    @pytest.mark.parametrize(
        "mime_type",
        [
            "application/zip",
            "application/pdf",
            "image/png",
            "video/mp4",
            "text/plain",
            "application/json",
            "image/jpeg",
        ],
    )
    def test_mime_type_should_be_ignore_if_the_file_has_a_valid_ext(self, mime_type: str) -> None:
        filename, ext = get_filename_and_ext(self._file.name, mime_type=mime_type)
        assert ext == self._file.suffix
        assert filename == self._file.name

    @pytest.mark.parametrize(
        ("name", "expected_name", "expected_ext"),
        [
            ("img_3763-webp.6091490", "img_3763.webp", ".webp"),
            ("1-gif.5021643", "1.gif", ".gif"),
        ],
    )
    def test_forum_filename(self, name: str, expected_name: str, expected_ext: str) -> None:
        name, ext = get_filename_and_ext(name, xenforo=True)
        assert ext == expected_ext
        assert name == expected_name

    def test_long_extension_should_raise_invalid_ext_error(self) -> None:
        with pytest.raises(InvalidExtensionError):
            get_filename_and_ext("video.abcdef")

    def test_no_extension_should_raise_no_ext_error(self) -> None:
        with pytest.raises(NoExtensionError):
            get_filename_and_ext("README")


@pytest.mark.parametrize(
    "url",
    [
        "http:/s",
        "https://google",
        "/path/to/file",
        "file",
        "/example.com/file",
    ],
)
def test_parsing_invalid_url(url: str) -> None:
    with pytest.raises(ValueError, match="URL"):
        parse_http_url(url)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http:////google.com", "http://google.com"),
        ("https://////google.com", "https://google.com"),
        ("http:/google.com", "http:/google.com"),
        ("//google.com", "//google.com"),
        ("/google.com", "/google.com"),
        ("https://example.com////bar", "https://example.com////bar"),
    ],
)
def test_fix_multi_slashes(url: str, expected: str) -> None:
    assert fix_multi_slashes(url) == expected


@pytest.mark.parametrize(
    ("url", "origin", "trim", "expected"),
    [
        ("http://localhost", None, False, "http://localhost/"),
        ("https://////example.com/file//a//b/", None, False, "https://example.com/file//a//b/"),
        ("https://////example.com/file//a//b/", None, True, "https://example.com/file//a//b"),
        ("https://////example.com/file/", None, True, "https://example.com/file"),
        ("https://example.com/file/video.mp4?a=1+b=2", None, True, "https://example.com/file/video.mp4?a=1 b%3D2"),
        (
            "https://example.com/video/file/%E6%92%AE%E5%BD%B1%E4%BC%9A",
            None,
            False,
            "https://example.com/video/file/撮影会",
        ),
        ("//example.com/file", "https://example.net", False, "https://example.com/file"),
        ("example.com/file", "https://example.net", False, "https://example.net/example.com/file"),
        ("/example.com/file", "https://example.net", False, "https://example.net/example.com/file"),
    ],
)
def test_parse_http(url: str, origin: str | None, expected: str, *, trim: bool) -> None:
    result = parse_http_url(url, AbsoluteHttpURL(origin) if origin else None, trim=trim)
    assert result.human_repr() == expected


class TestTextEditor:
    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only test")
    def test_win_default(self, tmp_cwd: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("EDITOR", raising=False)
        cmd = text_editor._find_win_editor()
        assert cmd == text_editor._editor_cmd()
        assert cmd == ("C:\\Windows\\system32\\notepad.exe",)
        np = tmp_cwd / "notepad++.exe"
        np.write_text("test")
        cmd = text_editor._find_win_editor()
        assert cmd
        assert cmd[1:] == (
            "-multiInst",
            "-noPlugin",
            "-notabbar",
            "-nosession",
        )

    @pytest.mark.skipif(sys.platform != "darwin", reason="MAC OS test only")
    def test_mac_os_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("EDITOR", raising=False)
        cmd = text_editor._editor_cmd()
        assert cmd
        assert cmd == ("open", "-t", "-n", "-W")
        assert type(cmd[0]) is text_editor.OSDefaultCMD

    @pytest.mark.skipif(sys.platform in ("darwin", "win32"), reason="Linux test only")
    def test_unix_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("EDITOR", raising=False)
        cmd = text_editor._find_unix_editor()
        assert cmd
        assert cmd == text_editor._editor_cmd()


def test_operators_nested_itemgetter() -> None:
    data = {}

    get = operators.nested_itemgetter("a", "b")
    with pytest.raises(KeyError, match=r"['a']"):
        get(data)

    data = {
        "a": 1,
        "c": 2,
    }

    with pytest.raises(KeyError, match=r"['a', 'b']"):
        get(data)

    data = {
        "a": {
            "b": 1,
        },
        "c": 2,
    }

    assert get(data) == 1


def test_operators_nested_itemsetter() -> None:
    data = {}

    update = operators.nested_itemsetter("a", "b")
    update(data, 2)

    assert data == {"a": {"b": 2}}


def test_file_browser() -> None:
    match platform.system():
        case "Windows":
            expected = ("windows-default",)
        case "Darwin":
            expected = ("macos-default",)
        case _:
            return

    browsers = tuple(f.name for f in file_browser.get_file_browsers())
    assert browsers == expected


@pytest.mark.parametrize(
    ("url", "hosts", "expected"),
    [
        ("https://x.com", {"x.com"}, True),
        ("https://x.com", {"http://x.com"}, True),
        ("https://x.com", {"https://x.com"}, True),
        ("https://vix.com", {"x.com"}, True),
        ("https://vix.com", {"https://x.com"}, False),
    ],
)
def test_matches_any_host(url: str, hosts: tuple[str, ...], *, expected: bool) -> None:
    assert matches_any_host(AbsoluteHttpURL(url), hosts) is expected
