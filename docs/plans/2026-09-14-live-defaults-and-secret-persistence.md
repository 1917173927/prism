# Working Plan

## Goal

Remove locally fixable false-LIVE and restart-loss behavior before external credentials are supplied. Preserve explicit demo/test fixtures, but prevent LIVE requests from silently consuming them.

## Context / Constraints

- Existing Fuyao server credentials are available; Wencai credentials and contract verification are not.
- LIVE failures must fail closed and must never be relabelled fixture output.
- User secrets must not be written in plaintext, returned by APIs, logged, or committed.
- Existing user-owned untracked files must remain untouched.

## Design

Two approaches were considered:

1. Persist secrets directly in SQLite with an application encryption key. This is portable, but still requires securely provisioning another master key.
2. Use the operating-system secret protection facility and persist only protected blobs plus non-secret metadata. This is the smallest secure local-Windows design and leaves environment variables as the deployment fallback.

Use approach 2 for the current local product. Keep the storage interface injectable so a deployment secret manager can replace it later.

## Changes

1. Add an owner-scoped protected secret store and regression tests.
2. Persist user LLM settings across restarts without exposing API keys.
3. Add protected provider settings for server-wide Fuyao and Wencai credentials.
4. Make explicit LIVE routes fail closed when only fixture research implementations are available.
5. Reuse existing real Fuyao endpoints for the supported stock/fund paths; retain explicit unsupported states for missing fundamentals and Wencai-dependent research.
6. Update deployment documentation, LOG, and TODO.

## Verification

- Focused unit and API integration tests for restart persistence, owner isolation, deletion, redaction, invalid protected data, and LIVE fixture refusal.
- Full pytest suite under the supported Python 3.12 environment.
- Python compilation, JavaScript syntax validation, diff check, and a real Fuyao smoke request.
- Independent post-implementation sub-agent review for security, Mock leakage, and test validity.
