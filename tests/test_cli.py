from pathlib import Path

import pytest

from cyberdrop_dl.main import run


@pytest.mark.parametrize(
    "command, text",
    [
        ("--help", "Bulk asynchronous downloader for multiple file hosts"),
        ("--show-supported-sites", "for a details about supported paths"),
    ],
)
def test_command_by_console_output(tmp_cwd: Path, capsys: pytest.CaptureFixture[str], command: str, text: str) -> None:
    try:
        run(tuple(command.split()))
    except SystemExit:
        pass
    captured = capsys.readouterr()
    output = captured.out
    assert text in output
