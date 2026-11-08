"""Fail-closed reader for externally pinned recovery bundles.

The module is transport-neutral.

A reader must implement:

    open_object(key) -> context manager of a binary stream

The module verifies a separately supplied SHA-256 digest.
It does not establish trust in that digest or authorize
production operations.

No cloud SDK, credentials, or network calls are included.
"""

import hashlib
import hmac
import os
from pathlib import Path
import re
import tempfile


CHUNK_SIZE = 1024 * 1024

SHA256_PATTERN = re.compile(
    r"[0-9a-f]{64}",
    re.ASCII,
)


def _validate_sha256(value):
    """Accept only canonical lowercase SHA-256 hex strings."""
    if (
        not isinstance(value, str)
        or SHA256_PATTERN.fullmatch(value) is None
    ):
        raise ValueError(
            "Invalid expected SHA-256 digest"
        )

    return value


def _validate_object_key(key, digest):
    """Accept exactly the requested content-addressed key."""
    expected_key = f"sha256/{digest}.zip"

    if (
        not isinstance(key, str)
        or key != expected_key
    ):
        raise ValueError(
            "Remote object key does not match pinned SHA-256"
        )

    return key


def _validate_max_bytes(value):
    """Require a positive, explicit download size limit."""
    if type(value) is not int or value <= 0:
        raise ValueError(
            "max_bytes must be a positive integer"
        )

    return value


def _check_destination_parents(path):
    """Reject symlinked destination ancestors."""
    parent = Path(path).parent

    for ancestor in (parent, *parent.parents):
        if ancestor.is_symlink():
            raise ValueError(
                "Symlinked destination parent is forbidden"
            )

        if ancestor.exists() and not ancestor.is_dir():
            raise ValueError(
                "Destination parent is not a directory"
            )


def _reject_existing_target(path):
    """Never replace an existing file, directory or symlink."""
    path = Path(path)

    if path.exists() or path.is_symlink():
        raise FileExistsError(
            f"Download destination already exists: {path}"
        )


def fetch_pinned_remote_bundle(
    *,
    reader,
    object_key,
    expected_sha256,
    output_path,
    max_bytes,
) -> Path:
    """Download an externally pinned object to a new file.

    Invariants:
    - Exact sha256/<digest>.zip address required.
    - No remote read on invalid inputs or existing output.
    - Download size is bounded.
    - Streaming SHA-256 is checked before publication.
    - Failed downloads leave no published output.
    - Publication is exclusive and non-overwriting.

    A successful return confirms byte integrity only.
    The portable recovery trust chain must still validate
    the downloaded archive independently.
    """

    digest = _validate_sha256(
        expected_sha256
    )

    key = _validate_object_key(
        object_key,
        digest,
    )

    limit = _validate_max_bytes(
        max_bytes
    )

    target = Path(output_path)

    # Before touching the remote source, validate the
    # destination and refuse any overwrite.
    _check_destination_parents(target)
    _reject_existing_target(target)

    if not callable(
        getattr(reader, "open_object", None)
    ):
        raise ValueError(
            "Remote reader must expose open_object(key)"
        )

    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    _check_destination_parents(target)
    _reject_existing_target(target)

    # The temporary file resides on the destination
    # filesystem, allowing exclusive hard-link publication.
    fd, temporary_name = tempfile.mkstemp(
        prefix=".remote-recovery-fetch-",
        dir=target.parent,
    )

    staging = Path(temporary_name)

    try:
        downloaded = 0
        hasher = hashlib.sha256()

        # The supplied reader owns the transport.
        # The returned stream is a context manager.
        with os.fdopen(fd, "wb") as output:
            with reader.open_object(key) as stream:
                while True:

                    # Read at most one byte beyond the
                    # remaining limit to detect overflow.
                    remaining = limit - downloaded

                    read_size = min(
                        CHUNK_SIZE,
                        remaining + 1,
                    )

                    chunk = stream.read(read_size)

                    if chunk == b"":
                        break

                    if not isinstance(
                        chunk,
                        (bytes, bytearray),
                    ):
                        raise ValueError(
                            "Remote stream returned nonbinary data"
                        )

                    if len(chunk) > read_size:
                        raise ValueError(
                            "Remote stream exceeded requested read size"
                        )

                    downloaded += len(chunk)

                    if downloaded > limit:
                        raise ValueError(
                            "Remote bundle exceeds max_bytes"
                        )

                    hasher.update(chunk)
                    output.write(chunk)

            output.flush()
            os.fsync(output.fileno())

        actual_digest = hasher.hexdigest()

        if not hmac.compare_digest(
            actual_digest,
            digest,
        ):
            raise ValueError(
                "Downloaded bundle SHA-256 mismatch"
            )

        # Recheck the publication destination.
        # Another process may have created it meanwhile.
        _check_destination_parents(target)
        _reject_existing_target(target)

        # Atomic creation of the published file.
        # os.link refuses to replace an existing target.
        os.link(staging, target)

        return target

    finally:
        # Successful and unsuccessful paths both remove
        # the unpublished staging filename.
        staging.unlink(missing_ok=True)
