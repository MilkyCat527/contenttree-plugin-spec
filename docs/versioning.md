# Versioning

This repository has **two independent version axes**. Confusing them
is the single most common integration mistake for consumers of this
contract, so this document is explicit about both and about how (not)
they interact.

## Axis 1: `contract_version` (the wire protocol)

- A small integer, currently `1` or `2`
  (`schemas/common/fields.schema.json#/$defs/contractVersion`), carried
  inside every manifest (`schemas/manifest.schema.json`) and every
  invoke request/response body.
- `contract_version: 1` — synchronous-only contract. See
  `docs/protocol.md`.
- `contract_version: 2` — adds the deferred completion protocol
  (callback events, operation status polling, browser continuation).
  See `docs/protocol.md`.
- `contract_version` is a **wire-level capability flag**, not a
  repository release identifier. A plugin manifest declares which
  `contract_version` it implements; a host uses that to decide which
  schemas/behaviors to expect from that plugin. Multiple different
  releases of this repository (see Axis 2) may describe the exact same
  set of `contract_version` values, if no *breaking* change to the wire
  contract was needed.
- New `contract_version` integers are introduced only for **breaking**
  changes to the wire contract's required shape or semantics (e.g. a
  hypothetical future `contract_version: 3`). Non-breaking additions
  (new optional fields, new documentation, clarified prose) do **not**
  require a new `contract_version` — they are expressed instead via
  Axis 2 (a repository release) while `contract_version` stays the
  same.
- **Compatibility policy**: within a single `contract_version`, this
  repository's schemas may only change in backwards-compatible ways
  (e.g. adding a new optional property, loosening a constraint,
  clarifying description text) — never by adding a new required
  property, removing/renaming an existing property, tightening an
  existing constraint an already-valid payload could violate, or
  changing an enum's accepted values in an incompatible way. Any change
  that would invalidate a previously-valid, real-world payload requires
  a new `contract_version`.

## Axis 2: repository semantic version

- This repository (`contenttree-plugin-spec`) is versioned
  independently via tags/releases, starting at `v0.1.0-draft.1` (see
  `CHANGELOG.md`, which follows [Keep a
  Changelog](https://keepachangelog.com/en/1.1.0/)).
- Pre-1.0 (`0.y.z` and `0.y.z-draft.n`) releases MAY still contain
  breaking changes to *non-normative* artifacts (documentation
  restructuring, `$id` URL changes, added examples) while the
  underlying `contract_version` schemas remain wire-compatible; treat
  anything before `1.0.0` as a draft whose exact schema `$id`s and file
  layout could still move, though the *wire semantics* described by
  Axis 1 are the more load-bearing compatibility promise even pre-1.0.
- Once this repository reaches `1.0.0`, ordinary [SemVer
  2.0.0](https://semver.org/) rules apply to the *repository* itself:
  - **MAJOR** — any breaking change to schemas, OpenAPI documents, or
    documented behavior for an *already-published* `contract_version`
    (this should be rare/exceptional post-1.0, since Axis 1's own
    compatibility policy above is meant to absorb most of this via a
    new `contract_version` instead); or removal of support for a
    previously-published `contract_version` value.
  - **MINOR** — introduction of a new `contract_version` value, or any
    backwards-compatible addition (new optional schema property, new
    documentation section, new non-normative example) to an existing
    `contract_version`.
  - **PATCH** — clarifications, typo fixes, non-normative documentation
    edits, and any change that does not alter the set of valid/invalid
    payloads for any `contract_version`.
- The relationship is many-to-one in both directions across the
  repository's lifetime: many repository releases can describe the
  same `contract_version` set, and (looking forward) a single
  repository MAJOR release could in principle introduce more than one
  new `contract_version` value at once, though in practice this
  repository expects to introduce at most one new `contract_version`
  per MAJOR release.

## Stack sequencing note (S1 / S2)

This repository's own delivery is itself sequenced as a stack of pull
requests against a shared base:

- **S1** (this PR) — licensing, schemas (`schemas/`), OpenAPI documents
  (`openapi/`), and documentation (`docs/`) only. No SDK, no fixtures,
  no test suite, no CI, no issue templates.
- **S2** (stacked on top of S1) — adds the conformance fixture set and
  the pytest-based conformance suite that exercises the deterministic
  HMAC vectors published in `docs/security.md`, the schemas, and the
  OpenAPI documents from S1. S2 does not change any S1 schema's
  normative meaning; it only adds tests, fixtures, and the supporting
  tooling to run them.

This sequencing is a **delivery/process** detail of how this
repository's own history was built, not part of the wire protocol
itself — `contract_version` and this repository's semantic version
(Axis 1/Axis 2 above) are unaffected by which S-numbered PR a given
change first landed in.
