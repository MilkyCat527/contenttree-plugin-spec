"""K1 delivery event subscription, CloudEvents batch envelope, and
contenttree.delivery.served.v1 conformance tests.
"""
from __future__ import annotations

MANIFEST_ID = "https://schemas.contenttree.dev/plugin-spec/manifest.schema.json"
SERVED_ID = "https://schemas.contenttree.dev/plugin-spec/events/delivery-served-v1.schema.json"
BATCH_ID = "https://schemas.contenttree.dev/plugin-spec/events/event-batch-envelope.schema.json"
ACK_ID = "https://schemas.contenttree.dev/plugin-spec/events/event-batch-response.schema.json"


def test_event_subscription_manifest_rules(validator_factory, schema_by_id):
    validator = validator_factory(schema_by_id[MANIFEST_ID])
    manifest = {
        "manifest_version": 1,
        "plugin_id": "com.example.insights",
        "name": "Delivery Insights",
        "version": "0.1.0",
        "runtime": {"type": "http-remote"},
        "supported_contract_versions": [3],
        "endpoints": {"events": "/events"},
        "scopes": ["delivery:events:read", "delivery:audience:dims"],
        "extension_points": [
            {
                "type": "event-subscription",
                "subscription_id": "delivery-served",
                "event_types": ["contenttree.delivery.served.v1"],
                "receive_path": "/events",
                "timeout_seconds": 10,
            }
        ],
    }
    assert validator.is_valid(manifest)
    # Missing delivery:events:read scope must fail
    assert not validator.is_valid({**manifest, "scopes": ["delivery:audience:dims"]})
    # Absolute URL in receive_path must fail
    bad_path = {
        **manifest,
        "extension_points": [
            {**manifest["extension_points"][0], "receive_path": "https://evil.example.com/events"}
        ],
    }
    assert not validator.is_valid(bad_path)
    # Action plugin without endpoints.invoke still fails
    bad_action = {
        **manifest,
        "scopes": ["tree:export:read"],
        "extension_points": [
            {
                "type": "review-export-action",
                "action_id": "export",
                "label": "Export",
                "timeout_seconds": 10,
                "input_contract": {"format": "json", "schema_version": 1},
            }
        ],
    }
    assert not validator.is_valid(bad_action)


def test_delivery_served_batch_and_ack_whitelist(validator_factory, schema_by_id):
    batch_validator = validator_factory(schema_by_id[BATCH_ID])
    ack_validator = validator_factory(schema_by_id[ACK_ID])

    event = {
        "specversion": "1.0",
        "type": "contenttree.delivery.served.v1",
        "id": "srv_test_01",
        "time": "2026-11-14T08:00:00Z",
        "source": "contenttree/host",
        "data": {
            "jti": "jti_test_01",
            "ten": "corp_a",
            "ctx": {"prj": "p1", "tree": "t1", "node": "n1", "run": "r1", "snap": "s1", "src": "skin"},
            "srf": "share.node_h5",
            "tier": "anonymous",
            "lnk": "lnk_1",
            "chn": None,
            "dims": {},
            "has_content": True,
            "ua_class": "mobile",
            "ref_host": "docs.example.com",
            "bot": False,
        },
    }
    batch = {"batch_id": "bch_01", "sent_at": "2026-11-14T08:00:01Z", "events": [event]}
    assert batch_validator.is_valid(batch)

    # Rejects IP, token, or content fields at data level
    for forbidden_key in ("ip", "token", "generated_content", "html"):
        leaked = {**event, "data": {**event["data"], forbidden_key: "secret"}}
        assert not batch_validator.is_valid({**batch, "events": [leaked]})

    # Rejects query/path in ref_host
    bad_ref = {**event, "data": {**event["data"], "ref_host": "docs.example.com/path?token=1"}}
    assert not batch_validator.is_valid({**batch, "events": [bad_ref]})

    assert ack_validator.is_valid({"status": "ok", "accepted": 1, "duplicates": 0})
    assert not ack_validator.is_valid({"status": "ok", "accepted": -1, "duplicates": 0})
