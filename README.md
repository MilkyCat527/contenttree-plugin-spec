# contenttree-plugin-spec

Permissively licensed, domain-neutral contract artifacts for host/plugin
integrations: JSON Schema (Draft 2020-12), OpenAPI 3.1 documents,
protocol/security/state-machine/versioning documentation, and (in the
conformance stack) fixtures + a pytest-based conformance suite.

This repository is the **single source of truth** for the wire contract
between a "host" and a "plugin" that exposes actions with either
synchronous or deferred ("long-running") completion semantics. It is
published under Apache-2.0 so that independent host and plugin
implementations can consume the schemas without needing to share, fork,
or reimplement each other's code.

## Why this repository exists

Long-running plugin actions (human-in-the-loop steps, external job
queues, asynchronous provider callbacks, etc.) need a precise,
implementation-agnostic contract so that:

- Hosts can validate what a plugin manifest declares before invoking it.
- Plugins can validate invoke requests and produce well-formed responses.
- Both sides can exchange completion events / poll operation status with
  an unambiguous, monotonic state machine.
- Callback and status requests can be authenticated without a shared
  session, using deterministic HMAC signing schemes.
- Browser-based continuation flows (e.g. a plugin needing user
  interaction in a new tab) have a narrow, auditable handoff mechanism.

## Repository layout

```
LICENSE                     Apache-2.0 license text
NOTICE                       Attribution / independent-authorship notice
CHANGELOG.md                 Keep-a-Changelog style history
docs/
  protocol.md                 End-to-end protocol narrative (v1 + v2)
  security.md                 HMAC signing, JWKS/assertion exchange, TLS/redirect rules
  state-machine.md             Plugin-reportable states + transition matrix
  versioning.md                contract_version vs. repo semver, compatibility policy
schemas/
  common/fields.schema.json    Shared $defs (identifiers, timestamps, enums, URLs, progress)
  manifest.schema.json         Unified plugin manifest schema (contract_version 1 or 2)
  v1/                          Synchronous-only invoke contract
  v2/                          Deferred completion protocol (invoke, callback, status, JWT exchange)
openapi/
  plugin-host-api.yaml         API surface exposed BY THE HOST (deferred completion callback only)
  plugin-api.yaml               API surface exposed BY THE PLUGIN (invoke, operation status, assertion exchange)
```

> Note: the browser continuation "assertion exchange" endpoint
> (`POST /auth/contenttree/exchange`) is hosted **by the plugin** (the
> host issues the assertion, the plugin's own origin verifies and
> consumes it), see `openapi/plugin-api.yaml` and `docs/security.md`.

## Versioning

- The **repository** follows its own semantic version, starting at
  `v0.1.0-draft.1` (see `docs/versioning.md` and `CHANGELOG.md`).
- The **wire protocol** carries its own small integer
  `contract_version` (`1` or `2`) inside the manifest and invoke
  payloads. Repository releases and `contract_version` bumps are
  independent: many repository releases may describe the same
  `contract_version`.

## Validating the artifacts

All JSON Schema documents are Draft 2020-12 and all `$ref`s resolve to
files inside this repository only — no network access is required or
performed at validation/test time. See `tests/` (added in the
conformance stack, `test/deferred-contract-conformance` branch) for the
pytest suite, or run a quick manual check:

```bash
python3 -c "
import json, pathlib
from jsonschema import Draft202012Validator
for p in pathlib.Path('schemas').rglob('*.schema.json'):
    Draft202012Validator.check_schema(json.loads(p.read_text()))
print('schemas OK')
"
```

## Non-goals (G3)

This repository intentionally contains **no SDK and no reference
implementation code**. Implementation repositories (hosts, plugins) may
*consume* these schemas/OpenAPI documents as a dependency, but no
implementation code is shared between this repository and any
implementation repository, and none was inspected while authoring this
contract.

## License

Apache License 2.0 — see `LICENSE` and `NOTICE`.
