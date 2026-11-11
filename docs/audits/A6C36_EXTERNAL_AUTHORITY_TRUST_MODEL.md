# A6c.36 — External Authority Trust Model

Status: DESIGN CONTRACT ONLY — NOT IMPLEMENTED

## 1. Scope

This document defines prerequisites for a future independent
authority to examine US pilot trusted-head advancement.

The existing local pipeline verifies SQLite, checkpoints,
authority transition evidence, CAS intent, decision request,
and local preconditions.

A local precheck is never authorization.

BIST V2.0.1 production must remain unchanged.
US status remains BOOTSTRAP_ONLY.
Live provider, scheduling and publication remain disabled.

## 2. Current boundary

Latest validated repository phase: A6c.35.

Local status:
LOCAL_PRECHECK_PASSED_EXTERNAL_AUTHORITY_REQUIRED

This status cannot grant privileges or advance trusted state.

External authentication: NOT ESTABLISHED
Independent protected-state storage: NOT ESTABLISHED
Trusted authority clock: NOT ESTABLISHED
Durable nonce registry: NOT ESTABLISHED
Authenticated authority decision: NOT ESTABLISHED
Atomic compare-and-swap: NOT IMPLEMENTED

## 3. Required independent trust roots

A future authority must control and authenticate:

- Its own signing and verification key material.
- Its current protected authority state.
- Its monotonic authority generation.
- Its trusted time source.
- Its durable nonce and operation-ID registry.
- Its authorization policy and permitted identities.

Caller-supplied hashes, timestamps and booleans are
not trusted observations.

No private signing keys or provider credentials may
be committed to the repository.

## 4. Mandatory verification sequence

Before considering any state transition, an external
authority must:

1. Authenticate the caller and authorize the operation
   for the specific US pilot and permitted scope.
2. Obtain the current protected state from its own
   independently controlled, strongly consistent store.
3. Compare the expected state SHA-256 and generation
   with that protected state.
4. Independently verify source provenance and the
   required file-backed evidence.
5. Reconstruct the transition review, CAS operation,
   execution boundary and decision request identities.
6. Validate the request against an authority-controlled
   clock and an authority-controlled nonce registry.
7. Apply the explicit authority authorization policy.
8. Recheck all atomic preconditions immediately before
   mutation.
9. Execute the protected-state CAS and required nonce
   consumption atomically, or commit neither.
10. Produce a verifiable immutable transaction receipt.

Any missing prerequisite must fail closed.

## 5. Atomic transaction requirements

The transaction must conditionally compare:

- Current protected state identity.
- Current authority generation.
- Expected head checkpoint identity.
- Relevant operation and nonce uniqueness constraints.

On success, it must durably record:

- Candidate state and incremented generation.
- Accepted operation and consumed nonce.
- Authenticated decision provenance.
- Immutable audit information.

A stale request must not overwrite a newer authority state.

An interrupted, ambiguous or failed transaction must
never be represented as completed without independently
verifying the committed outcome.

Retry and idempotency behavior must be explicitly specified
and tested against concurrent submissions.

## 6. Failure modes requiring tests

- Forged approval or self-attested signature.
- Caller-controlled protected-state reference.
- Stale generation and rollback attempts.
- Reused nonce or replayed request.
- Expired request against real trusted UTC.
- Duplicate concurrent CAS operations.
- Lost responses after a successful transaction.
- Partial nonce consumption or partial state mutation.
- Unauthorized identity or privilege escalation.
- Modified SQLite, checkpoint or recovery evidence.
- Authority-store unavailability.
- Tampered or missing audit receipt.

## 7. Integration decisions still open

The implementation must select and document:

- Protected transactional storage backend.
- Authentication and authorization mechanism.
- Key-management and trust-root ownership.
- Authoritative time and nonce strategy.
- Atomic CAS and receipt persistence semantics.
- Operational recovery and audit-retention policy.

No backend is selected by this document.

## 8. Non-goals

This design does not:

- Implement an external authority.
- Approve any stock universe or trading signal.
- Grant a trusted-head advancement.
- Establish a real signed authorization.
- Consume a production nonce.
- Perform any protected-state CAS.
- Enable production, live ingestion or publishing.

## 9. Acceptance gate for future implementation

Production advancement must remain blocked until
all external trust requirements are implemented,
tested against a real protected backend, independently
reviewed and explicitly approved.

Passing local tests alone is insufficient.
