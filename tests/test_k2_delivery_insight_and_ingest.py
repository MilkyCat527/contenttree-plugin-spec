"""K2 delivery-insight surface extension point, collection ticket claims (G0 F1),
closed client event batch schemas, and ingest conformance checklist tests.
"""
from __future__ import annotations

from conftest import FIXTURES_DIR, load_json

MANIFEST_ID = "https://schemas.contenttree.dev/plugin-spec/manifest.schema.json"
TICKET_ID = "https://schemas.contenttree.dev/plugin-spec/insights/ticket-claims-v1.schema.json"
CLIENT_BATCH_ID = "https://schemas.contenttree.dev/plugin-spec/insights/client-batch-v1.schema.json"


def test_delivery_insight_surface_manifest_rules(validator_factory, schema_by_id):
    validator = validator_factory(schema_by_id[MANIFEST_ID])
    manifest = load_json(FIXTURES_DIR / "manifest" / "valid" / "delivery-insight-surface.json")
    assert validator.is_valid(manifest)

    # Missing delivery:events:read scope must fail
    no_events_scope = {**manifest, "scopes": ["delivery:viewer:pseudonym"]}
    assert not validator.is_valid(no_events_scope)

    # Localhost HTTP origin is explicitly allowed for local conformance testing
    localhost_ep = {
        **manifest["extension_points"][1],
        "ingest_origin": "http://127.0.0.1:18080",
    }
    assert validator.is_valid({**manifest, "extension_points": [manifest["extension_points"][0], localhost_ep]})

    # Unknown event family or smuggled action_id on delivery-insight must fail
    bad_family = {
        **manifest["extension_points"][1],
        "supported_event_families": ["view", "dom.autocapture"],
    }
    assert not validator.is_valid({**manifest, "extension_points": [manifest["extension_points"][0], bad_family]})

    mixed_fields = {
        **manifest["extension_points"][1],
        "action_id": "illegal-action-id",
    }
    assert not validator.is_valid({**manifest, "extension_points": [manifest["extension_points"][0], mixed_fields]})


def test_ticket_claims_f1_string_sub_and_closed_whitelist(validator_factory, schema_by_id):
    validator = validator_factory(schema_by_id[TICKET_ID])
    agg = load_json(FIXTURES_DIR / "insights" / "ticket-claims" / "valid" / "aggregate-node-h5.json")
    pseudo = load_json(FIXTURES_DIR / "insights" / "ticket-claims" / "valid" / "pseudonymous-sub-user.json")
    assert validator.is_valid(agg)
    assert validator.is_valid(pseudo)

    # I-3: forbidden credential/PII fields are rejected at both top-level and ctx
    for bad_key in ("token", "share_token", "sub_user_token", "mobile", "phone", "ip", "user_id"):
        assert not validator.is_valid({**agg, bad_key: "secret"})
        assert not validator.is_valid({**agg, "ctx": {**agg["ctx"], bad_key: "secret"}})

    # Wrong aud (e.g. control-plane invocation token aud without ':ingest') is rejected
    assert not validator.is_valid({**agg, "aud": "plugin:com.contenttree.delivery-insights"})

    # Pseudonymous mode requires non-null vwr.p and non-anon sub
    assert not validator.is_valid({**pseudo, "sub": "anon"})
    assert not validator.is_valid({**pseudo, "vwr": {"k": "sub_user", "p": None, "t": "platform"}})


def test_client_batch_closed_event_families_and_whitelist(validator_factory, schema_by_id):
    validator = validator_factory(schema_by_id[CLIENT_BATCH_ID])
    valid_batch = load_json(FIXTURES_DIR / "insights" / "client-batch" / "valid" / "view-and-feedback-batch.json")
    assert validator.is_valid(valid_batch)

    # Every event variant rejects extra properties (I-9)
    for idx, ev in enumerate(valid_batch["events"]):
        mutated = list(valid_batch["events"])
        mutated[idx] = {**ev, "raw_text": "leaked heading or query"}
        assert not validator.is_valid({**valid_batch, "events": mutated}), f"event[{idx}] accepted extra field"

    # Unknown event type is rejected
    unknown_ev = {"t": "dom.click", "id": "ev_1", "o": "probe"}
    assert not validator.is_valid({**valid_batch, "events": [unknown_ev]})


def test_ingest_conformance_cases_are_complete_and_well_formed(validator_factory, schema_by_id):
    batch_validator = validator_factory(schema_by_id[CLIENT_BATCH_ID])
    doc = load_json(FIXTURES_DIR / "insights" / "ingest-conformance-cases.json")
    assert doc["protocol_version"] == 1
    cases = doc["cases"]
    assert len(cases) >= 10
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids))

    reasons = {c.get("expected_reason") for c in cases if not c["expect_accepted"]}
    assert {
        "batch_too_large",
        "invalid_ticket",
        "expired_ticket",
        "unsupported_version",
        "budget_exceeded",
        "schema_invalid",
        "capability_denied",
        "mode_violation",
    }.issubset(reasons)

    sample_jwt = "eyJhbGciOiJSUzI1NiJ9.eyJpc3MiOiJjb250ZW50dHJlZSJ9.c2ln"
    for case in cases:
        assert case["expected_http_status"] == 204
        if case["expect_accepted"]:
            envelope = {
                "v": 1,
                "ticket": sample_jwt,
                "sent_at": 1731550123456,
                "rt": "host@1.0.0",
                "events": case["events"],
            }
            assert batch_validator.is_valid(envelope), f"accepted case {case['id']} must be schema-valid"
