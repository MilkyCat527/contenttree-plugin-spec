# Security

This document specifies the two HMAC signing schemes used by the
deferred completion protocol (`contract_version` 2), the browser
continuation assertion exchange, and the transport-level rules that
apply to every request/response in this repository's scope. It
contains **deterministic test vectors** (fixed secret, fixed
timestamps, fixed bodies) so that an independent implementation can
verify its HMAC computation byte-for-byte without needing to run any
code from this repository. These vectors are consumed by the
conformance test suite added in the follow-on `S2` stack PR; nothing in
`S1` executes them, but they MUST NOT change once published, since
`S2`'s tests are written against these exact values.

> **Corrective update:** the Scheme 1 vector's callback body originally
> used `"result_mode":"none"`, a value inherited from an incompatible,
> now-retracted `resultMode` enum (`none`/`url`). `resultMode` is
> normatively `mock`/`production` (execution environment, never a
> result-transport mode — see `docs/protocol.md` and
> `schemas/common/fields.schema.json#/$defs/resultMode`); the vector
> body and its signature below have been corrected accordingly
> (`result_mode` is now `"mock"`) as part of that fix, before either
> stack PR's fixtures depended on the old, invalid value. The
> "MUST NOT change once published" invariant applies prospectively from
> this correction onward.

## Header names

Both signing directions use the same two header names; the *content*
of the signed string differs by direction (see below):

| Header | Meaning |
|---|---|
| `X-ContentTree-Signature` | `sha256=<lowercase-hex-hmac-sha256-digest>` |
| `X-ContentTree-Timestamp` | Decimal string of Unix epoch seconds (UTC) at signing time |

The `sha256=` prefix is fixed and MUST be present; verifiers MUST
reject a `X-ContentTree-Signature` value that does not start with it.
The digest itself is 64 lowercase hex characters (32 raw bytes).

## Clock skew tolerance: ±300 seconds

A verifier MUST compare the `X-ContentTree-Timestamp` header against
its own current time and **reject the request** if the absolute
difference exceeds **300 seconds** in either direction (i.e. valid
range is `now - 300 <= timestamp <= now + 300`). This bounds replay
window size given the `event_id` idempotency guarantee (callbacks) and
limits the value of a captured, unexpired status-poll request. A
rejected-for-skew request is a distinct condition from a rejected-for-
bad-signature request; implementations MAY use different status codes
or error bodies for the two, but this repository does not mandate a
specific error schema for either (see `openapi/*.yaml` for the generic
4xx responses declared on each operation).

## 64 KiB callback body limit

A callback request body (`v2/completion-event.schema.json` serialized
as JSON) MUST NOT exceed **65536 bytes (64 KiB)** measured as the exact
byte length of the HTTP request body that is also the exact byte
string signed (see below). A host MUST reject an oversized callback
body before attempting signature verification or JSON parsing, since
the size limit exists partly to bound the cost of both. Plugins MUST
keep `error_message` (the least-bounded field in the payload, `maxLength: 500`
characters) and any other free-text content well within this envelope;
500 characters of UTF-8 text is always far under 64 KiB on its own, so
in practice only pathological framing (e.g. transport-level padding)
should ever approach the limit.

## Callback destination construction

`host_api_base_url` is always an origin only; a gateway path MUST NOT be
embedded in it. A gateway-mounted host may instead supply the optional
`host_api_route_prefix` on the v2 invoke request. The shared
`hostApiRoutePrefix` schema accepts a normalized absolute path prefix
such as `/NewContentTree` and rejects a trailing slash, query, fragment,
percent encoding, backslash, empty segment, `.`/`..` segment, scheme,
and authority. Absence means the host API is mounted at the origin root.

After validating both invoke fields, plugins construct callback URLs by
literal concatenation as
`{host_api_base_url}{host_api_route_prefix or ''}/api/plugin-host/...`.
They MUST NOT use URL-reference resolution, percent-decode, or otherwise
normalize the supplied prefix: those transformations can change the
request target or replace part of the validated origin. This optional
path component does not weaken the HTTPS and origin-only requirements
below.

## HTTPS only, no redirects

