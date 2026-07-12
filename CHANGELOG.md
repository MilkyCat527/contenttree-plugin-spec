# Changelog

All notable changes to this repository are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to a pre-1.0 draft versioning scheme described in
`docs/versioning.md`.

## [Unreleased]

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
