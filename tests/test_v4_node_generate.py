"""contract_version 4 node.generate BYOA extension point, payload pull
descriptor, context bundle, and result schema conformance tests.
"""
from __future__ import annotations

import hashlib

import pytest

MANIFEST_ID = "https://schemas.contenttree.dev/plugin-spec/manifest.schema.json"
V4_INVOKE_ID = "https://schemas.contenttree.dev/plugin-spec/v4/invoke-request.schema.json"
V4_PAYLOAD_ID = "https://schemas.contenttree.dev/plugin-spec/v4/node-generate-payload-descriptor.schema.json"
V4_RESULT_ID = "https://schemas.contenttree.dev/plugin-spec/v4/node-generate-result.schema.json"

SAMPLE_SHA = hashlib.sha256(b'{"format":"node_generate_context_bundle"}').hexdigest()
SAMPLE_JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6ImN0LWV4ZWN1dG9yLXBheWxvYWQrand0In0.eyJpc3MiOiJjb250ZW50dHJlZSJ9.c2ln"


def test_manifest_accepts_node_generate_extension_point_and_caps_clearance_at_s1(
    validator_factory, schema_by_id
):
    validator = validator_factory(schema_by_id[MANIFEST_ID])
    valid_manifest = {
        "manifest_version": 1,
        "plugin_id": "com.example.byoa-node-gen",
        "name": "Reference Node Generator",
        "version": "1.0.0",
        "runtime": {"type": "http-remote"},
        "supported_contract_versions": [3, 4],
        "endpoints": {
            "invoke": "/actions",
            "operation_status": "/operations/{operation_id}",
        },
        "scopes": [],
        "clearance": "S1",
        "data_handling": {
            "purposes": ["content_generation"],
            "retention": {"mode": "transient"},
            "egress_domains": ["agent.example.com"],
        },
        "capabilities": {
            "payload_pull": True,
            "hmac_keyring": True,
        },
        "extension_points": [
            {
                "type": "node-generate",
                "action_id": "generate",
                "completion_mode": "deferred",
                "timeout_seconds": 3600,
                "input_contract": {
                    "format": "node_generate",
                    "schema_version": 1,
                },
            }
        ],
    }
    assert validator.is_valid(valid_manifest)

    # S0 is also valid (lower than S1)
    assert validator.is_valid({**valid_manifest, "clearance": "S0"})

    # S2 and S3 must be rejected by manifest schema
    assert not validator.is_valid({**valid_manifest, "clearance": "S2"})
    assert not validator.is_valid({**valid_manifest, "clearance": "S3"})

    # node-generate must be deferred and use format=node_generate
    bad_sync = {
        **valid_manifest,
        "extension_points": [
            {
                **valid_manifest["extension_points"][0],
                "completion_mode": "sync",
            }
        ],
    }
    assert not validator.is_valid(bad_sync)


def test_v4_invoke_request_and_payload_descriptor_validate(
    validator_factory, schema_by_id
):
    invoke_validator = validator_factory(schema_by_id[V4_INVOKE_ID])
    payload_desc = {
        "delivery": "pull",
        "url": "https://host.example.com/api/node-executors/jobs/exec-0001/payload",
        "sha256": SAMPLE_SHA,
        "media_type": "application/json",
        "access_token": SAMPLE_JWT,
        "jti": "ept_0001",
        "expires_at": "2026-11-01T10:10:00Z",
    }
    invoke_req = {
        "contract_version": 4,
        "extension_point": "node.generate",
        "invocation_id": "exec-0001",
        "action_id": "generate",
        "source": {
            "tree_id": "tree-0001",
            "snapshot_id": "snap-0001",
            "run_id": "run-0001",
        },
        "payload": payload_desc,
        "node_generate": {
            "execution_id": "exec-0001",
            "node": {
                "node_id": "node-0001",
                "name": "Weekly Summary",
                "description": "Summarize the weekly progress",
            },
            "output_contract": {
                "format": "markdown",
            },
            "deadline_at": "2026-11-01T11:00:00Z",
        },
    }
    assert invoke_validator.is_valid(invoke_req)
    assert not invoke_validator.is_valid({**invoke_req, "contract_version": 3})


def test_v4_context_bundle_and_result_schema_validate(
    validator_factory, schema_by_id
):
    payload_schema = schema_by_id[V4_PAYLOAD_ID]
    bundle_validator = validator_factory(
        {
            "$schema": payload_schema["$schema"],
            "$id": f"{V4_PAYLOAD_ID}#context-bundle",
            "$ref": f"{V4_PAYLOAD_ID}#/$defs/contextBundle",
        }
    )
    bundle = {
        "schema_version": 1,
        "format": "node_generate_context_bundle",
        "execution_id": "exec-0001",
        "bundle_ref": "bundle://exec-0001",
        "bundle_sha256": SAMPLE_SHA,
        "instructions_version": "executor-v1",
        "instructions": "Generate only the target node body.",
        "input": "Context markdown body",
        "output_contract": {"format": "markdown"},
        "provenance": [
            {
                "ref_uri": "wecom_doc://corp/doc-1",
                "content_sha256": SAMPLE_SHA,
                "sensitivity": "S1",
            }
        ],
        "max_sensitivity": "S1",
    }
    assert bundle_validator.is_valid(bundle)

    result_validator = validator_factory(schema_by_id[V4_RESULT_ID])
    inline_cb = {
        "event_id": "evt_exec_0001_done",
        "state": "succeeded",
        "result": {
            "content_markdown": "## Weekly Summary\n\nAll milestones met.",
            "citations": ["wecom_doc://corp/doc-1"],
            "usage_reported": {"mode": "rule_rewrite"},
        },
    }
    assert result_validator.is_valid(inline_cb)

    url_cb = {
        "event_id": "evt_exec_0001_url",
        "state": "succeeded",
        "result": {
            "result_url": "https://agent.example.com/results/exec-0001.json",
        },
    }
    assert result_validator.is_valid(url_cb)

    # Empty result object with neither content_markdown, structured_output, nor result_url is rejected
    assert not result_validator.is_valid(
        {"event_id": "evt_bad", "state": "succeeded", "result": {}}
    )