Every request defined by this repository — invoke, callback, operation
status poll, and assertion exchange — MUST be made over HTTPS, and the
HTTP client on either side MUST NOT follow redirects (`3xx` responses
MUST be treated as failures, not silently followed). This applies to
the callback URL composed from `host_api_base_url` and optional
`host_api_route_prefix`, the plugin's own `base_url` (established out
of band at registration; see `openapi/plugin-api.yaml`'s `servers` block —
`endpoints.invoke`/`endpoints.operation_status` in
`schemas/manifest.schema.json` are relative *paths* resolved against
that `base_url`, never absolute URLs themselves), `launch_url`, and
`result_url` alike. The **sole exception** is `http://localhost` /
`http://127.0.0.1` for `host_api_base_url`
(`schemas/common/fields.schema.json#/$defs/hostApiBaseUrl`), which
exists only to support local conformance testing; production hosts and
plugins MUST NOT honor a non-HTTPS `host_api_base_url` from any
counterparty claiming to be anything other than local test
infrastructure they themselves control.

## Idempotency, late/stale handling, retries

See `docs/protocol.md` (`#4. Idempotency, late and stale events,
retries`) for the full semantics; the `event_id` field
(`schemas/common/fields.schema.json#/$defs/eventId`) is the idempotency
key for callback delivery, and `v2/callback-success-response.schema.json`
is the vehicle for signaling `duplicate` / `applied` / `late` / `stale`
back to the retrying plugin.

## Secrets are never in any payload

The shared HMAC secret (used for both signing directions, unless an
implementation chooses independently rotated per-direction secrets —
this repository does not mandate either way, only that whichever secret
scheme is used, it MUST be provisioned out of band, e.g. at plugin
registration time) MUST NEVER appear in any invoke request, invoke
response, callback body, operation status body, manifest, or assertion
claim set defined by this repository's schemas. Every schema in
`schemas/` that carries `additionalProperties: false` structurally
prevents adding a secret-carrying field without also breaking schema
validation, but implementers MUST NOT work around this by, for example,
embedding a secret inside an already-permitted opaque string field
(`external_id`, `provider`, etc.).

---

## Scheme 1: `plugin-to-host` (callback signing)

Used when the **plugin** POSTs a completion event to the host's fixed
callback path (see `docs/protocol.md` §3 and
`openapi/plugin-host-api.yaml`).

### Signing string

```
plugin-to-host:<timestamp>.<exact-body>
```

- `<timestamp>` is the exact decimal string also sent in the
  `X-ContentTree-Timestamp` header (not re-derived or reformatted by
  the verifier).
- `<exact-body>` is the **exact byte sequence** of the HTTP request
  body — the same bytes that will subsequently be parsed as JSON and
  validated against `v2/completion-event.schema.json`. It is
  concatenated as-is (UTF-8 text in these vectors); no re-serialization,
  whitespace normalization, or key reordering may occur before or
  during signing. A verifier MUST compute the HMAC over the raw
  received body bytes *before* JSON-parsing them, precisely so that
  byte-for-byte reproduction (including whitespace) is required to
  forge a valid signature over a modified body.
- The literal character between the timestamp and the body is a single
  `.` (U+002E FULL STOP), and the literal prefix (including its
  trailing `:`) is `plugin-to-host:`.

### Signature

```
HMAC-SHA256(secret, signing_string)
```

rendered as `sha256=` + lowercase hex.

### Deterministic test vector

```
secret (UTF-8 bytes):    contenttree-plugin-spec-conformance-secret-v1
X-ContentTree-Timestamp: 1750000000   (2025-06-15T15:06:40Z)
request body (exact bytes, no trailing newline):
{"event_id":"evt-conformance-0001","sequence":1,"state":"succeeded","occurred_at":"2025-06-15T14:13:20Z","result_mode":"mock"}
```

Signing string (shown with the literal body inline for clarity — the
verifier does not add any quoting/escaping beyond what is already in
the body bytes above):

```
plugin-to-host:1750000000.{"event_id":"evt-conformance-0001","sequence":1,"state":"succeeded","occurred_at":"2025-06-15T14:13:20Z","result_mode":"mock"}
```

Expected `X-ContentTree-Signature`:

```
sha256=762e19e3b505b13b866d11f1a898d0a8017f954db32b68153a1fb949817a6790
```

