"""
EVA Assistant single-instance guard.
Copyright (c) 2026 Steve Dogs Studio.
"""

from __future__ import annotations

import atexit
import os
from pathlib import Path
from typing import TextIO


class SingleInstanceError(RuntimeError):
    """Raised when another EVA process already holds the instance lock."""


class SingleInstanceLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle: TextIO | None = None
        self._atexit_registered = False

    def acquire(self) -> None:
        if self._handle is not None:
            return

        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+", encoding="utf-8")

        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                if not handle.read(1):
                    handle.write("\n")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            handle.close()
            raise SingleInstanceError(f"EVA is already running and holds {self.path}.") from error

        handle.seek(0)
        handle.truncate()
        handle.write(f"{os.getpid()}\n")
        handle.flush()

        self._handle = handle
        if not self._atexit_registered:
            atexit.register(self.release)
            self._atexit_registered = True

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return

        try:
            handle.seek(0)
            handle.truncate()
            handle.flush()
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                handle.write("\n")
                handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            handle.close()
            self._handle = None


def acquire_single_instance_lock(path: Path) -> SingleInstanceLock:
    lock = SingleInstanceLock(path)
    lock.acquire()
    return lock
