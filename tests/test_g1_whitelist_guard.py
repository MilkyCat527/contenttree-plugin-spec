"""G1 whitelist guard: the exact 11-property closed set shared by
completion-event and operation-status, and the one deliberate difference
between them (the sequence field's minimum).

G1 (this repository's domain-neutrality guardrail, see README.md "Non-goals
(G3)" for the sibling no-SDK guardrail): any new schema property must be
meaningful for ANY deferred-capable plugin, not tied to a specific domain.
A closed (additionalProperties: false), exhaustively enumerated property set
is the structural enforcement mechanism for that rule — this test pins the
exact whitelist so that an accidental/undiscussed new property (schema
drift) fails CI instead of silently expanding the wire contract.
"""
from __future__ import annotations

EXPECTED_EVENT_PROPERTIES = {
    "event_id",
    "sequence",
    "state",
    "occurred_at",
    "result_mode",
    "progress",
    "external_id",
    "result_url",
    "provider",
    "error_code",
    "error_message",
}


def test_whitelist_has_exactly_eleven_properties():
    assert len(EXPECTED_EVENT_PROPERTIES) == 11


def test_completion_event_schema_matches_g1_whitelist(schema_by_id):
    schema = schema_by_id["https://schemas.contenttree.dev/plugin-spec/v2/completion-event.schema.json"]
    assert schema["additionalProperties"] is False
    assert set(schema["properties"].keys()) == EXPECTED_EVENT_PROPERTIES


def test_operation_status_schema_matches_g1_whitelist(schema_by_id):
    schema = schema_by_id["https://schemas.contenttree.dev/plugin-spec/v2/operation-status.schema.json"]
    assert schema["additionalProperties"] is False
    assert set(schema["properties"].keys()) == EXPECTED_EVENT_PROPERTIES


def test_completion_event_and_operation_status_share_identical_property_set(schema_by_id):
    completion = schema_by_id["https://schemas.contenttree.dev/plugin-spec/v2/completion-event.schema.json"]
    status = schema_by_id["https://schemas.contenttree.dev/plugin-spec/v2/operation-status.schema.json"]
    assert set(completion["properties"].keys()) == set(status["properties"].keys())
    # Both also share the same *required* subset.
    assert set(completion["required"]) == set(status["required"])


def test_sequence_minimum_differs_between_event_and_status(schema_by_id):
    """The one intentional divergence: completion events are strictly
    positive (sequence 0 is never delivered as a callback), while the
    operation status snapshot allows 0 (the synchronous pre-callback
    snapshot)."""
    completion = schema_by_id["https://schemas.contenttree.dev/plugin-spec/v2/completion-event.schema.json"]
    status = schema_by_id["https://schemas.contenttree.dev/plugin-spec/v2/operation-status.schema.json"]

    completion_sequence_ref = completion["properties"]["sequence"]["$ref"]
    status_sequence_ref = status["properties"]["sequence"]["$ref"]

    assert completion_sequence_ref.endswith("#/$defs/sequencePositive")
    assert status_sequence_ref.endswith("#/$defs/sequenceNonNegative")
    assert completion_sequence_ref != status_sequence_ref


def test_sequence_positive_and_non_negative_defs_have_expected_minimums(schema_by_id):
    fields = schema_by_id["https://schemas.contenttree.dev/plugin-spec/common/fields.schema.json"]
    assert fields["$defs"]["sequencePositive"]["minimum"] == 1
    assert fields["$defs"]["sequenceNonNegative"]["minimum"] == 0


def test_plugin_state_enum_excludes_host_only_states(schema_by_id):
    """Host-only bookkeeping states (pending, ok, expired, ...) MUST NOT be
    members of the plugin-reportable pluginState enum (docs/state-machine.md
    'Host-only states')."""
    fields = schema_by_id["https://schemas.contenttree.dev/plugin-spec/common/fields.schema.json"]
    plugin_state_enum = set(fields["$defs"]["pluginState"]["enum"])
    assert plugin_state_enum == {"awaiting_user", "running", "succeeded", "failed", "cancelled"}
    host_only_examples = {"pending", "ok", "expired"}
    assert plugin_state_enum.isdisjoint(host_only_examples)


def test_callback_response_whitelist_is_five_properties_with_single_required(schema_by_id):
    """Sibling closed-whitelist guard for the callback response body, which
    is small and static enough to pin exactly."""
    schema = schema_by_id["https://schemas.contenttree.dev/plugin-spec/v2/callback-success-response.schema.json"]
    assert schema["additionalProperties"] is False
    assert set(schema["properties"].keys()) == {"accepted", "duplicate", "applied", "late", "stale"}
    assert schema["required"] == ["accepted"]


def test_interaction_assertion_claims_whitelist_is_nine_properties(schema_by_id):
    """Sibling closed-whitelist guard for the browser continuation
    assertion claim set (docs/security.md: 'no additional claims are
    permitted by the schema')."""
    schema = schema_by_id["https://schemas.contenttree.dev/plugin-spec/v2/interaction-assertion-claims.schema.json"]
    assert schema["additionalProperties"] is False
    expected = {"iss", "aud", "sub", "exp", "iat", "jti", "invocation_id", "tree_id", "purpose"}
    assert set(schema["properties"].keys()) == expected
    assert len(expected) == 9
    assert set(schema["required"]) == expected, "every claim is required; no additional claims are permitted"