> This vector's `secret` is a fixed, publicly documented ASCII string
> chosen solely for reproducible testing. It carries no ambient
> authority (there is no real host or plugin that honors it) and MUST
> NOT be reused as an actual production secret.

---

## Scheme 2: `host-to-plugin` (operation status GET signing)

Used when the **host** GETs a plugin's operation status endpoint (see
`docs/protocol.md` §2 and `openapi/plugin-api.yaml`).

### Signing string (canonical request)

```
host-to-plugin:<timestamp>\nGET\n<request-target>
```

- `<timestamp>` — same rule as Scheme 1.
- The method is always the literal ASCII string `GET` (this scheme is
  only ever used for the operation status poll, which is always a GET;
  it is not a general-purpose request signer).
- `<request-target>` is the **raw HTTP request-target**: the exact
  request path, taken byte-for-byte from the request line (no
  percent-decoding, no trailing-slash normalization), followed by `?`
  and the exact raw query string **only if a query string is present**
  (omit the `?` entirely when there is no query — do not append a bare
  `?`). The query string is used exactly as sent on the wire: this
  scheme does **not** reorder, deduplicate, or otherwise canonicalize
  query parameters beyond using the raw bytes present on the request
  line. Both sides MUST therefore construct the request line
  deterministically (fixed parameter order) if a query string is used
  at all, since the signature is sensitive to byte-for-byte query
  ordering.
- Line separator between the three components is a single `\n` (U+000A
  LINE FEED); there is no trailing newline after `<request-target>`.

### Signature

Identical construction to Scheme 1: `HMAC-SHA256(secret, signing_string)`,
rendered as `sha256=` + lowercase hex.

### Deterministic test vectors

**Vector A — no query string:**

```
secret (UTF-8 bytes):    contenttree-plugin-spec-conformance-secret-v1
X-ContentTree-Timestamp: 1750000030   (2025-06-15T15:07:10Z)
request-target:          /plugins/demo-plugin/actions/review-summary/operations/op-conformance-0001
```

Signing string:

```
host-to-plugin:1750000030
GET
/plugins/demo-plugin/actions/review-summary/operations/op-conformance-0001
```

Expected `X-ContentTree-Signature`:

```
sha256=6f36da729c8f411809c870d03c50a84da169433b28ef28d5bbc273267d3423a2
```

**Vector B — with query string:**

```
secret (UTF-8 bytes):    contenttree-plugin-spec-conformance-secret-v1
X-ContentTree-Timestamp: 1750000060   (2025-06-15T15:07:40Z)
request-target:          /plugins/demo-plugin/actions/review-summary/operations/op-conformance-0001?wait=30
```

Signing string:

```
host-to-plugin:1750000060
GET
/plugins/demo-plugin/actions/review-summary/operations/op-conformance-0001?wait=30
```

Expected `X-ContentTree-Signature`:

```
sha256=aa1bb12bc8c05e8dfe3ebf6869d800718da690abf787caec8371d51519d11937
```

> Same fixed, non-production test secret as Scheme 1's vector.

### Reproducing these vectors

```python
import hmac, hashlib

secret = b"contenttree-plugin-spec-conformance-secret-v1"

# Scheme 1
body = ('{"event_id":"evt-conformance-0001","sequence":1,"state":"succeeded",'
        '"occurred_at":"2025-06-15T14:13:20Z","result_mode":"mock"}')
signing_string = f"plugin-to-host:1750000000.{body}"
print(hmac.new(secret, signing_string.encode(), hashlib.sha256).hexdigest())
# 762e19e3b505b13b866d11f1a898d0a8017f954db32b68153a1fb949817a6790

# Scheme 2 (vector A)
signing_string = (
    "host-to-plugin:1750000030\nGET\n"
    "/plugins/demo-plugin/actions/review-summary/operations/op-conformance-0001"
)
print(hmac.new(secret, signing_string.encode(), hashlib.sha256).hexdigest())
# 6f36da729c8f411809c870d03c50a84da169433b28ef28d5bbc273267d3423a2

# Scheme 2 (vector B)
signing_string = (
    "host-to-plugin:1750000060\nGET\n"
    "/plugins/demo-plugin/actions/review-summary/operations/op-conformance-0001?wait=30"
)
print(hmac.new(secret, signing_string.encode(), hashlib.sha256).hexdigest())
# aa1bb12bc8c05e8dfe3ebf6869d800718da690abf787caec8371d51519d11937
```

