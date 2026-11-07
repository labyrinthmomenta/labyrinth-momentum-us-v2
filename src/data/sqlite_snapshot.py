"""Verified, non-overwriting SQLite snapshots for US pilot data."""

from contextlib import closing
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
from urllib.parse import quote

from src.data.daily_run_lock import hold_daily_ingestion_lock


SCHEMA_VERSION = 1
DATABASE_NAME = "market_data.db"
MANIFEST_NAME = "manifest.json"

EXPECTED_TABLES = (
    "daily_bars",
    "download_status",
)

ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")
SHA_PATTERN = re.compile(r"[0-9a-f]{64}")


def _read_only_uri(path: Path) -> str:
    resolved = path.resolve()
    return (
        "file:"
        + quote(str(resolved), safe="/")
        + "?mode=ro"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _sync_file(path: Path) -> None:
    with path.open("rb") as stream:
        os.fsync(stream.fileno())


def _inspect_database(path: Path) -> dict[str, int]:
    """Validate SQLite and count required US ingestion tables."""
    if not path.is_file() or path.is_symlink():
        raise ValueError(
            f"Missing or unsafe SQLite database: {path}"
        )

    try:
        with closing(
            sqlite3.connect(
                _read_only_uri(path),
                uri=True,
            )
        ) as conn:
            integrity = conn.execute(
                "PRAGMA integrity_check"
            ).fetchone()

            if integrity != ("ok",):
                raise ValueError(
                    f"SQLite integrity check failed: {integrity}"
                )

            counts = {}

            for table in EXPECTED_TABLES:
                exists = conn.execute(
                    """
                    SELECT 1
                    FROM sqlite_master
                    WHERE type = 'table' AND name = ?
                    """,
                    (table,),
                ).fetchone()

                if exists is None:
                    raise ValueError(
                        f"Missing required SQLite table: {table}"
                    )

                # Table identifiers come only from our
                # fixed EXPECTED_TABLES tuple.
                counts[table] = conn.execute(
                    f'SELECT COUNT(*) FROM "{table}"'
                ).fetchone()[0]

            return counts

    except sqlite3.DatabaseError as exc:
        raise ValueError(
            f"Invalid SQLite database: {path}"
        ) from exc


def _validate_snapshot_id(snapshot_id: str) -> None:
    if (
        not isinstance(snapshot_id, str)
        or ID_PATTERN.fullmatch(snapshot_id) is None
    ):
        raise ValueError(
            "Invalid snapshot ID; use letters, digits, "
            "underscores, or hyphens"
        )


def _validate_manifest(
    snapshot_dir: Path,
    manifest: object,
) -> dict:
    if not isinstance(manifest, dict):
        raise ValueError(
            "Snapshot manifest must be a JSON object"
        )

    required = {
        "schema_version",
        "market",
        "snapshot_id",
        "database_file",
        "sha256",
        "database_bytes",
        "tables",
    }

    if set(manifest) != required:
        raise ValueError("Invalid snapshot manifest schema")

    if (
        type(manifest["schema_version"]) is not int
        or manifest["schema_version"] != SCHEMA_VERSION
        or manifest["market"] != "US"
        or manifest["database_file"] != DATABASE_NAME
    ):
        raise ValueError("Invalid snapshot manifest metadata")

    snapshot_id = manifest["snapshot_id"]
    _validate_snapshot_id(snapshot_id)

    if snapshot_id != snapshot_dir.name:
        raise ValueError(
            "Snapshot ID does not match directory name"
        )

    if (
        not isinstance(manifest["sha256"], str)
        or SHA_PATTERN.fullmatch(
            manifest["sha256"]
        ) is None
    ):
        raise ValueError("Invalid snapshot SHA-256")

    size = manifest["database_bytes"]

    if type(size) is not int or size <= 0:
        raise ValueError("Invalid snapshot database size")

    tables = manifest["tables"]

    if (
        not isinstance(tables, dict)
        or set(tables) != set(EXPECTED_TABLES)
    ):
        raise ValueError("Invalid snapshot table metadata")

    for table, count in tables.items():
        if type(count) is not int or count < 0:
            raise ValueError(
                f"Invalid row count for {table}"
            )

    return manifest


def _check_no_sidecars(db_path: Path) -> None:
    """Require a standalone database without SQLite sidecars."""
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = Path(str(db_path) + suffix)

        if sidecar.exists() or sidecar.is_symlink():
            raise ValueError(
                f"Unexpected SQLite sidecar: {sidecar}"
            )


def create_sqlite_snapshot(
    *,
    source_db: str | Path,
    snapshot_root: str | Path,
    snapshot_id: str,
) -> Path:
    """Create a verified snapshot without overwriting existing IDs.

    Holds the same database lock as the ingestion runner.
    Uses SQLite Backup API, including for WAL-mode sources.

    The database file is published first and the verified
    manifest last. An incomplete snapshot fails verification.
    """
    _validate_snapshot_id(snapshot_id)

    source = Path(source_db)
    root = Path(snapshot_root)
    destination = root / snapshot_id

    if not source.is_file() or source.is_symlink():
        raise FileNotFoundError(source)

    # Acquire the lock BEFORE inspecting or copying the DB.
    with hold_daily_ingestion_lock(source):
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(destination)

        source_counts = _inspect_database(source)

        root.mkdir(parents=True, exist_ok=True)

        staging = Path(
            tempfile.mkdtemp(
                prefix=f".{snapshot_id}.staging-",
                dir=root,
            )
        )

        try:
            staged_db = staging / DATABASE_NAME
            staged_manifest = staging / MANIFEST_NAME

            with closing(
                sqlite3.connect(
                    _read_only_uri(source),
                    uri=True,
                )
            ) as source_conn:
                with closing(
                    sqlite3.connect(staged_db)
                ) as backup_conn:
                    source_conn.backup(backup_conn)
                    backup_conn.commit()

            # SQLite Backup API may preserve WAL journal mode.
            # Convert ONLY the staged copy into a standalone
            # database before hashing and publication.
            with closing(sqlite3.connect(staged_db)) as conn:
                mode = conn.execute(
                    "PRAGMA journal_mode=DELETE"
                ).fetchone()

                if mode != ("delete",):
                    raise ValueError(
                        "Snapshot journal normalization failed"
                    )

            _check_no_sidecars(staged_db)

            backup_counts = _inspect_database(staged_db)

            if backup_counts != source_counts:
                raise ValueError(
                    "Source and backup table counts differ"
                )

            _sync_file(staged_db)

            manifest = {
                "schema_version": SCHEMA_VERSION,
                "market": "US",
                "snapshot_id": snapshot_id,
                "database_file": DATABASE_NAME,
                "sha256": _sha256(staged_db),
                "database_bytes": staged_db.stat().st_size,
                "tables": backup_counts,
            }

            with staged_manifest.open(
                "x",
                encoding="utf-8",
            ) as stream:
                json.dump(
                    manifest,
                    stream,
                    indent=2,
                    sort_keys=True,
                )
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())

            # Exclusive directory creation prevents another
            # snapshot with the same ID from being replaced.
            destination.mkdir(mode=0o700, exist_ok=False)

            try:
                # Both hard links remain on the same filesystem.
                # The manifest is the final publication marker.
                os.link(
                    staged_db,
                    destination / DATABASE_NAME,
                )

                os.link(
                    staged_manifest,
                    destination / MANIFEST_NAME,
                )

            except BaseException:
                # Clean up an incomplete publication.
                shutil.rmtree(destination)
                raise

            return destination

        finally:
            shutil.rmtree(staging, ignore_errors=True)


