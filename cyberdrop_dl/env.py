from __future__ import annotations

import hashlib
import os
import sys

ALL_VARS: dict[str, str | None] = {}
os.environ["PYDANTIC_ERRORS_INCLUDE_URL"] = "0"


def _env(name: str, *, censor: bool = False) -> str | None:
    full_name = "CDL_" + name
    value = os.getenv(full_name)
    if censor and value:
        value = hashlib.sha256(value.encode("utf-8")).hexdigest()
    ALL_VARS[full_name] = value
    return value


def _cast_bool(value: bool | str | None) -> bool:  # noqa: FBT001
    if not value:
        return False

    if value is True:
        return value

    return value.casefold() not in {"no", "0", "false"}


RUNNING_IN_TERMUX = _cast_bool(os.getenv("TERMUX_VERSION") or "com.termux" in os.getenv("PREFIX", sys.prefix))
FORCE_PORTRAIT_MODE = _cast_bool(_env("PORTRAIT_MODE") or RUNNING_IN_TERMUX)
DEBUG_LOG_FOLDER = _env("DEBUG_LOG_FOLDER")
MAX_LOG_MSG_LENGTH = int(_env("MAX_LOG_MSG_LENGTH") or 0) or 5_000
DEBUG_MODE = _cast_bool(
    _env("DEBUG_MODE")
    or DEBUG_LOG_FOLDER
    or os.getenv("PYCHARM_HOSTED")
    or os.getenv("TERM_PROGRAM") in {"vscode", "zed"}
    or "pytest" in sys.modules
)
ENABLE_DEBUG_CRAWLERS = (
    _env("ENABLE_DEBUG_CRAWLERS", censor=True) == "d396ab8c85fcb1fecd22c8d9b58acf944a44e6d35014e9dd39e42c9a64091eda"
)

APPDATA_FOLDER = _env("APPDATA_FOLDER")
WRITE_JSON_UI = int(_env("WRITE_JSON_UI") or 0) or None
FFMPEG_FIX_HLS = _cast_bool(_env("FFMPEG_FIX_HLS"))
EDITOR = os.getenv("EDITOR")
CI = _cast_bool(os.getenv("CI"))
TERMUX = {
    k.removeprefix("TERMUX_APP_").removeprefix("TERMUX_").lstrip("_"): v
    for k, v in os.environ.items()
    if k.startswith("TERMUX_")
}


# CRAWLERS

FILEDITCH_WAIT = int(_env("FILEDITCH_WAIT") or 20)
GOFILE_SALT = _env("GOFILE_SALT")
TWITTER_MAX_EMPTY_PAGES = int(_env("TWITTER_MAX_EMPTY_PAGES") or 10)

ALL_VARS = dict(sorted(ALL_VARS.items()))  # pyright: ignore[reportConstantRedefinition]
ALL_VARS_RESOLVED = dict(
    sorted((k, v) for k, v in globals().items() if k != "ALL_VARS" and not k.startswith("_") and k.upper() == k)
)
