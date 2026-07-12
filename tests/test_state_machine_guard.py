"""State-machine guard: an explicit allowed-transition matrix mirroring
docs/state-machine.md's table, plus the terminal-freeze rule and the
higher-sequence running -> awaiting_user rejection semantics.

The guard function below is deliberately *not* a reference implementation
of host-side state tracking (no SDK — see README.md "Non-goals (G3)"); it
is a small, test-local model whose sole purpose is to encode the transition
matrix as data so this suite can assert every cell of docs/state-machine.md
is covered, including the explicitly-disallowed cells that individual
schema validation alone cannot catch (schema validation only checks that
each event's own `state` is a valid enum member + the sequence-0-implies-
awaiting_user rule; it has no cross-event memory of a *previous* state,
which is exactly what the transition matrix and this guard add).
"""
from __future__ import annotations

from typing import Optional

TERMINAL_STATES = {"succeeded", "failed", "cancelled"}
ALL_STATES = {"awaiting_user", "running", "succeeded", "failed", "cancelled"}

# Mirrors docs/state-machine.md "Explicit transition matrix" exactly.
# Keys: previous recorded state (None = no previous state yet, i.e. sequence 0).
# Values: set of new states that are a *newly applied* (non-duplicate) valid
# transition from that previous state.
ALLOWED_TRANSITIONS: dict[Optional[str], set[str]] = {
    None: {"awaiting_user"},
    "awaiting_user": {"awaiting_user", "running", "succeeded", "failed", "cancelled"},
    "running": {"running", "succeeded", "failed", "cancelled"},  # running -> awaiting_user explicitly disallowed
    "succeeded": set(),  # terminal freeze: only an identical event_id replay (duplicate) may repeat "succeeded"
    "failed": set(),
    "cancelled": set(),
}


def is_transition_allowed(previous_state: Optional[str], new_state: str) -> bool:
    """Returns whether `new_state` is a valid *newly applied* transition from
    `previous_state`, per docs/state-machine.md. Does not model the
    idempotent-duplicate-replay exception (same event_id resubmitted) —
    callers must special-case that themselves using the event_id identity,
    exactly as docs/state-machine.md separates "duplicate" from "applied"."""
    if previous_state not in ALLOWED_TRANSITIONS:
        raise ValueError(f"unknown previous_state: {previous_state!r}")
    if new_state not in ALL_STATES:
        raise ValueError(f"unknown new_state: {new_state!r}")
    return new_state in ALLOWED_TRANSITIONS[previous_state]


def test_transition_matrix_covers_every_state_as_previous():
    assert set(ALLOWED_TRANSITIONS.keys()) == {None} | ALL_STATES


def test_sequence_zero_may_only_report_awaiting_user():
    for state in ALL_STATES:
        expected = state == "awaiting_user"
        assert is_transition_allowed(None, state) is expected


def test_awaiting_user_may_transition_to_any_state_including_itself():
    for state in ALL_STATES:
        assert is_transition_allowed("awaiting_user", state) is True


def test_running_to_awaiting_user_is_explicitly_disallowed():
    """The one named exception in docs/state-machine.md: once `running` has
    been reported, the operation MUST NOT subsequently report
    `awaiting_user` again, even at a strictly higher sequence number. This
    is true regardless of how much higher the new event's sequence is
    relative to the last one recorded — sequence being monotonically higher
    does not by itself make a `running` -> `awaiting_user` event valid."""
    assert is_transition_allowed("running", "awaiting_user") is False


def test_running_to_awaiting_user_rejection_holds_at_any_higher_sequence():
    """Normative test data: (previous_state, previous_sequence, new_state,
    new_sequence) tuples where new_sequence > previous_sequence (so the
    event is NOT stale merely for out-of-order sequencing) yet the
    transition must still be rejected purely on transition-matrix grounds."""
    higher_sequence_running_to_awaiting_user_cases = [
        ("running", 1, "awaiting_user", 2),
        ("running", 2, "awaiting_user", 5),
        ("running", 10, "awaiting_user", 999),
    ]
    for previous_state, previous_sequence, new_state, new_sequence in higher_sequence_running_to_awaiting_user_cases:
        assert new_sequence > previous_sequence, "test data must isolate the transition-matrix rejection, not sequence ordering"
        assert is_transition_allowed(previous_state, new_state) is False


def test_running_may_re_report_running_and_reach_any_terminal_state():
    assert is_transition_allowed("running", "running") is True
    for terminal in TERMINAL_STATES:
        assert is_transition_allowed("running", terminal) is True


def test_terminal_states_are_frozen_against_every_new_applied_transition():
    """Once a terminal state is recorded, no *newly applied* transition is
    permitted at all — not to another terminal state, not back to a
    non-terminal state. (The only way a terminal state can be "re-reported"
    is an exact event_id replay, which is a `duplicate`, not a fresh
    `applied` transition — see docs/state-machine.md notes on the matrix
    and is intentionally NOT modeled as an allowed entry here.)"""
    for terminal in TERMINAL_STATES:
        for candidate in ALL_STATES:
            assert is_transition_allowed(terminal, candidate) is False, (
                f"terminal state {terminal!r} must reject a fresh transition to {candidate!r}"
            )


def test_terminal_freeze_matches_documented_matrix_cell_count():
    """Sanity-checks the matrix literally mirrors the doc's table shape:
    3 terminal previous-states x 5 possible new-states = 15 disallowed
    cells (all handled as 'stale' per docs/state-machine.md), plus the
    running->awaiting_user disallowed cell = 16 explicitly disallowed
    (non-duplicate) transitions in total across the whole matrix."""
    disallowed = 0
    for previous_state, allowed in ALLOWED_TRANSITIONS.items():
        if previous_state is None:
            candidates = ALL_STATES
        else:
            candidates = ALL_STATES
        for candidate in candidates:
            if previous_state is None:
                # sequence 0: only awaiting_user is a "cell" at all; the rest
                # are structurally impossible ("—"), not "disallowed" (❌).
                continue
            if candidate not in allowed:
                disallowed += 1
    assert disallowed == 16


def test_new_operation_id_is_the_only_documented_escape_from_terminal_freeze():
    """Purely documentation-presence guard: docs/state-machine.md must
    state that a new operation_id (not any in-place transition) is the
    only way to report further work after a terminal outcome."""
    from conftest import DOCS_DIR

    text = (DOCS_DIR / "state-machine.md").read_text(encoding="utf-8")
    assert "there is none" in text
    assert "new** `operation_id`" in text or "new `operation_id`" in text
