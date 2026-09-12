from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cyberdrop_dl.__main__ import run_cdl
from cyberdrop_dl.config import Config
from cyberdrop_dl.config.appdata import AppData, AppDirs
from cyberdrop_dl.crawlers import SKIP_DOWNLOAD

if TYPE_CHECKING:
    from collections.abc import Generator

KEYS = (
    "url",
    "filename",
    "debrid_url",
    "original_filename",
    "referer",
    "album_id",
    "uploaded_at",
    "download_folder",
    "thumbnail",
)
ROOT = Path(__file__).resolve().parents[2]
TEST_FOLDER = ROOT / "tests/crawlers/test_cases"

TestCase = dict[str, Any]


def parse_jsonl(file: Path) -> Generator[tuple[str, str, TestCase]]:
    base = Path.cwd() / Config().download_folder
    for line in file.read_text(encoding="utf-8").splitlines():
        media = json.loads(line)
        if media["url"].startswith("metadata:"):
            continue
        url = media["parents"][0] if media["parents"] else media["referer"]
        media["download_folder"] = "re:" + str(Path(media["download_folder"]).relative_to(base))
        yield media["domain"], url, {key: media[key] for key in KEYS}


def run(url_txt: Path, main_log: Path) -> None:
    with tempfile.TemporaryDirectory() as temp:
        appdata = AppData.from_dirs(AppDirs.from_path(Path(temp) / "test_appdata"))
        appdata.config_file.parent.mkdir(parents=True, exist_ok=True)
        appdata.config_file.touch()
        appdata.db_file.touch()
        _ = SKIP_DOWNLOAD.set(True)
        _ = run_cdl(
            [
                "download",
                "--database-file",
                str(appdata.db_file),
                "--config-file",
                str(appdata.config_file),
                "--cookies",
                "cookies.txt",
                "--input-file",
                str(url_txt),
                "--log-file",
                str(main_log),
                "--flaresolverr",
                "http://localhost:8191",
                "--no-flaresolverr-use-session",
                "--flaresolverr-concurrency",
                "3",
                "--dump-json",
                "--ui",
                "simple",
            ]
        )


def create_test_files(file: Path) -> None:
    all_results: dict[str, dict[str, list[TestCase]]] = {}
    if not file.exists():
        return
    for domain, url, results in parse_jsonl(file):
        site_tests = all_results.setdefault(domain, {})
        site_tests.setdefault(url, []).append(results)

    test_files: list[Path] = []
    for domain, cases in all_results.items():
        test_cases = [
            {
                "url": url,
                "results": results,
                "count": len(results),
            }
            for url, results in cases.items()
        ]
        test_file = TEST_FOLDER / f"test_case_{domain.replace('.', '_')}.py"
        _ = test_file.write_text(f"DOMAIN = {domain!r}\nTEST_CASES = {test_cases}")
        test_files.append(test_file)

    if test_files:
        _ = subprocess.run(["ruff", "format", *test_files], check=False)


if __name__ == "__main__":
    main_log, url_txt = [Path(file).resolve() for file in (*sys.argv[1:], "test_run.log", "URLs.txt")[:2]]
    run(url_txt, main_log)
    json_l = main_log.with_suffix(".results.jsonl")
    create_test_files(json_l)
