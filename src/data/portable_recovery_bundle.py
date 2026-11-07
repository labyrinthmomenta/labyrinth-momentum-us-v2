"""Offline portable recovery bundles for the US pilot.

This module does not authorize live ingestion, scheduling,
production publication, or external trust approval.
"""

from datetime import date
import hashlib
import json
import hmac
import os
from pathlib import Path
import shutil
import stat
import tempfile
import zipfile

from src.data.checkpoint_anchor import (
    load_bootstrap_checkpoint_anchor,
)
from src.data.snapshot_checkpoint import (
    verify_snapshot_checkpoint,
)


MEMBERS = (
    "anchor.json",
    "checkpoint.json",
    "snapshot/manifest.json",
    "snapshot/market_data.db",
)

MAX_MEMBER_BYTES = {
    "anchor.json": 32768,
    "checkpoint.json": 32768,
    "snapshot/manifest.json": 32768,
    "snapshot/market_data.db": 512 * 1024 * 1024,
}

CHUNK_SIZE = 1024 * 1024


def _sha256_file(path):
    digest = hashlib.sha256()

    with Path(path).open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(CHUNK_SIZE), b""
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _verify_chain(
    *,
    anchor_path,
    checkpoint_path,
    snapshot_dir,
    trusted_anchor_sha256,
    expected_pilot_manifest_sha256,
    required_symbols,
    min_as_of,
    original_checkpoint_name=None,
):
    """Verify externally pinned anchor, checkpoint and SQLite."""
    anchor = load_bootstrap_checkpoint_anchor(
        anchor_path=anchor_path,
        trusted_anchor_sha256=trusted_anchor_sha256,
        min_as_of=min_as_of,
    )

    if (
        anchor["pilot_manifest_sha256"]
        != expected_pilot_manifest_sha256
    ):
        raise ValueError(
            "Pilot manifest SHA-256 mismatch"
        )

    if Path(snapshot_dir).name != anchor["snapshot_id"]:
        raise ValueError(
            "Snapshot directory identity mismatch"
        )

    if (
        original_checkpoint_name is not None
        and anchor["checkpoint_file"]
        != original_checkpoint_name
    ):
        raise ValueError(
            "Checkpoint filename mismatch"
        )

    checkpoint = verify_snapshot_checkpoint(
        checkpoint_path=checkpoint_path,
        snapshot_dir=snapshot_dir,
        trusted_checkpoint_sha256=(
            anchor["checkpoint_sha256"]
        ),
        expected_pilot_manifest_sha256=(
            expected_pilot_manifest_sha256
        ),
        required_symbols=required_symbols,
        min_as_of=min_as_of,
        expected_previous_checkpoint_sha256=None,
    )

    for field in (
        "snapshot_id",
        "snapshot_sha256",
        "pilot_manifest_sha256",
        "as_of",
        "previous_checkpoint_sha256",
    ):
        if checkpoint[field] != anchor[field]:
            raise ValueError(
                f"Anchor/checkpoint mismatch: {field}"
            )

    return anchor


def _source_files(anchor, checkpoint, snapshot):
    return {
        "anchor.json": anchor,
        "checkpoint.json": checkpoint,
        "snapshot/manifest.json": (
            snapshot / "manifest.json"
        ),
        "snapshot/market_data.db": (
            snapshot / "market_data.db"
        ),
    }


def _check_regular_files(sources):
    for name, path in sources.items():
        if not path.is_file() or path.is_symlink():
            raise ValueError(
                f"Missing or unsafe bundle member: {name}"
            )

        size = path.stat().st_size

        if (
            size <= 0
            or size > MAX_MEMBER_BYTES[name]
        ):
            raise ValueError(
                f"Invalid bundle member size: {name}"
            )


