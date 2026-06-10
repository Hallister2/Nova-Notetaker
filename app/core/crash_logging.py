from __future__ import annotations

import faulthandler
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import TextIO


from app.core.settings import LOGS_DIR

_FAULT_LOG: TextIO | None = None


def _runtime_log_path() -> Path:
    return LOGS_DIR / f"runtime-{datetime.now():%Y-%m-%d}.log"


def write_runtime_log(message: str) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _runtime_log_path().open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message}\n")




def install_crash_logging() -> None:
    global _FAULT_LOG

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    if _FAULT_LOG is None or _FAULT_LOG.closed:
        fault_path = LOGS_DIR / f"crash-{datetime.now():%Y-%m-%d_%H%M%S}.log"
        _FAULT_LOG = fault_path.open("a", encoding="utf-8")
        faulthandler.enable(file=_FAULT_LOG, all_threads=True)
        write_runtime_log(f"Crash diagnostics enabled: {fault_path}")

    previous_excepthook = sys.excepthook
    previous_threading_excepthook = threading.excepthook

    def excepthook(exc_type, exc_value, exc_traceback) -> None:
        write_runtime_log("Unhandled exception:\n" + "".join(traceback.format_exception(exc_type, exc_value, exc_traceback)))
        previous_excepthook(exc_type, exc_value, exc_traceback)

    def threading_excepthook(args: threading.ExceptHookArgs) -> None:
        write_runtime_log(
            "Unhandled thread exception:\n"
            + "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
        )
        previous_threading_excepthook(args)

    sys.excepthook = excepthook
    threading.excepthook = threading_excepthook
