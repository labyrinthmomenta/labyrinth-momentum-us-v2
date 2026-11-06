"""Exclusive process lock for US daily ingestion."""

from contextlib import contextmanager
import errno
import fcntl
import os
from pathlib import Path
from typing import Iterator


class DailyRunAlreadyActiveError(RuntimeError):
    """Another ingestion process already owns the database lock."""


@contextmanager
def hold_daily_ingestion_lock(
    db_path: str | Path,
) -> Iterator[Path]:
    """Hold a non-blocking exclusive lock for one SQLite database.

    The lock file is intentionally retained after release.
    OS-managed locks are released when the descriptor closes,
    including after normal process termination.

    All participating ingestion processes must use this lock.
    """
    database = Path(db_path)

    if not database.is_file():
        raise FileNotFoundError(database)

    # Resolve relative paths and symlinks to identify
    # the same database consistently.
    lock_path = Path(
        str(database.resolve()) + ".daily.lock"
    )

    flags = os.O_RDWR | os.O_CREAT

    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC

    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    fd = os.open(lock_path, flags, 0o600)

    try:
        try:
            fcntl.flock(
                fd,
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except OSError as exc:
            if exc.errno in {
                errno.EACCES,
                errno.EAGAIN,
                errno.EWOULDBLOCK,
            }:
                raise DailyRunAlreadyActiveError(
                    "Another daily ingestion run is active "
                    f"for database: {database}"
                ) from exc
            raise

        try:
            yield lock_path
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)

    finally:
        os.close(fd)
