# Protocol

This document narrates the end-to-end wire protocol for both
`contract_version` 1 (always synchronous) and `contract_version` 2
(synchronous by default, deferred when an extension point's manifest
entry declares `completion_mode: deferred`). It is domain-neutral: it
describes generic host/plugin action invocation, not any specific
action's business logic. All payload shapes referenced here are
normative via the JSON Schema documents under `schemas/`; this document
is descriptive and does not itself impose additional wire constraints
beyond what those schemas already say. Endpoint surfaces are formalized
in `openapi/plugin-host-api.yaml` (host-exposed) and
`openapi/plugin-api.yaml` (plugin-exposed).

## Actors

- **Host** — the system that owns a plugin registry, decides to invoke
  a plugin action, and receives completion events / serves the
  deferred-operation callback endpoint.
- **Plugin** — the system that declares a manifest (`schemas/manifest.schema.json`),
  accepts invoke requests for its actions, and (for deferred actions)
  eventually reports completion via callback and/or answers operation
  status polls.
- **Browser** — the end user's user agent, only relevant for actions
  with `interaction_mode: launch_url` (see "Browser continuation"
  below).

## Manifest and endpoints

A plugin manifest (`schemas/manifest.schema.json`) advertises exactly
one top-level, path-based `endpoints` object — never per-action or
per-`contract_version` endpoints, and never absolute URLs:

- `endpoints.invoke` (always required, documented value: `/actions`) —
  the host `POST`s to `{plugin_base_url}{endpoints.invoke}/{action_id}`
  to invoke any of the plugin's extension points, regardless of which
  `contract_version` the request body uses.
- `endpoints.operation_status` (required if and only if at least one
  extension point declares `completion_mode: deferred`, documented
  value: `/operations/{operation_id}`) — the host `GET`s
  `{plugin_base_url}{endpoints.operation_status}` (with the
  `{operation_id}` template resolved) to poll a deferred operation.

