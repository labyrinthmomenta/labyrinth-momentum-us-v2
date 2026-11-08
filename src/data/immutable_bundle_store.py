"""Content-addressed storage for offline recovery bundles.

This module only stores and retrieves bytes. It does not
authorize market-data ingestion, recovery trust, scheduling,
or production publication.

The local filesystem store enforces non-overwriting writes,
not operating-system-level permanent immutability.
"""

import hashlib
import hmac
import os
from pathlib import Path
import re
import tempfile


SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
CHUNK_SIZE = 1024 * 1024


def _validated_digest(value):
    if (
        not isinstance(value, str)
        or SHA256_PATTERN.fullmatch(value) is None
    ):
        raise ValueError("Invalid SHA-256 content address")

    return value


def _sha256_file(path):
    digest = hashlib.sha256()

    with Path(path).open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(CHUNK_SIZE),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _check_regular_file(path, label):
    path = Path(path)

    if path.is_symlink() or not path.is_file():
        raise ValueError(
            f"Missing or unsafe {label}: {path}"
        )

    return path


def _check_store_paths(root):
    """Reject symlinked storage root and namespace."""
    root = Path(root)
    namespace = root / "sha256"

    if root.is_symlink() or namespace.is_symlink():
        raise ValueError(
            "Symlinked object store directories are forbidden"
        )

    if root.exists() and not root.is_dir():
        raise ValueError(
            "Object store root is not a directory"
        )

    if namespace.exists() and not namespace.is_dir():
        raise ValueError(
            "Object store namespace is not a directory"
        )

    return namespace


def _copy_to_staging(
    *,
    source,
    destination_parent,
    prefix,
    expected_sha256,
):
    """Stream a copy to a private file and verify its bytes."""
    fd, name = tempfile.mkstemp(
        prefix=prefix,
        dir=destination_parent,
    )

    staging = Path(name)

    try:
        digest = hashlib.sha256()

        with Path(source).open("rb") as input_stream:
            with os.fdopen(fd, "wb") as output_stream:
                for chunk in iter(
                    lambda: input_stream.read(CHUNK_SIZE),
                    b"",
                ):
                    digest.update(chunk)
                    output_stream.write(chunk)

                output_stream.flush()
                os.fsync(output_stream.fileno())

        if not hmac.compare_digest(
            digest.hexdigest(),
            expected_sha256,
        ):
            raise ValueError(
                "Copied bundle SHA-256 mismatch"
            )

        return staging

    except BaseException:
        staging.unlink(missing_ok=True)
        raise


def publish_immutable_bundle(
    *,
    source_bundle,
    store_root,
    expected_sha256,
) -> Path:
    """Store bytes at sha256/<digest>.zip without overwriting."""
    expected = _validated_digest(expected_sha256)
    source = _check_regular_file(
        source_bundle,
        "source bundle",
    )

    root = Path(store_root)
    namespace = _check_store_paths(root)

    target = namespace / f"{expected}.zip"

    if target.exists() or target.is_symlink():
        raise FileExistsError(target)

    if not hmac.compare_digest(
        _sha256_file(source),
        expected,
    ):
        raise ValueError(
            "Source bundle SHA-256 mismatch"
        )

    namespace.mkdir(
        parents=True,
        exist_ok=True,
    )

    _check_store_paths(root)

    if target.exists() or target.is_symlink():
        raise FileExistsError(target)

    staging = _copy_to_staging(
        source=source,
        destination_parent=namespace,
        prefix=".bundle-publish-",
        expected_sha256=expected,
    )

    try:
        # Detect changes in the source during copying.
        _check_regular_file(
            source,
            "source bundle",
        )

        if not hmac.compare_digest(
            _sha256_file(source),
            expected,
        ):
            raise ValueError(
                "Source changed during bundle publication"
            )

        # Exclusive, atomic file creation on the same
        # filesystem. Existing objects are never replaced.
        os.link(staging, target)

        return target

    finally:
        staging.unlink(missing_ok=True)


def fetch_immutable_bundle(
    *,
    store_root,
    expected_sha256,
    output_path,
) -> Path:
    """Fetch verified object bytes to a new destination only."""
    expected = _validated_digest(expected_sha256)

    target = Path(output_path)

    if target.exists() or target.is_symlink():
        raise FileExistsError(target)

    root = Path(store_root)
    namespace = _check_store_paths(root)

    stored = namespace / f"{expected}.zip"

    _check_regular_file(
        stored,
        "stored bundle",
    )

    if not hmac.compare_digest(
        _sha256_file(stored),
        expected,
    ):
        raise ValueError(
            "Stored bundle SHA-256 mismatch"
        )

    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    staging = _copy_to_staging(
        source=stored,
        destination_parent=target.parent,
        prefix=".bundle-fetch-",
        expected_sha256=expected,
    )

    try:
        # Confirm the stored object did not change
        # during this copy operation.
        _check_regular_file(
            stored,
            "stored bundle",
        )

        if not hmac.compare_digest(
            _sha256_file(stored),
            expected,
        ):
            raise ValueError(
                "Stored bundle changed during fetch"
            )

        # Refuse overwrite even if a second process
        # created the target while copying.
        os.link(staging, target)

        return target

    finally:
        staging.unlink(missing_ok=True)
