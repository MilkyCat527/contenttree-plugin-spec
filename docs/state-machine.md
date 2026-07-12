# State machine

This document defines the complete set of plugin-reportable states for
a `contract_version` 2 deferred operation, and the **explicit
transition matrix** that governs which state may follow which. It
applies to the sequence of `state` values observed across: the
`sequence: 0` operation status snapshot, every subsequent callback
event (`sequence >= 1`), and any later operation status poll. It does
not apply to `contract_version` 1, whose single synchronous response
always reports exactly one terminal state and has no transitions at
all (see `docs/protocol.md`).

## Reportable states

`schemas/common/fields.schema.json#/$defs/pluginState` is the complete,
closed enum a plugin may ever report:

| State | Terminal? | Meaning |
|---|---|---|
| `awaiting_user` | No | The operation is waiting on a browser continuation / human input before it can proceed. Only ever the state at `sequence: 0`, or reached again later if (and only if) the transition matrix below permits it. |
| `running` | No | The operation is actively being processed (no further human input pending at this moment). |
| `succeeded` | **Yes** | The operation completed successfully. |
| `failed` | **Yes** | The operation completed unsuccessfully. |
| `cancelled` | **Yes** | The operation was terminated before producing a result (by the host, the plugin, or an external actor), distinct from `failed`. |

Two related, narrower enums exist for context-specific schemas:

- `pluginStateAccepted` (`awaiting_user`, `running`) — the only states a
  plugin may report synchronously in the invoke-accepted response,
  since terminal outcomes cannot be known that early.
- `pluginStateTerminal` (`succeeded`, `failed`, `cancelled`) — the only
  states a `contract_version` 1 synchronous invoke response may report.

**Host-only states** (e.g. an internal `pending`, `ok`, or `expired`
bookkeeping status a host may keep for its own audit/queueing purposes)
are explicitly **not** part of `pluginState` and MUST NOT appear in any
plugin-authored event or operation status body. Those are purely
internal to the host's own implementation and out of scope for this
repository's schemas.

## Sequence numbering

- **Operation status snapshot** (`v2/operation-status.schema.json`):
  `sequence >= 0`. `sequence: 0` is the synchronous snapshot available
  immediately after invoke accepts the operation, before any callback
  has been delivered (invoking an action creates no outbox / event by
  itself). By construction, `sequence: 0` always reports
  `state: "awaiting_user"` — this is enforced structurally by the
  schema's conditional (`if sequence == 0, then state == "awaiting_user"`).
- **Completion event** (`v2/completion-event.schema.json`, delivered via
  callback): `sequence >= 1`. The first callback event for any
  operation is always `sequence: 1`.
- Both are scoped per-`operation_id` and MUST be strictly monotonically
  increasing as observed by the host for a given `operation_id` — a
  callback (or, transitively, the latest operation-status snapshot)
  reporting a `sequence` not strictly greater than the highest already
  recorded is **stale** (see `docs/protocol.md` §4 and
  `docs/security.md`).

## Terminal freeze

Once a host has recorded `succeeded`, `failed`, or `cancelled` for an
`operation_id` (at any `sequence`), that recorded state is **frozen**:
no later event (regardless of its own `sequence` number) may change it.
Any event arriving after a terminal state has been recorded MUST be
treated as `stale` (`v2/callback-success-response.schema.json`:
`accepted: true, stale: true, applied: false`) and MUST NOT itself be
applied, even if its own `sequence` number is numerically higher than
what was last recorded. There is exactly one way out of a terminal
state for a given `operation_id`: there is none. A plugin that needs to
report further work after reaching a terminal outcome (e.g. a retry)
MUST do so under a **new** `operation_id` obtained via a new `invoke`
call.

## Explicit transition matrix

The table below is read as: given the **previously recorded** state
(row) for an `operation_id`, is a **newly arriving** event/status
report of the given state (column) a valid, applicable transition
(`✅`), a structurally-impossible/undefined case for this protocol
(`—`, cannot occur because the previous state itself would already be
terminal or because there is no previous state yet), or an explicitly
**disallowed** transition that MUST be rejected/treated as stale even
though both states individually are valid enum members (`❌`)?

| Previous → New | `awaiting_user` | `running` | `succeeded` | `failed` | `cancelled` |
|---|---|---|---|---|---|
| *(none — sequence 0)* | ✅ (the only state sequence 0 may report) | — | — | — | — |
| `awaiting_user` | ✅ (still waiting; re-reported) | ✅ | ✅ | ✅ | ✅ |
| `running` | ❌ **disallowed** | ✅ (still running; re-reported) | ✅ | ✅ | ✅ |
| `succeeded` | ❌ (terminal freeze) | ❌ (terminal freeze) | ✅ (idempotent duplicate/replay only, via `event_id`) | ❌ (terminal freeze) | ❌ (terminal freeze) |
| `failed` | ❌ (terminal freeze) | ❌ (terminal freeze) | ❌ (terminal freeze) | ✅ (idempotent duplicate/replay only, via `event_id`) | ❌ (terminal freeze) |
| `cancelled` | ❌ (terminal freeze) | ❌ (terminal freeze) | ❌ (terminal freeze) | ❌ (terminal freeze) | ✅ (idempotent duplicate/replay only, via `event_id`) |

Notes on the matrix:

- **`running` → `awaiting_user` is explicitly disallowed.** Once an
  operation has announced it is actively `running` (no longer waiting
  on the user), it MUST NOT subsequently report going back to
  `awaiting_user`. If a plugin genuinely needs a *further* round of user
  interaction after already reporting `running`, that is a distinct
  operation-design smell this protocol does not support within a single
  `operation_id`; model it as a new deferred action/operation instead.
  Any such event MUST be rejected as `stale`
  (`accepted: true, stale: true, applied: false`), not applied.
- A row's ✅ cells for identical previous/new state (`awaiting_user` →
  `awaiting_user`, `running` → `running`) represent legitimate
  re-announcements (e.g. a heartbeat-style progress update while
  remaining in the same non-terminal state) and are `applied: true`
  (they may still update `progress`, `occurred_at`, etc.) as long as
  `sequence` strictly increases.
- Terminal → same-terminal cells (`succeeded` → `succeeded`, etc.) are
  ✅ **only** when it is the exact same `event_id` being replayed
  (idempotent duplicate delivery, `accepted: true, duplicate: true`). A
  *different* `event_id` reporting the same terminal state again after
  one was already recorded is still a terminal-freeze violation and
  MUST be treated as `stale`, not newly `applied`.
- Terminal → any *different* state is always `❌` (terminal freeze, see
  above) — this covers all remaining terminal-row cells.
- `awaiting_user` → any single state is `✅` because
  `awaiting_user` is the only valid state at `sequence: 0` and is
  explicitly the row with the most freedom to transition, including
  directly to any terminal state (an operation can resolve to a
  terminal outcome without ever visibly reporting `running`, e.g. if
  the user interaction itself is the entire unit of work).

## Relationship to HTTP-level idempotency semantics

The state machine above governs the *meaning* of `applied` vs.
`duplicate` vs. `stale` in
`v2/callback-success-response.schema.json`; see `docs/protocol.md` §4
and `docs/security.md` for the wire-level idempotency, retry, and
signing rules that these responses interact with.