def _archive_members(archive):
    """Reject unknown, duplicate, unsafe or oversized entries."""
    infos = archive.infolist()
    names = [info.filename for info in infos]

    if (
        len(names) != len(MEMBERS)
        or set(names) != set(MEMBERS)
    ):
        raise ValueError(
            "Unexpected, duplicate or unsafe ZIP members"
        )

    result = {}

    for info in infos:
        name = info.filename

        if info.is_dir() or info.flag_bits & 1:
            raise ValueError(
                f"Unsafe archive entry: {name}"
            )

        file_type = stat.S_IFMT(
            info.external_attr >> 16
        )

        if file_type not in (0, stat.S_IFREG):
            raise ValueError(
                f"Unsupported ZIP file type: {name}"
            )

        if (
            info.file_size <= 0
            or info.file_size > MAX_MEMBER_BYTES[name]
        ):
            raise ValueError(
                f"Oversized ZIP member: {name}"
            )

        if info.compress_type not in (
            zipfile.ZIP_STORED,
            zipfile.ZIP_DEFLATED,
        ):
            raise ValueError(
                f"Unsupported ZIP compression: {name}"
            )

        result[name] = info

    return result


def _extract_member(archive, info, output_path):
    """Stream one explicitly mapped member; never extract paths."""
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    count = 0

    with archive.open(info, "r") as source:
        with output_path.open("xb") as output:
            while True:
                chunk = source.read(CHUNK_SIZE)

                if not chunk:
                    break

                count += len(chunk)

                if count > info.file_size:
                    raise ValueError(
                        "Archive member exceeded declared size"
                    )

                output.write(chunk)

            output.flush()
            os.fsync(output.fileno())

    if count != info.file_size:
        raise ValueError(
            "Archive member size mismatch"
        )



def _unique_marker_keys(pairs):
    result = {}

    for key, value in pairs:
        if key in result:
            raise ValueError(
                f"Duplicate completion marker key: {key}"
            )
        result[key] = value

    return result


def _completion_marker_data(
    *,
    anchor,
    bundle_sha256,
    trusted_anchor_sha256,
):
    """Describe the verified offline recovery state."""
    return {
        "schema_version": 1,
        "status": "VERIFIED_OFFLINE",
        "market": "US",
        "mode": "PILOT_ONLY",
        "approval_status": "OFFLINE_CANDIDATE",
        "production_approved": False,
        "bundle_sha256": bundle_sha256,
        "trusted_anchor_sha256": (
            trusted_anchor_sha256
        ),
        "checkpoint_sha256": (
            anchor["checkpoint_sha256"]
        ),
        "snapshot_id": anchor["snapshot_id"],
        "snapshot_sha256": (
            anchor["snapshot_sha256"]
        ),
        "pilot_manifest_sha256": (
            anchor["pilot_manifest_sha256"]
        ),
        "as_of": anchor["as_of"],
        "previous_checkpoint_sha256": None,
    }


def _write_completion_marker(marker_path, marker_data):
    """Publish the completion marker last, exclusively."""
    marker_path = Path(marker_path)

    if marker_path.exists() or marker_path.is_symlink():
        raise FileExistsError(marker_path)

    content = (
        json.dumps(
            marker_data,
            indent=2,
            sort_keys=True,
        ) + "\n"
    ).encode("utf-8")

    fd, staging_name = tempfile.mkstemp(
        prefix=".completion-staging-",
        dir=marker_path.parent,
    )

    staging = Path(staging_name)

    try:
        with os.fdopen(fd, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())

        # Same-filesystem atomic, non-overwriting
        # publication of the final completion marker.
        os.link(staging, marker_path)

    finally:
        staging.unlink(missing_ok=True)


