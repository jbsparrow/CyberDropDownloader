# ruff : noqa: T201

from __future__ import annotations

import contextlib
import cProfile
import os
import pstats
import shutil
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

from cyberdrop_dl import constants, env

if TYPE_CHECKING:
    from collections.abc import Callable


def profile(func: Callable, ask: bool) -> None:
    @contextmanager
    def temp_dir_context():
        with TemporaryDirectory() as temp_dir:
            profile = setup_profile(temp_dir)
            try:
                yield
            finally:
                destroy_profile(*profile)
                if ask:
                    input("Press any key to finish and delete the profile folder: ")

    with temp_dir_context(), cProfile.Profile() as cdl_profile:
        with contextlib.suppress(SystemExit):
            func()

    print("Generating profile report..")
    results = pstats.Stats(cdl_profile)
    results.sort_stats(pstats.SortKey.TIME)
    results.dump_stats(filename="cyberdrop_dl.profiling")
    print("DONE!")


def setup_profile(temp_dir: Path | str) -> tuple[Path, Path]:
    old_cwd = Path.cwd()
    temp_dir_path = Path(temp_dir).resolve()
    cookies_dir = old_cwd / "AppData/Cookies"
    if cookies_dir.is_dir():
        temp_cookies_dir = temp_dir_path / "AppData/Cookies"
        temp_cookies_dir.mkdir(parents=True, exist_ok=True)
        for cookie_file in cookies_dir.glob("*.txt"):
            shutil.copy(cookie_file, temp_cookies_dir)

    os.chdir(temp_dir_path)
    print(f"Using {temp_dir_path} as temp AppData dir")
    env.DEBUG_LOG_FOLDER = temp_dir_path
    return old_cwd, temp_dir_path


def destroy_profile(old_cwd: Path, temp_dir_path: Path) -> None:
    os.chdir(old_cwd)
    new_log_file = None
    old_log_file = next(temp_dir_path.glob("cyberdrop_dl_debug*"), None)
    if old_log_file and old_log_file.is_file():
        suffix = "_profiling"
        if env.PROFILING == "use_date":
            suffix += f"_{constants.STARTUP_TIME.strftime(constants.LOGS_DATETIME_FORMAT)}"

        new_log_file = Path(f"cyberdrop_dl_debug{suffix}.log").resolve()
        shutil.move(old_log_file, new_log_file)
    print(f"Profile AppData folder: {temp_dir_path}")
    print(f"Debug log file: {new_log_file}")
