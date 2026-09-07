from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable, Sequence

    from cyberdrop_dl.utils.markdown import Row


def _unpack(data: Iterable[tuple[str, Any]]) -> Generator[tuple[str, str]]:
    for name, value in sorted(data, key=lambda x: str(x[0]).casefold()):
        yield name, str(value)


def _table(title: str | None, headers: Sequence[str], rows: Iterable[Row]) -> str:
    from cyberdrop_dl.utils.markdown import markdown_table

    title = f"## {title}\n\n" if title else ""
    return title + markdown_table(headers, *rows) + "\n"


def generate_report() -> str:
    from cyberdrop_dl import __version__, dependencies, ffmpeg
    from cyberdrop_dl.__main__ import __file__ as entrypoint
    from cyberdrop_dl.config.appdata import AppData
    from cyberdrop_dl.utils import get_system_information

    return "\n".join(
        [
            "\n# System Report\n",
            _table(
                "",
                ["Program", "Version", "Location"],
                [
                    ("cyberdrop-dl", __version__, str(entrypoint)),
                    ("ffmpeg", str(ffmpeg.version()), str(ffmpeg.which_ffmpeg())),
                    ("ffprobe", str(ffmpeg.ffprobe_version()), str(ffmpeg.which_ffprobe())),
                ],
            ),
            _table(
                "System",
                ["Name", "Value"],
                _unpack(get_system_information().items()),
            ),
            _table(
                "AppData",
                ["Name", "Default location"],
                _unpack(AppData.default()),
            ),
            _table(
                "Dependencies",
                ["Package", "Version"],
                _unpack(dependencies()),
            ),
        ]
    )


if __name__ == "__main__":
    print(generate_report())  # noqa: T201
