import os
from hashlib import sha256

RUNNING_IN_IDE = os.getenv("PYCHARM_HOSTED") or os.getenv("TERM_PROGRAM") == "vscode"
KEY = os.getenv("ENABLESIMPCITY")
if KEY:
    KEY = sha256(KEY.encode("utf-8")).hexdigest()

DEBUG_LOG_FILE_FOLDER = os.getenv("CDL_DEBUG_LOG_FILE_FOLDER")
PROFILING = os.getenv("CDL_PROFILING")
DEBUG_VAR = RUNNING_IN_IDE or DEBUG_LOG_FILE_FOLDER or PROFILING
