import os
from hashlib import sha256

os.environ["PYDANTIC_ERRORS_INCLUDE_URL"] = "0"
RUNNING_IN_IDE = bool(os.getenv("PYCHARM_HOSTED") or os.getenv("TERM_PROGRAM") == "vscode")
RUNNING_IN_TERMUX = bool(
    os.getenv("TERMUX_VERSION") or os.getenv("TERMUX_MAIN_PACKAGE_FORMAT") or "com.termux" in os.getenv("$PREFIX", "")
)
PORTRAIT_MODE = bool(RUNNING_IN_TERMUX or os.getenv("CDL_PORTRAIT_MODE"))
ENABLE_DEBUG_CRAWLERS = os.getenv("CDL_ENABLE_DEBUG_CRAWLERS")
if ENABLE_DEBUG_CRAWLERS:
    ENABLE_DEBUG_CRAWLERS = sha256(ENABLE_DEBUG_CRAWLERS.encode("utf-8")).hexdigest()

DEBUG_LOG_FOLDER = os.getenv("CDL_DEBUG_LOG_FOLDER")
PROFILING = os.getenv("CDL_PROFILING")
MAX_CRAWLER_ERRORS = int(os.getenv("CDL_MAX_CRAWLER_ERRORS") or 10)
DEBUG_VAR = RUNNING_IN_IDE or DEBUG_LOG_FOLDER or PROFILING
