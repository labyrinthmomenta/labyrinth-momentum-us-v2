"""A6c.25: fail-closed remote recovery reader contract.

All tests use in-memory objects. No cloud access.
"""

from contextlib import closing
import hashlib
import io
from pathlib import Path
import zipfile

import pytest

from src.data.remote_recovery_reader import (
    fetch_pinned_remote_bundle,
)


class FakeRemoteReader:
    """Read-only in-memory object-store transport."""

    def __init__(self, payload):
        self.payload = payload
        self.requested = []

    def open_object(self, key):
        self.requested.append(key)
        return closing(io.BytesIO(self.payload))


@pytest.fixture
def case(tmp_path):
    buffer = io.BytesIO()

    with zipfile.ZipFile(
        buffer,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        archive.writestr(
            "anchor.json",
            b'{"offline": true}',
        )
        archive.writestr(
            "checkpoint.json",
            b'{"offline": true}',
        )
        archive.writestr(
            "snapshot/manifest.json",
            b'{"offline": true}',
        )
        archive.writestr(
            "snapshot/market_data.db",
            b"OFFLINE TEST PAYLOAD",
        )

    payload = buffer.getvalue()
    digest = hashlib.sha256(payload).hexdigest()

    return {
        "payload": payload,
        "digest": digest,
        "key": f"sha256/{digest}.zip",
        "reader": FakeRemoteReader(payload),
        "output": tmp_path / "downloaded.zip",
    }


def download(case, **overrides):
    args = {
        "reader": case["reader"],
        "object_key": case["key"],
        "expected_sha256": case["digest"],
        "output_path": case["output"],
        "max_bytes": 16 * 1024 * 1024,
    }

    args.update(overrides)

    return fetch_pinned_remote_bundle(**args)


def test_valid_pinned_remote_download(case):
    result = download(case)

    assert result == case["output"]
    assert result.read_bytes() == case["payload"]
    assert case["reader"].requested == [case["key"]]

    assert hashlib.sha256(
        result.read_bytes()
    ).hexdigest() == case["digest"]


def test_path_traversal_key_rejected_before_read(case):
    with pytest.raises(ValueError):
        download(
            case,
            object_key="../unauthorized.zip",
        )

    assert case["reader"].requested == []
    assert not case["output"].exists()


def test_key_digest_mismatch_rejected_before_read(case):
    with pytest.raises(ValueError):
        download(
            case,
            object_key=f"sha256/{'0' * 64}.zip",
        )

    assert case["reader"].requested == []
    assert not case["output"].exists()


def test_corrupted_remote_bytes_rejected(case):
    reader = FakeRemoteReader(
        case["payload"] + b"UNEXPECTED DATA"
    )

    with pytest.raises(ValueError):
        download(case, reader=reader)

    assert reader.requested == [case["key"]]
    assert not case["output"].exists()


def test_oversized_remote_object_rejected(case):
    with pytest.raises(ValueError):
        download(
            case,
            max_bytes=len(case["payload"]) - 1,
        )

    assert not case["output"].exists()


def test_existing_download_cannot_be_overwritten(case):
    case["output"].write_bytes(b"PROTECTED")

    with pytest.raises(FileExistsError):
        download(case)

    assert case["output"].read_bytes() == b"PROTECTED"
    assert case["reader"].requested == []


def test_symlinked_destination_rejected(case):
    protected = (
        case["output"].parent / "protected.txt"
    )
    protected.write_bytes(b"DO NOT MODIFY")

    case["output"].symlink_to(protected)

    with pytest.raises((ValueError, FileExistsError)):
        download(case)

    assert protected.read_bytes() == b"DO NOT MODIFY"
    assert case["reader"].requested == []


def test_interrupted_remote_stream_leaves_no_output(case):
    class BrokenStream(io.BytesIO):
        def __init__(self, payload):
            super().__init__(payload)
            self.read_count = 0

        def read(self, size=-1):
            self.read_count += 1

            if self.read_count > 1:
                raise OSError(
                    "simulated remote transport failure"
                )

            return super().read(size)

    class BrokenReader:
        def open_object(self, key):
            return closing(
                BrokenStream(case["payload"])
            )

    with pytest.raises(
        OSError,
        match="simulated remote transport failure",
    ):
        download(
            case,
            reader=BrokenReader(),
        )

    assert not case["output"].exists()

    # A failed download must not leave staging files.
    assert list(
        case["output"].parent.iterdir()
    ) == []
