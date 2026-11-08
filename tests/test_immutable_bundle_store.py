"""A6c.24: immutable, content-addressed bundle storage."""

import hashlib
from pathlib import Path
import zipfile

import pytest

from src.data.immutable_bundle_store import (
    publish_immutable_bundle,
    fetch_immutable_bundle,
)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(1024 * 1024), b""
        ):
            digest.update(chunk)
    return digest.hexdigest()


@pytest.fixture
def case(tmp_path):
    source = tmp_path / "recovery.zip"

    with zipfile.ZipFile(
        source, "w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        archive.writestr("anchor.json", b'{"test": true}')
        archive.writestr("checkpoint.json", b'{"test": true}')
        archive.writestr(
            "snapshot/manifest.json",
            b'{"test": true}',
        )
        archive.writestr(
            "snapshot/market_data.db",
            b"SQLITE TEST FIXTURE",
        )

    return {
        "source": source,
        "store": tmp_path / "object-store",
        "output": tmp_path / "downloaded.zip",
        "digest": sha256(source),
    }


def publish(case, **overrides):
    args = {
        "source_bundle": case["source"],
        "store_root": case["store"],
        "expected_sha256": case["digest"],
    }
    args.update(overrides)
    return publish_immutable_bundle(**args)


def fetch(case, **overrides):
    args = {
        "store_root": case["store"],
        "expected_sha256": case["digest"],
        "output_path": case["output"],
    }
    args.update(overrides)
    return fetch_immutable_bundle(**args)


def test_publish_uses_content_addressed_key(case):
    result = publish(case)

    assert result == (
        case["store"]
        / "sha256"
        / f"{case['digest']}.zip"
    )
    assert result.is_file()
    assert sha256(result) == case["digest"]
    assert sha256(case["source"]) == case["digest"]


def test_publish_does_not_overwrite_existing_object(case):
    result = publish(case)
    original = result.read_bytes()

    with pytest.raises(FileExistsError):
        publish(case)

    assert result.read_bytes() == original


def test_publish_rejects_wrong_expected_digest(case):
    with pytest.raises(ValueError):
        publish(
            case,
            expected_sha256="0" * 64,
        )

    assert not (
        case["store"] / "sha256" / ("0" * 64 + ".zip")
    ).exists()


def test_fetch_preserves_exact_bundle_bytes(case):
    stored = publish(case)

    result = fetch(case)

    assert result == case["output"]
    assert result.is_file()
    assert result.read_bytes() == stored.read_bytes()
    assert sha256(result) == case["digest"]


def test_fetch_rejects_corrupted_stored_object(case):
    stored = publish(case)

    with stored.open("ab") as stream:
        stream.write(b"UNAUTHORIZED MODIFICATION")

    with pytest.raises(ValueError):
        fetch(case)

    assert not case["output"].exists()


def test_fetch_rejects_symlinked_storage_object(case):
    stored = publish(case)
    stored.unlink()
    stored.symlink_to(case["source"])

    with pytest.raises(ValueError):
        fetch(case)

    assert not case["output"].exists()


def test_fetch_cannot_overwrite_existing_destination(case):
    publish(case)

    case["output"].write_bytes(b"PROTECTED")
    before = case["output"].read_bytes()

    with pytest.raises(FileExistsError):
        fetch(case)

    assert case["output"].read_bytes() == before


def test_invalid_content_address_is_rejected(case):
    with pytest.raises(ValueError):
        publish(
            case,
            expected_sha256="../escape",
        )

    assert not (
        case["store"].parent / "escape"
    ).exists()
