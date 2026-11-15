"""K4 tracking plan, custom & specialized client events, offline export ticket
revocation lifecycle, Hybrid viewer assertion extension, multi-run experiment
evaluation, and M5 destination adapter kind tests.
"""
from __future__ import annotations

from conftest import FIXTURES_DIR, OPENAPI_DIR, load_json, load_yaml

TRACKING_PLAN_ID = "https://schemas.contenttree.dev/plugin-spec/insights/tracking-plan-v1.schema.json"
CUSTOM_EVENTS_ID = "https://schemas.contenttree.dev/plugin-spec/insights/custom-events-v1.schema.json"
EXPERIMENT_ID = "https://schemas.contenttree.dev/plugin-spec/insights/experiment-evaluate-v1.schema.json"
TICKET_ID = "https://schemas.contenttree.dev/plugin-spec/insights/ticket-claims-v1.schema.json"
CLIENT_BATCH_ID = "https://schemas.contenttree.dev/plugin-spec/insights/client-batch-v1.schema.json"
LIFECYCLE_ID = "https://schemas.contenttree.dev/plugin-spec/events/lifecycle-event-v1.schema.json"
SERVED_ID = "https://schemas.contenttree.dev/plugin-spec/events/delivery-served-v1.schema.json"
DISCLOSURE_ID = "https://schemas.contenttree.dev/plugin-spec/insights/destinations-disclosure-v1.schema.json"
HEALTH_ID = "https://schemas.contenttree.dev/plugin-spec/insights/collection-health-v1.schema.json"


def test_k4_tracking_plan_rejects_free_text_and_requires_enum_values(validator_factory, schema_by_id):
    validator = validator_factory(schema_by_id[TRACKING_PLAN_ID])
    plan = load_json(FIXTURES_DIR / "insights" / "k4" / "valid" / "tracking-plan.json")
    assert validator.is_valid(plan)

    # Reject free-text property types and enum without enum_values
    bad_text = load_json(FIXTURES_DIR / "insights" / "k4" / "invalid" / "tracking-plan-free-text-prop.json")
    assert not validator.is_valid(bad_text)

    bad_enum = {
        **plan,
        "events": [
            {
                **plan["events"][0],
                "properties": [{"name": "mode", "type": "enum", "required": True, "enum_values": None}],
            }
        ],
    }
    assert not validator.is_valid(bad_enum)

    # Boolean property must not carry enum_values
    bad_bool = {
        **plan,
        "events": [
            {
                **plan["events"][0],
                "properties": [{"name": "passed", "type": "boolean", "required": True, "enum_values": ["yes"]}],
            }
        ],
    }
    assert not validator.is_valid(bad_bool)


def test_k4_client_batch_custom_and_s8_events_forbid_free_text(validator_factory, schema_by_id):
    validator = validator_factory(schema_by_id[CLIENT_BATCH_ID])
    batch = load_json(FIXTURES_DIR / "insights" / "k4" / "valid" / "custom-and-specialized-batch.json")
    assert validator.is_valid(batch)

    bad_prose = load_json(FIXTURES_DIR / "insights" / "k4" / "invalid" / "custom-event-free-text-value.json")
    assert not validator.is_valid(bad_prose)

    # Extra undeclared properties on custom/tour/model3d events are rejected
    for ev in batch["events"]:
        assert not validator.is_valid({**batch, "events": [{**ev, "raw_dom_html": "<div>leak</div>"}]})


def test_k4_ticket_claims_tp_ext_va_and_exp_ctx_extensions(validator_factory, schema_by_id):
    validator = validator_factory(schema_by_id[TICKET_ID])
    base = load_json(FIXTURES_DIR / "insights" / "ticket-claims" / "valid" / "aggregate-node-h5.json")
    extended = {
        **base,
        "srf": "export.offline",
        "tier": "export",
        "cap": ["view", "custom", "tour", "model3d"],
        "tp": {
            "v": 2,
            "d": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            "ev": {"practice_submit": {"attempt": "enum:first|retry!", "score": "number:0:100", "passed": "boolean!"}},
        },
        "ext_va": "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1XzEifQ.c2ln",
        "exp_ctx": {"id": "exp_01", "var": "variant_b"},
    }
    assert validator.is_valid(extended)
    assert not validator.is_valid({**extended, "ext_va": "not-a-compact-jwt"})
    assert not validator.is_valid({**extended, "exp_ctx": {"id": "exp_01", "var": "b", "secret": "x"}})


