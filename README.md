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
  manifest.schema.json         Unified plugin manifest schema (manifest_version 1; supported_contract_versions + per-extension_point completion_mode/interaction_mode)
  v1/                          Always-synchronous invoke contract
  v2/                          Sync- (default) or deferred-capable protocol (invoke, callback, status, JWT exchange)
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
  `contract_version` (`1` or `2`) inside every invoke payload. A
  manifest does not carry a singular `contract_version`; it advertises
  `supported_contract_versions` instead (see `docs/versioning.md`).
  Repository releases and `contract_version` bumps are independent:
  many repository releases may describe the same `contract_version`.

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

### Running the full conformance suite

The `test/deferred-contract-conformance` branch (stacked on top of this
one, PR base = this branch) adds an independently authored pytest suite —
no SDK, no product implementation code. To run it:

```bash
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m pytest tests/ -q
```

Requires Python 3.10+. The suite:

- parses every JSON/YAML artifact and validates each schema against
  `Draft202012Validator.check_schema`;
- resolves every schema and OpenAPI `$ref` **locally only** (a
  `retrieve` callback raises instead of falling back to the network),
  and additionally blocks all outbound sockets for the whole test
  session as a defense-in-depth guard;
- applies `jsonschema.FormatChecker` (date-time, uri, etc.) to fixtures
  and targeted schema probes;
- validates both OpenAPI 3.1 documents structurally (paths, methods,
  security schemes, headers, response codes);
- validates ~70 hand-authored valid/invalid fixtures
  (`fixtures/`) against the schemas via an external index
  (`fixtures/index.json`) that keeps target-schema metadata **outside**
  each fixture instance — never an in-band `__schema__` property, which
  the `additionalProperties: false` schemas would reject anyway;
- pins the exact 11-property G1 whitelist shared by the completion
  event and operation status shapes (`additionalProperties: false`,
  identical property sets except the `sequence` minimum);
- encodes the documented state-machine transition matrix as test-local
  guard data (not a reference implementation) and asserts terminal-state
  freeze plus the `running` → `awaiting_user` rejection rule;
- independently recomputes all three HMAC vectors documented in
  `docs/security.md` from a frozen fixture
  (`fixtures/security/hmac-vectors.json`) and fails if the docs and the
  fixture ever drift apart;
- checks the `hostApiBaseUrl` HTTPS-origin rule (including the
  localhost/127.0.0.1 test exception), interaction-assertion required
  claims, and exact callback response field shapes.

CI (`.github/workflows/validate.yml`) runs the same suite on every push
and pull request across Python 3.10–3.12, with pip dependency caching
and a minimal `permissions: contents: read` block.

## Non-goals (G3)

This repository intentionally contains **no SDK and no reference
implementation code**. Implementation repositories (hosts, plugins) may
*consume* these schemas/OpenAPI documents as a dependency, but no
implementation code is shared between this repository and any
implementation repository, and none was inspected while authoring this
contract.

## License

Apache License 2.0 — see `LICENSE` and `NOTICE`.