def verify_committed_recovery(
    *,
    restore_root,
    bundle_path,
    trusted_anchor_sha256,
    expected_pilot_manifest_sha256,
    required_symbols,
    min_as_of: date,
) -> dict:
    """Accept only a fully marked and reverified recovery.

    A completion marker is not a signature or an
    authorization for live or production operations.
    """
    target = Path(restore_root)
    bundle = Path(bundle_path)

    if not target.is_dir() or target.is_symlink():
        raise ValueError(
            "Recovery root is missing or unsafe"
        )

    if not bundle.is_file() or bundle.is_symlink():
        raise ValueError(
            "Recovery bundle is missing or unsafe"
        )

    marker_path = target / "recovery.complete.json"

    if (
        not marker_path.is_file()
        or marker_path.is_symlink()
    ):
        raise ValueError(
            "Missing or unsafe recovery completion marker"
        )

    if (
        marker_path.stat().st_size <= 0
        or marker_path.stat().st_size > 32768
    ):
        raise ValueError(
            "Invalid completion marker size"
        )

    try:
        marker = json.loads(
            marker_path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_marker_keys,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "Invalid completion marker JSON"
        ) from exc

    if not isinstance(marker, dict):
        raise ValueError(
            "Completion marker must be a JSON object"
        )

    if (
        type(marker.get("schema_version")) is not int
        or marker.get("production_approved") is not False
    ):
        raise ValueError(
            "Completion marker safety policy rejected"
        )

    anchor_path = target / "anchor.json"
    checkpoint_path = target / "checkpoint.json"

    anchor = load_bootstrap_checkpoint_anchor(
        anchor_path=anchor_path,
        trusted_anchor_sha256=trusted_anchor_sha256,
        min_as_of=min_as_of,
    )

    snapshot_parent = target / "snapshot"
    snapshot = (
        snapshot_parent
        / anchor["snapshot_id"]
    )

    if (
        not snapshot_parent.is_dir()
        or snapshot_parent.is_symlink()
    ):
        raise ValueError(
            "Unsafe restored snapshot directory"
        )

    # Reject unexpected files in an allegedly complete
    # recovery, including abandoned staging artifacts.
    if {
        path.name for path in target.iterdir()
    } != {
        "anchor.json",
        "checkpoint.json",
        "snapshot",
        "recovery.complete.json",
    }:
        raise ValueError(
            "Unexpected recovery root contents"
        )

    if {
        path.name for path in snapshot_parent.iterdir()
    } != {anchor["snapshot_id"]}:
        raise ValueError(
            "Unexpected snapshot directory contents"
        )

    if not snapshot.is_dir() or snapshot.is_symlink():
        raise ValueError(
            "Unsafe restored snapshot"
        )

    if {
        path.name for path in snapshot.iterdir()
    } != {"manifest.json", "market_data.db"}:
        raise ValueError(
            "Unexpected restored snapshot files"
        )

    files = _source_files(
        anchor_path,
        checkpoint_path,
        snapshot,
    )
    _check_regular_files(files)

    verified_anchor = _verify_chain(
        anchor_path=anchor_path,
        checkpoint_path=checkpoint_path,
        snapshot_dir=snapshot,
        trusted_anchor_sha256=trusted_anchor_sha256,
        expected_pilot_manifest_sha256=(
            expected_pilot_manifest_sha256
        ),
        required_symbols=required_symbols,
        min_as_of=min_as_of,
    )

    bundle_sha256 = _sha256_file(bundle)

    expected_marker = _completion_marker_data(
        anchor=verified_anchor,
        bundle_sha256=bundle_sha256,
        trusted_anchor_sha256=trusted_anchor_sha256,
    )

    if set(marker) != set(expected_marker):
        raise ValueError(
            "Unexpected completion marker schema"
        )

    if marker != expected_marker:
        raise ValueError(
            "Completion marker content or digest mismatch"
        )

    # A valid bundle hash alone is insufficient:
    # ensure all archived payloads still match
    # the restored, validated files.
    try:
        with zipfile.ZipFile(bundle, "r") as archive:
            infos = _archive_members(archive)

            for member, restored_file in files.items():
                digest = hashlib.sha256()

                with archive.open(
                    infos[member],
                    "r",
                ) as stream:
                    for chunk in iter(
                        lambda: stream.read(CHUNK_SIZE),
                        b"",
                    ):
                        digest.update(chunk)

                if not hmac.compare_digest(
                    digest.hexdigest(),
                    _sha256_file(restored_file),
                ):
                    raise ValueError(
                        f"Bundle/restored mismatch: {member}"
                    )

    except (
        zipfile.BadZipFile,
        EOFError,
        RuntimeError,
    ) as exc:
        raise ValueError(
            "Recovery bundle failed ZIP verification"
        ) from exc

    if not hmac.compare_digest(
        _sha256_file(bundle),
        bundle_sha256,
    ):
        raise ValueError(
            "Recovery bundle changed during verification"
        )

    # Ensure the marker itself remained unchanged.
    if json.loads(
        marker_path.read_text(encoding="utf-8"),
        object_pairs_hook=_unique_marker_keys,
    ) != marker:
        raise ValueError(
            "Completion marker changed during verification"
        )

    return marker