---

## Browser continuation: assertion exchange

### Transport and handoff hardening

- The final handoff `Location` value MUST validate against
  `schemas/v2/browser-assertion-handoff-location.schema.json`.
- The host-side continuation response that hands the browser to
  `launch_url` (redirect or equivalent browser handoff) MUST be
  non-cacheable and non-referring: `Cache-Control: no-store` and
  `Referrer-Policy: no-referrer`.
- `launch_url` MUST be fragment-free before host handoff. The host MUST
  append exactly one fixed fragment parameter in this form:
  `#contenttree_assertion=<percent-encoded JWT>`, preserving any query
  string already present on `launch_url`.
- The assertion JWT MUST NOT be placed in the path or query of
  `launch_url`, and MUST NOT be copied into any other URL parameter.
  Fragments are chosen because they are not sent in HTTP request lines
  and (under `no-referrer`) are not propagated as `Referer` metadata.
- Plugin bootstrap MUST read the fragment before loading third-party
  resources, immediately clear it with `history.replaceState`, and then
  call same-origin `POST /auth/contenttree/exchange` with the exact
  once-decoded compact JWS value in JSON body field `assertion`.
- Bootstrap MUST reject malformed fragment input deterministically and
  MUST NOT exchange on malformed input: missing assertion, empty
  assertion, duplicate `contenttree_assertion`, or invalid
  percent-encoding.
- Implementations MUST NOT log or persist assertion-token material
  (including browser logs, analytics payloads, local/session storage, or
  URL persistence).

### Assertion (JWT) requirements

- Algorithm: **RS256 only**. Verifiers MUST reject any other `alg`
  (including `none`).
- Claims (see `schemas/v2/interaction-assertion-claims.schema.json`):
  `iss`, `aud`, `sub`, `exp`, `iat`, `jti`, `invocation_id`, `tree_id`,
  `purpose`. All are required; no additional claims are permitted by
  the schema.
- `purpose` MUST equal the fixed literal `"plugin_interaction"` —
  a dedicated audience-confusion guard so that a signing key shared (or
  compromised) across multiple token purposes cannot be replayed here.
- `jti` MUST be treated as **single-use**: the plugin MUST reject any
  assertion whose `jti` it has already consumed, independent of
  whether `exp` has elapsed. Implementations should maintain a
  consumed-`jti` set with a TTL of at least the assertion's maximum
  allowed lifetime.
- `exp` MUST be enforced; short lifetimes (recommended: a few minutes)
  are strongly preferred, since the assertion only needs to survive one
  browser redirect + one POST to `/auth/contenttree/exchange`.
- The plugin MUST verify `aud` identifies itself and `iss` identifies
  the host it trusts for this `invocation_id`, and MUST verify the
  signature against the host's published JWKS (JWKS distribution
  mechanism/rotation policy is out of scope for this repository; hosts
  and plugins negotiate it during registration).

### Exchange endpoint

`POST /auth/contenttree/exchange` (hosted **by the plugin** — see
`openapi/plugin-api.yaml` and the note in `README.md`).

- Request: `schemas/v2/interaction-assertion-exchange-request.schema.json`
  (`{ "assertion": "<compact JWS>" }`).
- Response (200 on success):
  `schemas/v2/interaction-assertion-exchange-response.schema.json`
  body, plus a `Set-Cookie` response header for the newly minted browser
  continuation session cookie with all of:
  - `HttpOnly` (never readable from page JavaScript)
  - `Secure` (never sent over plain HTTP)
  - `SameSite=Lax`
- The response body's `csrf_token` is **not** placed in a
  script-readable cookie. The browser's own client-side code must read
  it from the JSON response and attach it as the
  `X-ContentTree-CSRF-Token` header on subsequent state-changing
  requests within that session; the plugin's origin MUST reject such
  requests if the header is missing or does not match the session's
  issued token.
- An invalid, expired, wrong-audience, wrong-issuer, replayed-`jti`, or
  bad-signature assertion MUST be rejected (4xx) and MUST NOT mint a
  session cookie.
