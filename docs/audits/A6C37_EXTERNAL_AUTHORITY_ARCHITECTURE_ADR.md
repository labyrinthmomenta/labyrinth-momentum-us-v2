# A6c.37 — External Authority Architecture ADR

Status: PROPOSED — REVIEW_REQUIRED — NOT_DEPLOYED

Related contract:
A6C36_EXTERNAL_AUTHORITY_TRUST_MODEL.md

## 1. Decision context

The current US pilot pipeline performs extensive local
evidence reconstruction and identity verification.

Last completed phase: A6c.36.

Current tests: 572 passed.

Current authority status:
LOCAL_PRECHECK_PASSED_EXTERNAL_AUTHORITY_REQUIRED

Local prechecks are not authorization.

An external authority, protected transactional state,
authenticated approval, trusted time and durable replay
protection are not implemented.

This ADR proposes an architecture, not a deployment.

## 2. Proposed architecture

Preferred candidate:

- A separate authority service.
- A separately administered PostgreSQL database.
- Workload identity authenticated by an independent
  identity provider.
- Server-side authorization using deny-by-default policy.
- Externally controlled KMS/HSM for receipt signing.
- Authority-controlled time and nonce handling.
- Independently accessible immutable evidence objects.

No cloud provider or vendor is selected.

No existing local Python module gains authority by
being imported or called by this service.

## 3. Trust boundary

The client application may propose a transition.

The client must not be able to:

- Write the protected authority state directly.
- Claim its own identity is authenticated.
- Supply an authoritative current generation.
- Supply trusted UTC.
- Mark a nonce as consumed.
- Produce a valid authority receipt.
- Grant production authorization.

The external authority must control every one of
these privileged operations.

## 4. Transactional state

Proposed conceptual records:

AuthorityHead:
- Stream identity
- State SHA-256
- Generation
- Head checkpoint SHA-256
- Pilot manifest SHA-256
- Updated timestamp

ConsumedRequest:
- Decision request identity
- Nonce
- Operation identity
- Authority decision result
- Transaction identity

AuditReceipt:
- Transaction identity
- Before/after protected state
- Authenticated principal
- Decision provenance
- Commit result
- Server timestamp
- Cryptographic receipt identity

Exact database schemas are NOT approved by this ADR.

## 5. Atomicity requirements

The authority must use a single durable transaction
for conditional state advancement and nonce consumption.

Within its transaction, the authority must:

1. Lock or conditionally compare the current state.
2. Verify expected state SHA-256 and generation.
3. Verify current checkpoint and manifest identity.
4. Check the operation and nonce constraints.
5. Recheck the authority-controlled validity window.
6. Apply server-side authorization policy.
7. Conditionally update to generation +1.
8. Consume the nonce and record the operation.
9. Persist an auditable transaction result.
10. Commit all changes or none.

Unique constraints, transactional isolation and
concurrent request behavior must be tested.

A successful local precheck never bypasses this process.

## 6. Authentication and authorization

Candidate mechanism:

- Identity-provider-issued workload credentials.
- Explicit issuer, audience and identity verification.
- Short-lived credentials and key rotation.
- Server-side principal-to-policy mapping.
- Least-privilege database credentials.
- No client-supplied approval booleans.
- No private signing keys in Git or runtime snapshots.

The authority must deny unknown, expired, revoked
or unauthorized identities.

Authenticated identity does not itself imply approval.

## 7. Cryptographic receipts

After an independently verified transaction, the
authority should be capable of producing a receipt
using externally controlled signing keys.

Receipts must bind:

- Transaction and operation identity.
- Decision request identity.
- Before/after state identities.
- Generation transition.
- Authority identity and policy version.
- Committed transaction result.

Signature verification must use an independently
trusted authority public key or trust chain.

A locally computed SHA-256 is not a signature.

A claimed signed receipt must not be treated as
evidence of commitment until independently verified.

## 8. Time and replay protection

The authority must obtain time independently of
the decision-request caller.

The authoritative time source must be:

- UTC-based.
- Monitored for clock drift.
- Protected against caller substitution.
- Evaluated within the protected transaction.

Nonce uniqueness must be enforced by durable storage.

Decision-request ID and operation-ID behavior must
be defined for retries and idempotency.

A lost response after commit must be resolved by
checking the authoritative transaction result.

A retry must never create a second state transition.

## 9. Evidence independence

The authority must not trust client-supplied file
paths as evidence provenance.

An authority-controlled evidence retrieval mechanism
must independently retrieve and hash the required:

- SQLite snapshot.
- Checkpoint.
- Authority-state evidence.
- Pilot manifest.
- Relevant provenance and recovery records.

Object-store metadata alone is not sufficient to
replace cryptographic content verification.

The evidence store's trust boundaries, immutability
and access permissions require separate review.

## 10. Alternatives

Alternative A:
Managed transactional database with a dedicated
authority service.

Advantages:
- Explicit transaction boundaries.
- Constraints and concurrency testing.
- Portable application architecture.

Risks:
- Separate hosting and administration required.
- Strong access control and operations required.

Alternative B:
Cloud-native transactional conditional-write store.

Advantages:
- Managed scalability and availability.
- Potentially strong conditional-write primitives.

Risks:
- Backend-specific transaction limitations.
- Receipt and nonce atomicity require careful design.
- Increased provider coupling.

Rejected as real independent authority:
A SQLite database in the existing client environment.

Reason:
It does not create an independent protected trust
boundary merely by enabling WAL or transactions.

SQLite remains useful for offline test fixtures.

## 11. Required implementation gates

Before implementation:

- Select the authority hosting and ownership model.
- Select the external transactional backend.
- Define authenticated principal and authorization policy.
- Define protected state and evidence-store ownership.
- Define trusted clock and nonce persistence.
- Define transaction isolation and crash recovery.
- Define receipt signing and verification.
- Define audit retention and administrative separation.

Before production:

- Run adversarial concurrency tests.
- Verify rollback and replay resistance.
- Test partial failures and lost responses.
- Test compromised/untrusted client inputs.
- Independently review keys and permissions.
- Obtain explicit production approval.

## 12. Current non-goals

This ADR does not:

- Deploy PostgreSQL or any other database.
- Create an authority service.
- Provision KMS/HSM keys.
- Set up identity provider credentials.
- Establish a trusted external clock.
- Execute a production transaction.
- Consume a durable production nonce.
- Sign an authority decision.
- Advance a trusted head.
- Enable US production or publishing.

BIST V2.0.1 production remains unchanged.

US status remains BOOTSTRAP_ONLY.

## 13. Decision status

Architecture candidate:
Separately administered PostgreSQL-backed authority
service, with independently authenticated workload
identity and externally controlled signing keys.

Decision: PROPOSED ONLY.

Backend ownership, hosting, credentials and deployment
must be established before implementing real authority.

Local Python tests cannot certify an unprovisioned
external trust boundary.
