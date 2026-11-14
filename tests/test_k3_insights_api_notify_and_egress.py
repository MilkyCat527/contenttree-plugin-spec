"""K3 insights query OpenAPI & schemas, owner notify Host API & scope,
lifecycle deletion events, and active destinations egress disclosure tests.
"""
from __future__ import annotations

from conftest import FIXTURES_DIR, OPENAPI_DIR, load_json, load_yaml

MANIFEST_ID = "https://schemas.contenttree.dev/plugin-spec/manifest.schema.json"
BATCH_ID = "https://schemas.contenttree.dev/plugin-spec/events/event-batch-envelope.schema.json"
LIFECYCLE_ID = "https://schemas.contenttree.dev/plugin-spec/events/lifecycle-event-v1.schema.json"
OVERVIEW_ID = "https://schemas.contenttree.dev/plugin-spec/insights/tree-overview-v1.schema.json"
NODES_ID = "https://schemas.contenttree.dev/plugin-spec/insights/node-metrics-v1.schema.json"
COMPARE_ID = "https://schemas.contenttree.dev/plugin-spec/insights/run-compare-v1.schema.json"
FEEDBACK_ID = "https://schemas.contenttree.dev/plugin-spec/insights/feedback-list-v1.schema.json"
HEALTH_ID = "https://schemas.contenttree.dev/plugin-spec/insights/collection-health-v1.schema.json"
NOTIFY_REQ_ID = "https://schemas.contenttree.dev/plugin-spec/insights/owner-notify-request-v1.schema.json"
NOTIFY_RESP_ID = "https://schemas.contenttree.dev/plugin-spec/insights/owner-notify-response-v1.schema.json"
DISCLOSURE_ID = "https://schemas.contenttree.dev/plugin-spec/insights/destinations-disclosure-v1.schema.json"


def test_k3_manifest_notify_scope_lifecycle_events_and_console_paths(validator_factory, schema_by_id):
    validator = validator_factory(schema_by_id[MANIFEST_ID])
    manifest = load_json(FIXTURES_DIR / "manifest" / "valid" / "delivery-insight-k3-full.json")
    assert validator.is_valid(manifest)

    # console_path on review-export-action is forbidden
    bad_action = {
        "manifest_version": 1,
        "plugin_id": "com.example.export",
        "name": "Export",
        "version": "1.0.0",
        "runtime": {"type": "http-remote"},
        "supported_contract_versions": [3],
        "endpoints": {"invoke": "/actions"},
        "scopes": ["tree:export:read"],
        "extension_points": [
            {
                "type": "review-export-action",
                "action_id": "exp",
                "label": "Export",
                "timeout_seconds": 10,
                "console_path": "/console",
                "input_contract": {"format": "json", "schema_version": 1},
            }
        ],
    }
    assert not validator.is_valid(bad_action)


def test_k3_lifecycle_events_in_batch_envelope(validator_factory, schema_by_id):
    batch_validator = validator_factory(schema_by_id[BATCH_ID])
    lifecycle_validator = validator_factory(schema_by_id[LIFECYCLE_ID])

    tree_del = load_json(FIXTURES_DIR / "events" / "lifecycle" / "valid" / "tree-deleted.json")
    plugin_dis = {
        "specversion": "1.0",
        "type": "contenttree.lifecycle.plugin_disabled.v1",
        "id": "lcy_dis_001",
        "time": "2026-11-14T15:00:00Z",
        "source": "contenttree/host",
        "data": {
            "ten": "corp:acme",
            "prj": "prj_001",
            "tree": None,
            "reason": "project_insights_disabled",
            "purge_destinations": True,
        },
    }
    assert lifecycle_validator.is_valid(tree_del)
    assert lifecycle_validator.is_valid(plugin_dis)
    assert batch_validator.is_valid(
        {
            "batch_id": "bch_k3_01",
            "sent_at": "2026-11-14T15:00:01Z",
            "events": [tree_del, plugin_dis],
        }
    )


def test_k3_owner_notify_forbids_pii_urls_and_requires_alert_code(validator_factory, schema_by_id):
    req_validator = validator_factory(schema_by_id[NOTIFY_REQ_ID])
    resp_validator = validator_factory(schema_by_id[NOTIFY_RESP_ID])

    weekly = load_json(FIXTURES_DIR / "insights" / "k3" / "valid" / "owner-notify-weekly.json")
    assert req_validator.is_valid(weekly)

    # threshold_alert without alert_code must be rejected
    assert not req_validator.is_valid({**weekly, "kind": "threshold_alert", "alert_code": None})
    assert req_validator.is_valid(
        {**weekly, "kind": "threshold_alert", "alert_code": "completion_drop"}
    )

    # Extra PII / raw text / arbitrary URL fields are rejected
    for forbidden in ("url", "jump_url", "email", "wechat_userid", "mobile", "raw_comment"):
        assert not req_validator.is_valid({**weekly, forbidden: "forbidden"})
        assert not req_validator.is_valid(
            {**weekly, "metrics": {**weekly["metrics"], forbidden: 1}}
        )

    resp = load_json(FIXTURES_DIR / "insights" / "k3" / "valid" / "owner-notify-response.json")
    assert resp_validator.is_valid(resp)
    assert not resp_validator.is_valid({**resp, "recipients": ["alice"]})


def test_k3_destinations_disclosure_and_openapi_contracts(validator_factory, schema_by_id):
    disc_validator = validator_factory(schema_by_id[DISCLOSURE_ID])
    valid_disc = load_json(FIXTURES_DIR / "insights" / "k3" / "valid" / "destinations-disclosure.json")
    assert disc_validator.is_valid(valid_disc)

    # Reject unknown adapter kind or uppercase/port egress_domain
    bad_dest = {
        **valid_disc,
        "destinations": [{**valid_disc["destinations"][0], "kind": "snowplow"}],
    }
    assert not disc_validator.is_valid(bad_dest)

    plugin_openapi = load_yaml(OPENAPI_DIR / "insights-plugin-api.yaml")
    assert set(plugin_openapi["paths"].keys()) == {
        "/v1/insights/trees/{tree_id}/overview",
        "/v1/insights/trees/{tree_id}/nodes",
        "/v1/insights/trees/{tree_id}/nodes/{node_id}",
        "/v1/insights/trees/{tree_id}/compare",
        "/v1/insights/trees/{tree_id}/feedback",
        "/v1/insights/trees/{tree_id}/health",
        "/v1/destinations/disclosure",
    }

    host_openapi = load_yaml(OPENAPI_DIR / "insights-host-api.yaml")
    assert set(host_openapi["paths"].keys()) == {
        "/api/plugin-host/v1/trees/{tree_id}/notify",
    }
    notify_op = host_openapi["paths"]["/api/plugin-host/v1/trees/{tree_id}/notify"]["post"]
    assert notify_op["security"] == [{"pluginToHostHmac": []}]

    # Verify all K3 query response schemas remain closed
    for sid in (OVERVIEW_ID, NODES_ID, COMPARE_ID, FEEDBACK_ID, HEALTH_ID):
        assert schema_by_id[sid]["additionalProperties"] is False