`plugin_base_url` itself is established out of band (e.g. at plugin
registration in the host's own catalog) and is not part of the manifest
schema; see `openapi/plugin-api.yaml`'s `servers` block for the
documentation placeholder.

Each extension point independently declares `completion_mode`
(`sync`, the default, or `deferred`) and `interaction_mode` (`none`,
the default, or `launch_url`). A manifest with any `completion_mode:
deferred` extension point MUST list `2` in its top-level
`supported_contract_versions` array and MUST declare
`endpoints.operation_status` — see `schemas/manifest.schema.json`'s
`if`/`then` conditional. There is no manifest-level `contract_version`
field: contract negotiation is expressed entirely through
`supported_contract_versions`.

## contract_version 1 — always synchronous

1. Host `POST`s a `v1/invoke-request.schema.json` body to
   `{plugin_base_url}{endpoints.invoke}/{action_id}`.
2. The plugin computes the entire result synchronously and returns a
   `v1/invoke-response.schema.json` body as the HTTP response:
   `{"status": "ok"|"failed", "error_code"?, "message"?, "result"?:
   {"url"?, "external_id"?}}`. This is a terminal outcome by
   construction — there is no `state` field and no notion of
   `awaiting_user`/`running` on this envelope; the response itself IS
   the final result.
3. There is no completion event, no operation status polling, and no
   `operation_id` under `contract_version` 1. The protocol interaction
   is exactly one request/response pair.

## contract_version 2 — synchronous (default) or deferred, per action

`contract_version: 2` invoke requests (`v2/invoke-request.schema.json`)
carry every `v1/invoke-request.schema.json` field unchanged, plus a
required `host_api_base_url`: an absolute HTTPS origin (scheme +
host[:port], **no path, query, or fragment** — see
`schemas/common/fields.schema.json#/$defs/hostApiBaseUrl`) at which the
host exposes its plugin-host API for *this specific invocation*.

Gateway-mounted deployments may also include the optional
`host_api_route_prefix` (see
`schemas/common/fields.schema.json#/$defs/hostApiRoutePrefix`), for
example `/NewContentTree`. It is a normalized absolute path prefix:
exactly one leading slash, at least one non-empty segment, and no
trailing slash, query, fragment, percent encoding, backslash, empty
segment, `.` segment, `..` segment, scheme, or authority. A root-mounted
host omits the field; it does not send `""` or `/`.

Plugins MUST construct callback URLs by exact string concatenation as
`{host_api_base_url}{host_api_route_prefix or ''}/api/plugin-host/...`;
they MUST NOT move the route prefix into `host_api_base_url`, resolve
either component as a new URL, decode it, or apply further path
normalization. This separation lets the plugin support a gateway mount
without guessing, hardcoding, or accepting an arbitrary full callback
URL, while `host_api_base_url` remains protected by its origin-only
anti-SSRF rule. The shared HMAC secret used to sign callbacks is
**never** carried in any invoke, callback, or status payload; it is
provisioned out of band during plugin registration.

Whether an invocation completes synchronously or is deferred depends
entirely on the invoked action's own manifest `completion_mode` — never
on anything in the request body itself:

### Sync completion_mode (default)

The plugin responds exactly like `contract_version` 1: a
`v1/invoke-response.schema.json` body, HTTP 200, is the final result.
`contract_version: 2` does not imply deferred completion; it only
*permits* it on a per-action basis.

### Deferred completion_mode

The plugin responds synchronously, **HTTP 200**, with a
`v2/invoke-accepted-response.schema.json` body — an acceptance, not a
result: `{"status": "accepted", "result": {"operation_id", "launch_url"?,
"state": "awaiting_user"|"running", "result_mode": "mock"|"production"}}`.
There is no separate `202 Accepted` status code for this case: the same
single `200` response used by the sync branch above carries this
different body shape instead, and `openapi/plugin-api.yaml` documents
both alternatives as one `oneOf` response body on that one `200`,
discriminated by the body's own `status` property — never by the HTTP
status code, which is always `200` for every business outcome (`4xx` is
reserved for preflight validation failures such as a malformed request
or an unknown `action_id`, never for a *valid* `accepted`/`ok`/`failed`
business result).
`interaction_mode` never appears on this response body: whether
`result.launch_url` must be present, must be absent, or is merely
optional is governed entirely by the invoked action's manifest
`interaction_mode` (`none` vs `launch_url`) — a cross-document rule
enforced by the host, since a single JSON Schema document cannot
reference a separate manifest document's per-action declaration. See
`schemas/v2/invoke-accepted-response.schema.json`'s description for the
same note.

`result_mode` (`mock`|`production`) reports the **execution
environment** the plugin ran (or will run) this operation in — it is
completely independent of whether/how a result artifact is delivered.
It is not a result-transport mode: there is no `none`/`url` variant,
and `result_mode` never conditionally requires or forbids `result_url`
(on this response, on completion events, or on operation status
snapshots). `result_url`, where it appears (completion events,
operation status), is always independently optional.

Invoking an action does not itself create any outbox / completion
event. The first thing the host can observe about this operation's
progress, other than the invoke-accepted response, is either (a) the
operation status endpoint reporting sequence 0, or (b) the plugin's
first callback event at sequence 1.

### 2. Operation status (poll, host → plugin, GET)

`GET {plugin_base_url}{endpoints.operation_status}` with the
`{operation_id}` path template resolved to the concrete operation
(documented concrete shape: `GET
{plugin_base_url}/operations/{operation_id}` — see
`schemas/manifest.schema.json`'s `endpoints.operation_status`). Returns
a `v2/operation-status.schema.json` body: the same semantic shape as a
completion event, but `sequence` is **non-negative** (`>= 0`), because
`sequence: 0` represents the synchronous snapshot available
immediately after invoke — before any completion event has been
delivered over the callback — and by construction always reports
`state: "awaiting_user"`. At `sequence: 0`, `event_id` is a documented,
deterministic **snapshot identifier** (not a delivered callback
`event_id`) kept only so this schema stays field-for-field isomorphic
with `completion-event.schema.json`. This request is authenticated
using the `host-to-plugin` HMAC scheme (see `docs/security.md`).

An unknown or wrong `operation_id` (e.g. one that does not belong to
the requested `action_id`, or was never issued) yields **HTTP 404** —
see `openapi/plugin-api.yaml`.

### 3. Completion event (push, plugin → host, POST callback)

`POST {host_api_base_url}{host_api_route_prefix or ''}/api/plugin-host/v1/invocations/{invocation_id}/events`
— a **fixed path** appended after the optional gateway route prefix the
host supplied at invoke time. Body is a
`v2/completion-event.schema.json` document.
`sequence` here is **strictly positive** (`>= 1`): sequence 0 is
reserved for the synchronous initial operation status snapshot and is
never itself delivered as a callback event, so the very first callback
for an operation always carries `sequence: 1`.

This request is authenticated using the `plugin-to-host` HMAC scheme
(see `docs/security.md`). The host's response body is a
`v2/callback-success-response.schema.json` document (HTTP 200 only —
rejections are surfaced as 4xx/5xx with no body schema imposed by this
repository). `accepted: true` is the only signal a plugin needs to stop
retrying; `duplicate`, `applied`, `late`, and `stale` are optional,
non-load-bearing detail. An unknown or wrong `invocation_id` yields
**HTTP 404**.

A callback body MUST NOT exceed **64 KiB**; see `docs/security.md`.

### 4. Idempotency, late and stale events, retries

- **Idempotency key**: `event_id`. If the host has already recorded an
  `event_id` for this `operation_id`, it MUST return `accepted: true,
  duplicate: true` without changing recorded state, regardless of how
  many times the identical event is replayed.
- **Late**: an event that arrives after the host's normal processing
  window for its `sequence` position, but that the host still chooses
  to record for audit purposes without regressing already-applied
  state (`accepted: true, late: true`, `applied` reflects whether it
  actually changed anything).
- **Stale**: an event whose `sequence`/`state` would represent a
  regression relative to state already recorded for this
  `operation_id` (e.g. `sequence: 2` arrives after `sequence: 3` was
  already applied, or a `running` event arrives after a terminal state
  was already recorded). The host MUST still audit-log the event and
  respond `accepted: true, stale: true, applied: false`; it MUST NOT
  apply the regression.
- **Retries**: plugins MUST retry callback delivery (with backoff)
  until they receive `accepted: true` or an unambiguous permanent
  rejection (4xx other than a transient auth-clock-skew case — see
  `docs/security.md`'s ±300s window). Hosts MUST treat callback
  delivery as at-least-once and rely on `event_id` idempotency, never
  on the network layer, for exactly-once semantics.
- Terminal states (`succeeded`, `failed`, `cancelled`) are **frozen**:
  once recorded for an `operation_id`, no further event for that
  `operation_id` can change the recorded state (any such event is
  `stale`). See `docs/state-machine.md` for the full transition
  matrix.

## Browser continuation (`interaction_mode: launch_url`)

1. Host receives `launch_url` in the invoke-accepted response and
   prepares browser handoff with a host-minted, RS256-signed
   interaction-assertion JWT (claims:
   `schemas/v2/interaction-assertion-claims.schema.json`). The final
   handoff `Location` value is defined by
   `schemas/v2/browser-assertion-handoff-location.schema.json`.
   - `launch_url` MUST be fragment-free before handoff. If the plugin
     returns a `launch_url` that already contains `#...`, the host MUST
     treat it as invalid for browser continuation and MUST NOT append an
     assertion to it.
   - The host MUST append the assertion as the fixed fragment parameter
     `#contenttree_assertion=<percent-encoded JWT>`, preserving any
     existing query string exactly as returned by the plugin.
   - The host MUST NOT place the JWT in the path or query. The only
     transport from host handoff to plugin bootstrap is the fragment
     parameter above.
2. Plugin bootstrap (on the plugin origin) processes the fragment
   before loading any third-party resource and before making any
   assertion-exchange request:
   - It MUST accept exactly one non-empty `contenttree_assertion`
     parameter in the fragment.
   - Duplicate or empty `contenttree_assertion` parameters are malformed
     and MUST be rejected deterministically: do not exchange, do not
     create a session.
   - On the valid case, bootstrap percent-decodes once and `POST`s the
     exact decoded compact JWS string in the existing JSON exchange
     payload (`{ "assertion": "..." }`) to its same-origin
     `/auth/contenttree/exchange` endpoint.
   - It MUST immediately clear the fragment via `history.replaceState`
     after extraction, preserving path + query and removing
     `#contenttree_assertion=...`.
   - It MUST NOT log or persist the assertion token.
3. The plugin verifies the assertion (signature, `iss`, `aud`, `exp`,
   `iat`, single-use `jti`, `purpose == "plugin_interaction"`) and, on
   success, mints a first-party browser session: an `HttpOnly`,
   `Secure`, `SameSite=Lax` cookie, plus a `csrf_token` in the JSON
   response body
   (`schemas/v2/interaction-assertion-exchange-response.schema.json`)
   that the browser must echo back via the `X-ContentTree-CSRF-Token`
   header on subsequent state-changing requests in that session.
4. From here on the interaction is entirely within the plugin's own
   UI/session model; this repository does not constrain it further.
   Eventually the plugin reports the operation's outcome via the
   normal callback/status mechanisms above.

See `docs/security.md` for the full assertion verification checklist
and cookie/CSRF requirements.

## Versioning cross-reference

See `docs/versioning.md` for how `contract_version` relates to this
repository's own semantic version.
