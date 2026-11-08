"""Fail-closed, offline verified SQLite checkpoint advancement.

Combines independently pinned checkpoint metadata assessment
with actual SQLite snapshot and checkpoint verification.

Successful results are proposals only:
- No trusted head is updated.
- No new snapshot is created.
- No external trust authority is established.
- No live ingestion or production publication is enabled.

For a non-genesis current checkpoint, callers must supply
its independently trusted predecessor SHA-256 explicitly.
"""

from datetime import date
import hashlib
import hmac
from pathlib import Path

from src.data.snapshot_checkpoint import (
    verify_snapshot_checkpoint,
)
from src.data.trusted_checkpoint_advancement import (
    assess_checkpoint_advance,
)


def _check_snapshot_directory(path, label):
    snapshot = Path(path)

    if snapshot.is_symlink():
        raise ValueError(
            f"Symlinked {label} snapshot is forbidden"
        )

    if not snapshot.is_dir():
        raise ValueError(
            f"Missing or invalid {label} snapshot"
        )

    return snapshot


def _same_sha256(left, right):
    return hmac.compare_digest(left, right)


def assess_verified_snapshot_advance(
    *,
    current_checkpoint_path,
    current_snapshot_dir,
    candidate_checkpoint_path,
    candidate_snapshot_dir,
    trusted_current_head_sha256,
    expected_candidate_sha256,
    expected_pilot_manifest_sha256,
    required_symbols,
    min_candidate_as_of: date,
    expected_current_predecessor_sha256=None,
) -> dict:
    """Verify a forward transition AND both real SQLite snapshots.

    All checkpoint SHA-256 values must be independently pinned
    by the caller. Snapshot SHA-256 values are authenticated
    through the pinned checkpoint bytes.

    The current checkpoint defaults to genesis (no predecessor).
    For a subsequent current head, explicitly provide its
    independently trusted predecessor SHA-256.

    Does not modify files or grant approval to advance the
    authoritative checkpoint head.
    """

    # Reject unsafe or missing snapshot directories before
    # evaluating any checkpoint metadata.
    current_snapshot = _check_snapshot_directory(
        current_snapshot_dir,
        "current",
    )

    candidate_snapshot = _check_snapshot_directory(
        candidate_snapshot_dir,
        "candidate",
    )

    if (
        current_snapshot.resolve()
        == candidate_snapshot.resolve()
    ):
        raise ValueError(
            "Current and candidate snapshots must differ"
        )

    # Stage 1: independently pinned metadata and forward
    # predecessor/date/symbol/snapshot-ID checks.
    proposal = assess_checkpoint_advance(
        current_checkpoint_path=current_checkpoint_path,
        candidate_checkpoint_path=candidate_checkpoint_path,
        trusted_current_head_sha256=(
            trusted_current_head_sha256
        ),
        expected_candidate_sha256=(
            expected_candidate_sha256
        ),
        expected_pilot_manifest_sha256=(
            expected_pilot_manifest_sha256
        ),
        required_symbols=required_symbols,
        min_candidate_as_of=min_candidate_as_of,
    )

    if proposal["status"] != "VALIDATED_PROPOSAL_ONLY":
        raise ValueError(
            "Checkpoint metadata was not validated"
        )

    current_as_of = date.fromisoformat(
        proposal["previous_as_of"]
    )

    candidate_as_of = date.fromisoformat(
        proposal["candidate_as_of"]
    )

    # Stage 2: verify actual current SQLite snapshot,
    # status records and independently pinned checkpoint.
    #
    # None means a genesis checkpoint is required.
    # Non-genesis callers must explicitly pin the predecessor.
    verified_current = verify_snapshot_checkpoint(
        checkpoint_path=current_checkpoint_path,
        snapshot_dir=current_snapshot,
        trusted_checkpoint_sha256=(
            trusted_current_head_sha256
        ),
        expected_pilot_manifest_sha256=(
            expected_pilot_manifest_sha256
        ),
        required_symbols=required_symbols,
        min_as_of=current_as_of,
        expected_previous_checkpoint_sha256=(
            expected_current_predecessor_sha256
        ),
    )

    # Stage 3: verify the actual candidate SQLite database.
    #
    # This is essential: matching checkpoint metadata is
    # insufficient if symbol status/history is incomplete.
    try:
        verified_candidate = verify_snapshot_checkpoint(
            checkpoint_path=candidate_checkpoint_path,
            snapshot_dir=candidate_snapshot,
            trusted_checkpoint_sha256=(
                expected_candidate_sha256
            ),
            expected_pilot_manifest_sha256=(
                expected_pilot_manifest_sha256
            ),
            required_symbols=required_symbols,
            min_as_of=candidate_as_of,
            expected_previous_checkpoint_sha256=(
                trusted_current_head_sha256
            ),
        )
    except ValueError as exc:
        # The underlying trusted snapshot verifier rejects
        # an old last_session as "Stale snapshot history".
        # Present this as an incomplete checkpoint status,
        # while preserving the original exception and reason.
        if str(exc).startswith("Stale snapshot history:"):
            raise ValueError(
                "Incomplete checkpoint status: "
                + str(exc)
            ) from exc

        raise

    # Stage 4: assert that both verified checkpoints
    # describe exactly the approved metadata proposal.
    if (
        verified_current["as_of"]
        != proposal["previous_as_of"]
    ):
        raise ValueError(
            "Current checkpoint date changed"
        )

    if (
        verified_candidate["as_of"]
        != proposal["candidate_as_of"]
    ):
        raise ValueError(
            "Candidate checkpoint date changed"
        )

    if (
        verified_candidate["previous_checkpoint_sha256"]
        != trusted_current_head_sha256
    ):
        raise ValueError(
            "Candidate predecessor changed"
        )

    if (
        verified_candidate["snapshot_id"]
        != proposal["candidate_snapshot_id"]
    ):
        raise ValueError(
            "Candidate snapshot identity mismatch"
        )

    if not _same_sha256(
        verified_candidate["snapshot_sha256"],
        proposal["candidate_snapshot_sha256"],
    ):
        raise ValueError(
            "Candidate snapshot SHA-256 mismatch"
        )

    if _same_sha256(
        verified_current["snapshot_sha256"],
        verified_candidate["snapshot_sha256"],
    ):
        raise ValueError(
            "Candidate reuses current SQLite snapshot"
        )

    if (
        verified_current["production_approved"] is not False
        or verified_candidate["production_approved"] is not False
    ):
        raise ValueError(
            "Production approval is forbidden"
        )

    # The original assessment only returns a proposal.
    # Completing real snapshot verification does not
    # authorize or perform a trusted head update.
    return {
        **proposal,
        "status": "VERIFIED_SNAPSHOT_PROPOSAL_ONLY",
        "production_approved": False,
    }
