# TraceMemory Execution Receipt — open spec v1

An Execution Receipt is a portable, cryptographically signed, independently
verifiable record of what an agent run did. It is designed to be verified
**offline, without trusting the TraceMemory server**.

## Contents

The signed `receipt` body contains:
- `receipt_version` — `tracememory.receipt/v1`
- `task_id`, `trace_id`, `agent_id`
- `task_contract` — original goal, approved scope, forbidden actions, task version
- `execution` — status, failure type, tool calls, and a SHA-256 of the final output
- `checkpoints` — the recoverable states for the run
- `recovery` — whether the run was restored from a checkpoint
- `memory` — lessons derived from the run (rule, confidence, derivation)

## Signing

1. The `receipt` body is encoded canonically: JSON with `sort_keys=true`,
   `separators=(",", ":")`, UTF-8. (Verifiers MUST reproduce this exactly.)
2. `content_sha256` = SHA-256 of the canonical bytes.
3. `signature_ed25519_b64` = Ed25519 signature over the same canonical bytes.
4. `public_key_ed25519_b64` = the signer's Ed25519 public key.

## Verifying (offline)

Recompute the canonical encoding of `receipt`, recompute its SHA-256, and verify
`signature_ed25519_b64` against it with the public key. If both the hash matches
and the signature is valid, the receipt is authentic and untampered.

A reference verifier ships at `tools/verify_receipt.py`:

```
python3 tools/verify_receipt.py receipt.json
```

It depends only on the `cryptography` package — not on the TraceMemory server.

## API

- `GET /api/traces/{trace_id}/receipt` — fetch the signed receipt for a run.
- `GET /api/receipts/public-key` — fetch the signer's Ed25519 public key.

## Why this is a standard, not a feature

Durable-execution tools can resume a run; none emit a portable, signed proof of
*what the run did* that a third party can verify without trusting the vendor.
The receipt is the atom other tools, auditors, and benchmarks can build on:
the same format can be scored by a reliability benchmark and used as evidence of
cross-run self-improvement.
