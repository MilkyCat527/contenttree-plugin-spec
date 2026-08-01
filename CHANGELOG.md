# Changelog

All notable changes to this repository are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to a pre-1.0 draft versioning scheme described in
`docs/versioning.md`.

## [Unreleased]

### Added

- `contract_version: 3` — explicit payload transport. The exported tree
  stops being a top-level `tree` property and moves behind a closed,
  discriminated `payload` descriptor
  (`schemas/v3/payload-descriptor.schema.json`) that is either `inline`
  (document carried on the request) or `pull` (fetched out of band).
  Both modes publish the same integrity metadata — media type, exact byte
  length and SHA-256 over the bytes the host produced — so verification
  does not depend on which transport was chosen, and both branches are
  closed objects, making the modes mutually exclusive structurally rather
  than by convention. Payloads are capped at 50 MiB in the schema itself.
  Everything else about v2 (completion modes, callbacks, status polling,
  browser continuation, response envelopes) is unchanged: implementing v3
  means adding payload handling, not a second protocol. `source.tree_id`
  becomes required so a plugin can log and correlate an invocation before
  downloading anything.
  - `schemas/v3/invoke-request.schema.json`,
    `schemas/v3/payload-descriptor.schema.json`,
    `schemas/v3/host-access-token-claims.schema.json`.
  - `openapi/plugin-host-api.yaml` gains
    `GET /api/plugin-host/v1/invocations/{invocation_id}/payload`: served
    by the host itself (never a redirect or a pre-signed third-party URL),
    all-or-nothing (no `Range`, since a partial body has no well-defined
    digest), `Cache-Control: no-store` plus an
    `X-ContentTree-Payload-SHA256` echo, `401` for both bad credentials
    and unknown invocations so callers cannot enumerate, `403` for a
    token that verifies but does not authorize the read, `410` once
    expired/cleaned up, and `429` once the read budget is exhausted.
  - `openapi/plugin-api.yaml`'s invoke `oneOf` now spans v1/v2/v3.
  - Host Access Token: its own `typ`, signing key, pinned issuer, dual
    audience (logical + concrete host API origin, RFC 8707), a
    `plugin:`-namespaced subject disjoint from any user subject, exactly
    one scope, and a required deployment binding that makes the token
    useless after an upgrade or rollback. The claim set is closed and
    carries no personal data.
  - `docs/security.md` Scheme 3 (`plugin-to-host-api`) with a fourth
    deterministic HMAC vector and its reproduction snippet. Presenting
    the token is necessary but never sufficient: the pull request also
    carries a direction-scoped signature, and the three schemes are
    domain-separated so a signature captured in one direction can never
    be replayed in another.
  - 24 new indexed conformance fixtures plus
    `tests/test_v3_payload_transport.py`, which pins the structural
    guarantees (mode exclusivity, identical integrity metadata, v3 ⊃ v2
    minus the inlined tree, token binding) rather than restating schema
    text.

- Governance surface for risk disclosure, declarative options and hosted
  artifacts (all additive; every new field is optional and every new
  capability defaults to `false`, so existing manifests keep their
  current meaning byte-for-byte):
  - Manifest `data_handling` (`purposes`, `retention` with a
    `none`/`transient`/`stored` mode plus optional day bound,
    `egress_domains`, `subprocessors`, `privacy_url`,
    `processing_location`). Egress entries are exact lowercase FQDNs —
    wildcards, bare single labels, schemes, ports and paths are
    rejected — and an empty array is a positive "no third-party egress"
    declaration. The object has no keyword by which a publisher could
    suppress a category the host derives itself from granted scopes and
    an action's `input_contract`.
  - Manifest `capabilities` (`hmac_keyring`, `payload_pull`) and the
    optional `X-ContentTree-Key-Id` transport header, documented in
    `docs/security.md`: a keyring-capable plugin lets a host overlap two
    HMAC keys during rotation, while a plugin without the capability
    keeps today's single-key behavior and must instead be drained before
    rotation. The header selects a candidate key and never grants trust.
  - `schemas/common/options-schema.schema.json`, a meta-schema pinning
    the restricted per-invocation options subset referenced by each
    extension point's new `options_schema`: closed flat object, ≤20
    scalar-or-scalar-array fields, allowlisted keywords, and a single
    platform-namespaced `x-contenttree-ui.widget` hint. `$ref`, `$defs`,
    `oneOf`/`anyOf`/`allOf`/`not`, `if`/`then`/`else`, `pattern`,
    `patternProperties`, `unevaluatedProperties`, `format` and nested
    objects are rejected outright rather than ignored.
  - `schemas/artifact-descriptor.schema.json` for the
    `contenttree-plugin.json` carried at the root of a hosted artifact:
    `scf-zip-v1` runtime declaration, license/source provenance, an
    in-artifact SBOM path, and a deployment `configuration_schema` whose
    uppercase keys may be marked `x-contenttree-secret`. The descriptor
    intentionally cannot state the digest of the artifact containing it,
    and every artifact-relative path rejects absolute paths, `..`
    segments, backslashes, empty segments and percent encoding.
  - 26 new indexed conformance fixtures plus
    `tests/test_governance_and_artifact_rules.py`, which probes the
    decisions themselves (may a plugin declare this?) rather than
    restating schema text, so a future edit that quietly widens the
    accepted surface fails even when all fixtures still pass.
  - `docs/protocol.md` gains "Publisher risk declaration",
    "Per-invocation options", "Capabilities" and "Hosted artifact
    descriptor" sections; `docs/security.md` gains the
    `X-ContentTree-Key-Id` rotation rules and the options-vs-configuration
    secret boundary.

- Backwards-compatible `contract_version: 2` gateway-mount support:
  v2 invoke requests may now carry the optional
  `host_api_route_prefix`, backed by the shared `hostApiRoutePrefix`
  schema definition. `/NewContentTree` is valid; non-normalized values
  with trailing slashes, query/fragment components, percent encoding,
  backslashes, empty/`.`/`..` segments, schemes, or authorities are
  rejected. `host_api_base_url` remains origin-only, and callback URLs
  are constructed as
  `{host_api_base_url}{host_api_route_prefix or ''}/api/plugin-host/...`.
  OpenAPI, protocol/security/versioning prose, indexed conformance
  fixtures, and transport/security guards cover both prefixed and
  legacy root-mounted requests.
- `schemas/v2/browser-assertion-handoff-location.schema.json` plus
  conformance fixtures now make the fixed, HTTPS, fragment-only
  `#contenttree_assertion=<JWT>` browser handoff machine-readable.
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

### Changed

- Advanced the repository/conformance metadata to `0.2.0` and both
  OpenAPI document versions to `2.1.0` for the backwards-compatible v2
  protocol extension. The integer wire `contract_version` remains `2`.

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
    body (v1/v2 invoke-request) and a single `200` response whose body is
    a `oneOf` (v1 `ok`/`failed` envelope, shared by v1 and v2-sync
    actions; v2 `accepted` envelope, deferred actions only) discriminated
    by the body's own `status` property. **Post-merge audit correction:**
    this path briefly used an invented `202 Accepted` status code for the
    deferred branch instead of the `200` `oneOf` described above; that was
    caught and corrected before this PR merged (see `docs/protocol.md`'s
    "Deferred completion_mode" section) — every business outcome under
    this contract, including `accepted`, is HTTP `200`, matching this
    repository's `4xx`-is-preflight-only convention. No published,
    merged revision of this repository ever advertised `202`.
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