def verify_sqlite_snapshot(
    snapshot_dir: str | Path,
) -> dict:
    """Fail closed for missing, corrupt, or inconsistent snapshots."""
    snapshot = Path(snapshot_dir)

    if not snapshot.is_dir() or snapshot.is_symlink():
        raise ValueError(
            f"Invalid snapshot directory: {snapshot}"
        )

    manifest_file = snapshot / MANIFEST_NAME
    database_file = snapshot / DATABASE_NAME

    if (
        not manifest_file.is_file()
        or manifest_file.is_symlink()
        or not database_file.is_file()
        or database_file.is_symlink()
    ):
        raise ValueError(
            "Snapshot database or manifest is missing or unsafe"
        )

    def unique_keys(pairs):
        result = {}

        for key, value in pairs:
            if key in result:
                raise ValueError(
                    f"Duplicate manifest key: {key}"
                )

            result[key] = value

        return result

    manifest = json.loads(
        manifest_file.read_text(encoding="utf-8"),
        object_pairs_hook=unique_keys,
    )

    manifest = _validate_manifest(
        snapshot,
        manifest,
    )

    _check_no_sidecars(database_file)

    if database_file.stat().st_size != manifest["database_bytes"]:
        raise ValueError(
            "Snapshot database size mismatch"
        )

    actual_digest = _sha256(database_file)

    if not hmac.compare_digest(
        actual_digest,
        manifest["sha256"],
    ):
        raise ValueError(
            "Snapshot SHA-256 mismatch"
        )

    actual_counts = _inspect_database(database_file)

    if actual_counts != manifest["tables"]:
        raise ValueError(
            "Snapshot table counts mismatch"
        )

    return manifest


def restore_sqlite_snapshot(
    *,
    snapshot_dir: str | Path,
    target_db: str | Path,
) -> Path:
    """Restore to a new target, never replacing an existing DB.

    Copying occurs into a temporary file. The temporary copy
    is independently verified before exclusive publication.
    """
    target = Path(target_db)

    if target.exists() or target.is_symlink():
        raise FileExistsError(target)

    _check_no_sidecars(target)

    manifest = verify_sqlite_snapshot(snapshot_dir)

    source_file = Path(snapshot_dir) / DATABASE_NAME

    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fd, staging_name = tempfile.mkstemp(
        prefix=f".{target.name}.restore-",
        suffix=".tmp",
        dir=target.parent,
    )

    staging = Path(staging_name)

    try:
        digest = hashlib.sha256()
        total_bytes = 0

        with source_file.open("rb") as source:
            with os.fdopen(fd, "wb") as output:
                for chunk in iter(
                    lambda: source.read(1024 * 1024),
                    b"",
                ):
                    digest.update(chunk)
                    total_bytes += len(chunk)
                    output.write(chunk)

                output.flush()
                os.fsync(output.fileno())

        if (
            total_bytes != manifest["database_bytes"]
            or not hmac.compare_digest(
                digest.hexdigest(),
                manifest["sha256"],
            )
        ):
            raise ValueError(
                "Restored SQLite copy differs from snapshot"
            )

        if _inspect_database(staging) != manifest["tables"]:
            raise ValueError(
                "Restored SQLite table counts mismatch"
            )

        # Atomic, non-overwriting publication.
        # os.link raises FileExistsError if another process
        # created the target while restoration was running.
        _check_no_sidecars(target)
        os.link(staging, target)

        return target

    finally:
        staging.unlink(missing_ok=True)
