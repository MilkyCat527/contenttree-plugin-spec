# Protocol

This document narrates the end-to-end wire protocol for both
`contract_version` 1 (synchronous-only) and `contract_version` 2
(deferred completion). It is domain-neutral: it describes generic
host/plugin action invocation, not any specific action's business
logic. All payload shapes referenced here are normative via the JSON
Schema documents under `schemas/`; this document is descriptive and
does not itself impose additional wire constraints beyond what those
schemas already say. Endpoint surfaces are formalized in
`openapi/plugin-host-api.yaml` (host-exposed) and
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

## contract_version 1 — synchronous-only

1. Host `POST`s a `v1/invoke-request.schema.json` body to the plugin's
   invoke endpoint for the target `action_id` (the concrete network
   address of a plugin's invoke endpoint is established out of band,
   e.g. via the host's plugin registry; it is not itself part of this
   manifest schema, since v1 plugins declare no `endpoints` object at
   all — see the "generic v1 only" rule below).
2. The plugin computes the entire result synchronously and returns a
   `v1/invoke-response.schema.json` body as the HTTP response. `state`
   is always one of the **terminal** states (`succeeded`, `failed`,
   `cancelled`) — a v1 plugin can never report `awaiting_user` or
   `running`, because by construction the response IS the final
   outcome.
3. There is no completion event, no operation status polling, and no
   `operation_id` in `contract_version` 1. The protocol interaction is
   exactly one request/response pair.
4. **v1 is generic only**: a manifest with `contract_version: 1` MUST
   NOT declare any action with `completion_mode: deferred`,
   `interaction_mode: launch_url`, or an `endpoints` object — all three
   are exclusively `contract_version: 2` concepts and
   `schemas/manifest.schema.json` rejects them structurally under
   `contract_version: 1`.

## contract_version 2 — deferred completion

### 1. Invoke

Host `POST`s a `v2/invoke-request.schema.json` body. In addition to
the v1 fields, it carries `host_api_base_url`: an absolute HTTPS origin
(scheme + host[:port], **no path, query, or fragment** — see
`schemas/common/fields.schema.json#/$defs/hostApiBaseUrl`) at which the
host exposes its plugin-host API for *this specific invocation*. This
exists so the plugin never has to guess, hardcode, or be handed an
arbitrary full callback URL (anti-SSRF: the plugin only ever appends
the one fixed, repository-documented path below to an origin the host
itself supplied for this call). The shared HMAC secret used to sign
callbacks is **never** carried in any invoke, callback, or status
payload; it is provisioned out of band during plugin registration.

The plugin responds synchronously with a
`v2/invoke-accepted-response.schema.json` body — an *acceptance*, not a
result. Two variants are structurally enforced by the schema's
`if`/`then`/`else`:

- **non-launch variant** (`interaction_mode: "none"`): `operation_id`,
  `state` (`awaiting_user` or `running`), `result_mode`; `launch_url`
  MUST be absent.
- **launch variant** (`interaction_mode: "launch_url"`): the same
  fields, plus a required `launch_url` that the host redirects (or
  hands to) the end user's browser. `launch_url` is a locator only — it
  carries no ambient authority; the browser continuation is separately
  authenticated via the interaction-assertion JWT (see
  `docs/security.md`).

Invoking an action does not itself create any outbox / completion
event. The first thing the host can observe about this operation's
progress, other than the invoke-accepted response, is either (a) the
operation status endpoint reporting sequence 0, or (b) the plugin's
first callback event at sequence 1.

### 2. Operation status (poll, host → plugin, GET)

`GET <endpoints.operation_status><action manifest URL>/operations/{operation_id}`
(the host appends the fixed suffix `/operations/{operation_id}` to the
action's declared `endpoints.operation_status` base URL). Returns a
`v2/operation-status.schema.json` body: the same semantic shape as a
completion event, but `sequence` is **non-negative** (`>= 0`), because
`sequence: 0` represents the synchronous snapshot available
immediately after invoke — before any completion event has been
delivered over the callback — and by construction always reports
`state: "awaiting_user"`. This request is authenticated using the
`host-to-plugin` HMAC scheme (see `docs/security.md`).

An unknown or wrong `operation_id` (e.g. one that does not belong to
the requested `action_id`, or was never issued) yields **HTTP 404** —
see `openapi/plugin-api.yaml`.

### 3. Completion event (push, plugin → host, POST callback)

`POST {host_api_base_url}/api/plugin-host/v1/invocations/{invocation_id}/events`
— a **fixed path** appended to the origin the host supplied at invoke
time. Body is a `v2/completion-event.schema.json` document.
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
   redirects (or otherwise hands off) the end user's browser to it,
   together with a host-minted, RS256-signed interaction-assertion JWT
   (claims: `schemas/v2/interaction-assertion-claims.schema.json`).
2. The browser (now at the plugin's own origin) submits the assertion
   via `POST /auth/contenttree/exchange`
   (`schemas/v2/interaction-assertion-exchange-request.schema.json`).
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
