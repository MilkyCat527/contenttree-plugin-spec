# Changelog

All notable changes to this repository are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to a pre-1.0 draft versioning scheme described in
`docs/versioning.md`.

## [Unreleased]

### Added

- `test/deferred-contract-conformance` (S2): independently authored
  pytest conformance suite for the schemas/OpenAPI/docs published in
  `feat/deferred-contract-schema` — no SDK, no product implementation
  code consulted or shared.
  - `tests/` — 9 modules covering schema validity (Draft 2020-12
    `check_schema` + local-only `$ref` resolution), an index-driven
    fixture validator, OpenAPI 3.1 structural checks for both
    `openapi/*.yaml` documents, the exact 11-property G1 event
    whitelist (completion event / operation status), a state-machine
    transition-matrix guard (test-local data only, not a reference
    implementation) including terminal-state freeze and the
    `running` → `awaiting_user` rejection rule, independent
    recomputation of all three documented HMAC vectors with
    docs-vs-fixture drift detection, `hostApiBaseUrl` HTTPS-origin /
    localhost-exception rules, interaction-assertion claim
    requirements, callback response field shapes, and explicit
    no-network / no-product-repo guards.
  - `fixtures/` — ~70 hand-authored valid/invalid instances spanning
    manifest v1/v2, v1 request/response, v2 invoke request + accepted
    response variants (launch/nonlaunch), completion event, operation
    status (seq0/seq1), callback response, and interaction assertion
    claims/exchange, indexed externally via `fixtures/index.json`
    (target schema + expected outcome kept outside each instance) and
    `fixtures/security/hmac-vectors.json` (frozen HMAC vectors mirrored
    from `docs/security.md`).
  - `pyproject.toml` / `requirements.txt` — pinned, pure-PyPI test
    dependencies (pytest, jsonschema, referencing, PyYAML,
    rfc3339-validator, rfc3987); no git/path dependencies.
  - `.github/workflows/validate.yml` — runs the suite on push/PR across
    Python 3.10–3.12 with pip dependency caching and
    `permissions: contents: read`.
  - `.github/ISSUE_TEMPLATE/schema-field-proposal.yml` (mandatory G1
    rationale) and `.github/ISSUE_TEMPLATE/bug-report.yml`;
    `.github/PULL_REQUEST_TEMPLATE.md` with a G1/G3 checklist.
  - `README.md` — added a "Running the full conformance suite" section
    with exact install/run commands.

  This entry documents work-in-progress on an unreleased branch; no new
  repository version has been tagged or published.

### Fixed

- **Blocking compatibility correction** to the wire shapes introduced
  in `0.1.0-draft.1`, which had reinvented several shapes incompatibly
  with the platform/plugin protocol documents authoritative for this
  contract. This release **retracts** the following prior claims and
  replaces them with the normative shapes:
  - `schemas/manifest.schema.json`: removed the invented
    manifest-level `contract_version` field and `actions` array.
    Replaced with `manifest_version` (fixed `1`), top-level
    `supported_contract_versions`, top-level path-based `endpoints`
    (`invoke`, optional `operation_status`), required `scopes`, and
    `extension_points` (with per-item, v2-only optional
    `completion_mode`: `sync` default | `deferred`, and
    `interaction_mode`: `none` default | `launch_url`). A manifest with
    any `completion_mode: deferred` extension point now must list `2`
    in `supported_contract_versions` and declare
    `endpoints.operation_status`.
  - `schemas/v1/invoke-request.schema.json`: removed the invented
    `plugin_id` and opaque `input` wrapper. Replaced with the actual
    host export payload shape: `user`, `project_id`, `tree`, `source`,
    optional `skin`/`options`.
  - `schemas/v1/invoke-response.schema.json`: removed the invented
    `{state, result_mode, result_url, provider, error_code,
    error_message}` envelope and its `if`/`then`/`else`. Replaced with
    the normative `{status: "ok"|"failed", error_code?, message?,
    result?: {url?, external_id?}}` envelope, with no conditional
    requirements.
  - `schemas/v2/invoke-request.schema.json`: same correction as v1,
    plus the pre-existing, correct `host_api_base_url` requirement
    (unchanged).
  - `schemas/v2/invoke-accepted-response.schema.json`: removed
    top-level `interaction_mode` from the response body (it is a
    manifest-only, per-extension-point property; its effect on
    `launch_url` presence/absence is a cross-document rule enforced by
    the host, not expressible in this schema alone). Replaced with the
    normative nested `{status: "accepted", result: {operation_id,
    launch_url?, state, result_mode}}` envelope.
  - `schemas/common/fields.schema.json`, `schemas/v2/completion-event.schema.json`,
    `schemas/v2/operation-status.schema.json`: `resultMode` is now
    exactly `mock`|`production` (the plugin's **execution
    environment**), not `none`|`url` (a result-transport mode). All
    `if`/`then`/`else` conditionals coupling `result_mode` to
    `result_url` have been removed; `result_url` is now always
    independently optional wherever it appears.
  - `openapi/plugin-api.yaml`: merged the previously separate
    `/v1/actions/{action_id}/invoke` and `/v2/actions/{action_id}/invoke`
    paths into a single `/actions/{action_id}` path (matching the
    manifest's `endpoints.invoke: "/actions"`), with a `oneOf` request
    body (v1/v2 invoke-request) and status-code-keyed responses (`200`
    → v1 envelope, shared by v1 and v2-sync actions; `202` → v2
    accepted envelope, deferred actions only).
  - `docs/protocol.md`, `docs/security.md`, `docs/versioning.md`,
    `README.md`: updated throughout for the above; `docs/security.md`'s
    Scheme 1 deterministic test vector body/signature were recomputed
    (`result_mode` changed from the retracted `"none"` value to
    `"mock"`).
  - Extension point `type` retains the existing, already-published
    generic `review-export-action` vocabulary (not a new
    courseware-specific constant); no action IDs or vendor names are
    hard-coded anywhere in this correction.

## [0.1.0-draft.1] - 2026-07-12

### Added

- Initial Apache-2.0 licensing (`LICENSE`, `NOTICE`).
- `schemas/common/fields.schema.json` shared identifier/enum/URL/progress
  definitions.
- `schemas/manifest.schema.json` unified plugin manifest schema
  supporting `contract_version` 1 (synchronous-only) and 2 (deferred
  completion protocol).
- `schemas/v1/*` synchronous invoke request/response schemas.
- `schemas/v2/*` deferred completion protocol schemas: invoke request,
  invoke-accepted response variants, completion event, operation status
  snapshot, callback success response, and browser continuation
  interaction-assertion claims + assertion exchange request/response.
- `openapi/plugin-host-api.yaml` — host-exposed API surface (deferred
  completion callback endpoint).
- `openapi/plugin-api.yaml` — plugin-exposed API surface (invoke,
  operation status, browser continuation assertion exchange).
- `docs/protocol.md`, `docs/security.md`, `docs/state-machine.md`,
  `docs/versioning.md`.
- Deterministic HMAC test vectors in `docs/security.md` for both the
  `plugin-to-host` (callback) and `host-to-plugin` (operation status
  poll) signing schemes, fixed for consumption by the `S2` conformance
  suite.

[Unreleased]: https://github.com/MilkyCat527/contenttree-plugin-spec/compare/v0.1.0-draft.1...HEAD
[0.1.0-draft.1]: https://github.com/MilkyCat527/contenttree-plugin-spec/releases/tag/v0.1.0-draft.1