def create_portable_recovery_bundle(
    *,
    anchor_path,
    checkpoint_path,
    snapshot_dir,
    bundle_path,
    trusted_anchor_sha256,
    expected_pilot_manifest_sha256,
    required_symbols,
    min_as_of: date,
) -> Path:
    """Build a four-member ZIP, without overwriting a target."""
    anchor = Path(anchor_path)
    checkpoint = Path(checkpoint_path)
    snapshot = Path(snapshot_dir)
    target = Path(bundle_path)

    if target.exists() or target.is_symlink():
        raise FileExistsError(target)

    _verify_chain(
        anchor_path=anchor,
        checkpoint_path=checkpoint,
        snapshot_dir=snapshot,
        trusted_anchor_sha256=trusted_anchor_sha256,
        expected_pilot_manifest_sha256=(
            expected_pilot_manifest_sha256
        ),
        required_symbols=required_symbols,
        min_as_of=min_as_of,
        original_checkpoint_name=checkpoint.name,
    )

    sources = _source_files(
        anchor, checkpoint, snapshot
    )
    _check_regular_files(sources)

    original_hashes = {
        name: _sha256_file(path)
        for name, path in sources.items()
    }

    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fd, name = tempfile.mkstemp(
        prefix=f".{target.name}.staging-",
        dir=target.parent,
    )
    os.close(fd)
    staging = Path(name)

    try:
        with zipfile.ZipFile(
            staging,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as archive:
            for member, path in sources.items():
                info = zipfile.ZipInfo(
                    member,
                    date_time=(2020, 1, 1, 0, 0, 0),
                )
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = (
                    (stat.S_IFREG | 0o600) << 16
                )

                with path.open("rb") as source:
                    with archive.open(
                        info,
                        "w",
                        force_zip64=True,
                    ) as output:
                        shutil.copyfileobj(
                            source,
                            output,
                            CHUNK_SIZE,
                        )

        # Verify archive payload against source digests.
        with zipfile.ZipFile(staging, "r") as archive:
            infos = _archive_members(archive)

            for member, path in sources.items():
                digest = hashlib.sha256()

                with archive.open(
                    infos[member], "r"
                ) as stream:
                    for chunk in iter(
                        lambda: stream.read(CHUNK_SIZE),
                        b"",
                    ):
                        digest.update(chunk)

                if not hmac.compare_digest(
                    digest.hexdigest(),
                    original_hashes[member],
                ):
                    raise ValueError(
                        f"Archive payload mismatch: {member}"
                    )

                if not hmac.compare_digest(
                    _sha256_file(path),
                    original_hashes[member],
                ):
                    raise ValueError(
                        f"Source changed while archiving: {member}"
                    )

        # Verify original trust chain again before publication.
        _verify_chain(
            anchor_path=anchor,
            checkpoint_path=checkpoint,
            snapshot_dir=snapshot,
            trusted_anchor_sha256=trusted_anchor_sha256,
            expected_pilot_manifest_sha256=(
                expected_pilot_manifest_sha256
            ),
            required_symbols=required_symbols,
            min_as_of=min_as_of,
            original_checkpoint_name=checkpoint.name,
        )

        with staging.open("rb") as stream:
            os.fsync(stream.fileno())

        # Exclusive atomic file publication.
        os.link(staging, target)

        return target

    finally:
        staging.unlink(missing_ok=True)


def restore_portable_recovery_bundle(
    *,
    bundle_path,
    trusted_anchor_sha256,
    expected_pilot_manifest_sha256,
    required_symbols,
    min_as_of: date,
    restore_root,
) -> Path:
    """Verify an untrusted ZIP before non-overwriting publication."""
    bundle = Path(bundle_path)
    target = Path(restore_root)

    if target.exists() or target.is_symlink():
        raise FileExistsError(target)

    if not bundle.is_file() or bundle.is_symlink():
        raise ValueError(
            "Recovery bundle missing or unsafe"
        )

    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    staging = Path(
        tempfile.mkdtemp(
            prefix=".portable-recovery-staging-",
            dir=target.parent,
        )
    )

    try:
        try:
            with zipfile.ZipFile(bundle, "r") as archive:
                infos = _archive_members(archive)

                staged_anchor = staging / "anchor.json"

                _extract_member(
                    archive,
                    infos["anchor.json"],
                    staged_anchor,
                )

                # Establish snapshot ID from validated
                # externally pinned anchor, never ZIP paths.
                anchor = load_bootstrap_checkpoint_anchor(
                    anchor_path=staged_anchor,
                    trusted_anchor_sha256=(
                        trusted_anchor_sha256
                    ),
                    min_as_of=min_as_of,
                )

                snapshot = (
                    staging
                    / "snapshot"
                    / anchor["snapshot_id"]
                )

                staged_checkpoint = (
                    staging / "checkpoint.json"
                )

                _extract_member(
                    archive,
                    infos["checkpoint.json"],
                    staged_checkpoint,
                )

                _extract_member(
                    archive,
                    infos["snapshot/manifest.json"],
                    snapshot / "manifest.json",
                )

                _extract_member(
                    archive,
                    infos["snapshot/market_data.db"],
                    snapshot / "market_data.db",
                )

        except (
            zipfile.BadZipFile,
            EOFError,
            RuntimeError,
        ) as exc:
            raise ValueError(
                "Invalid recovery ZIP archive"
            ) from exc

        # The extracted contents are still untrusted.
        anchor = _verify_chain(
            anchor_path=staged_anchor,
            checkpoint_path=staged_checkpoint,
            snapshot_dir=snapshot,
            trusted_anchor_sha256=trusted_anchor_sha256,
            expected_pilot_manifest_sha256=(
                expected_pilot_manifest_sha256
            ),
            required_symbols=required_symbols,
            min_as_of=min_as_of,
        )

        # Claim target exclusively after all checks pass.
        target.mkdir(mode=0o700, exist_ok=False)

        try:
            files = _source_files(
                staged_anchor,
                staged_checkpoint,
                snapshot,
            )

            destinations = {
                "anchor.json": target / "anchor.json",
                "checkpoint.json": (
                    target / "checkpoint.json"
                ),
                "snapshot/manifest.json": (
                    target
                    / "snapshot"
                    / anchor["snapshot_id"]
                    / "manifest.json"
                ),
                "snapshot/market_data.db": (
                    target
                    / "snapshot"
                    / anchor["snapshot_id"]
                    / "market_data.db"
                ),
            }

            for member in MEMBERS:
                output = destinations[member]

                output.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                # Same-filesystem exclusive hard link.
                os.link(files[member], output)

            # Verify published content as well.
            _verify_chain(
                anchor_path=target / "anchor.json",
                checkpoint_path=target / "checkpoint.json",
                snapshot_dir=(
                    target
                    / "snapshot"
                    / anchor["snapshot_id"]
                ),
                trusted_anchor_sha256=(
                    trusted_anchor_sha256
                ),
                expected_pilot_manifest_sha256=(
                    expected_pilot_manifest_sha256
                ),
                required_symbols=required_symbols,
                min_as_of=min_as_of,
            )


            # The recovered files and their trust chain
            # have been verified. Publish the marker last.
            marker_data = _completion_marker_data(
                anchor=anchor,
                bundle_sha256=_sha256_file(bundle),
                trusted_anchor_sha256=(
                    trusted_anchor_sha256
                ),
            )

            _write_completion_marker(
                target / "recovery.complete.json",
                marker_data,
            )

            # Confirm the published recovery is actually
            # consumable before returning success.
            verify_committed_recovery(
                restore_root=target,
                bundle_path=bundle,
                trusted_anchor_sha256=(
                    trusted_anchor_sha256
                ),
                expected_pilot_manifest_sha256=(
                    expected_pilot_manifest_sha256
                ),
                required_symbols=required_symbols,
                min_as_of=min_as_of,
            )

        except BaseException:
            # An incomplete publication is never accepted.
            shutil.rmtree(target)
            raise

        return target

    finally:
        shutil.rmtree(staging, ignore_errors=True)
