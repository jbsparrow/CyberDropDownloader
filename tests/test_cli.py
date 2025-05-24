from pathlib import Path

import pytest

from cyberdrop_dl.main import run


def test_help(tmp_cwd: Path, capsys: pytest.CaptureFixture[str]) -> None:
    try:
        run(("--help",))
    except SystemExit:
        pass
    captured = capsys.readouterr()
    output = captured.out
    assert "Bulk asynchronous downloader for multiple file hosts" in output