def test_k4_lifecycle_ticket_revocation_and_served_surfaces(validator_factory, schema_by_id):
    lcy_validator = validator_factory(schema_by_id[LIFECYCLE_ID])
    revoked_ev = {
        "specversion": "1.0",
        "type": "contenttree.lifecycle.ticket_revoked.v1",
        "id": "lcy_rev_001",
        "time": "2026-11-15T01:00:00Z",
        "source": "contenttree/host",
        "data": {
            "ten": "corp:acme",
            "prj": "prj_001",
            "tree": "tree_001",
            "reason": "export_ticket_revoked",
            "purge_destinations": False,
            "revoked_jti": "jti_export_001",
        },
    }
    assert lcy_validator.is_valid(revoked_ev)
    # Missing revoked_jti must be rejected when type is ticket_revoked.v1
    assert not lcy_validator.is_valid({**revoked_ev, "data": {**revoked_ev["data"], "revoked_jti": None}})

    served_validator = validator_factory(schema_by_id[SERVED_ID])
    base_served = load_json(FIXTURES_DIR / "events" / "delivery-served" / "valid" / "authorized-node-h5.json")
    for srf, src in (
        ("dashboard.artifact", "dashboard"),
        ("tour.view", "tour"),
        ("model3d.view", "model3d"),
        ("export.offline", "skin"),
    ):
        ev = {
            **base_served,
            "data": {
                **base_served["data"],
                "srf": srf,
                "ctx": {**base_served["data"]["ctx"], "src": src},
                "tp_ver": 2,
                "exp_ctx": {"id": "exp_01", "var": "treatment_a"},
            },
        }
        assert served_validator.is_valid(ev), f"served surface {srf} should validate"


def test_k4_m5_destinations_health_and_openapi_routes(validator_factory, schema_by_id):
    disc_validator = validator_factory(schema_by_id[DISCLOSURE_ID])
    base_disc = load_json(FIXTURES_DIR / "insights" / "k3" / "valid" / "destinations-disclosure.json")
    for kind in ("xapi_lrs", "clickhouse_http", "tencent_cls", "sensors_http"):
        mutated = {
            **base_disc,
            "destinations": [{**base_disc["destinations"][0], "kind": kind}],
        }
        assert disc_validator.is_valid(mutated), f"destination kind {kind} must validate"

    health_validator = validator_factory(schema_by_id[HEALTH_ID])
    base_health = load_json(FIXTURES_DIR / "insights" / "k3" / "valid" / "collection-health.json")
    assert health_validator.is_valid(
        {
            **base_health,
            "unknown_custom_event_count": 3,
            "unknown_custom_events_by_name": {"rogue_click": 3},
            "revoked_ticket_rejections": 1,
            "by_runtime": {"host@1.1.0": 15, "headless@1.0.0": 4},
        }
    )

    plugin_openapi = load_yaml(OPENAPI_DIR / "insights-plugin-api.yaml")
    for k4_path in (
        "/v1/insights/trees/{tree_id}/tracking-plan",
        "/v1/insights/trees/{tree_id}/custom-events",
        "/v1/insights/trees/{tree_id}/experiments/{experiment_id}",
        "/v1/insights/tickets/{jti}/revoke",
        "/v1/identity/verifiers",
    ):
        assert k4_path in plugin_openapi["paths"]

    for sid in (TRACKING_PLAN_ID, CUSTOM_EVENTS_ID, EXPERIMENT_ID):
        assert schema_by_id[sid]["additionalProperties"] is False
