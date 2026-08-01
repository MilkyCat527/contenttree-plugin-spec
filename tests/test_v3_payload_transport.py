"""contract_version 3 payload transport and Host Access Token invariants.

The interesting properties of v3 are not "does this instance validate"
(the indexed fixtures cover that) but the structural guarantees that make
the new transport safe to negotiate at all: the two payload modes must be
mutually exclusive rather than conventionally distinct, the integrity
metadata must be identical in both modes, the pull credential must be
unusable anywhere else, and v3 must remain a strict superset of v2's
non-payload envelope so a plugin upgrades by adding payload handling
rather than by implementing a second protocol.
"""
from __future__ import annotations

import copy
import hashlib
import json

import pytest

FIELDS_ID = "https://schemas.contenttree.dev/plugin-spec/common/fields.schema.json"
V2_REQUEST_ID = "https://schemas.contenttree.dev/plugin-spec/v2/invoke-request.schema.json"
V3_REQUEST_ID = "https://schemas.contenttree.dev/plugin-spec/v3/invoke-request.schema.json"
DESCRIPTOR_ID = "https://schemas.contenttree.dev/plugin-spec/v3/payload-descriptor.schema.json"
CLAIMS_ID = "https://schemas.contenttree.dev/plugin-spec/v3/host-access-token-claims.schema.json"

TREE = {"title": "Sample tree", "nodes": [{"name": "Chapter 1", "type": "chapter"}]}
TREE_BYTES = json.dumps(TREE, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
TREE_SHA = hashlib.sha256(TREE_BYTES).hexdigest()
JWT = (
    "eyJhbGciOiJSUzI1NiIsInR5cCI6ImN0LWhvc3QtYWNjZXNzK2p3dCJ9"
    ".eyJpc3MiOiJjb250ZW50dHJlZSJ9.c2lnbmF0dXJlLXBsYWNlaG9sZGVy"
)

INLINE = {
    "mode": "inline",
    "media_type": "application/json",
    "sha256": TREE_SHA,
    "size_bytes": len(TREE_BYTES),
    "data": TREE,
}
PULL = {
    "mode": "pull",
    "media_type": "application/json",
    "sha256": TREE_SHA,
    "size_bytes": 7340032,
    "url": "https://host.example.com/api/plugin-host/v1/invocations/inv-conformance-0001/payload",
    "access_token": JWT,
    "expires_at": "2025-06-15T15:18:10Z",
}


# --------------------------------------------------------------------------
# the two modes are structurally exclusive
# --------------------------------------------------------------------------


def test_exactly_one_payload_mode_ever_matches(validator_factory, schema_by_id):
    """Both branches are closed objects with a const discriminator, so the
    oneOf can never match twice — a plugin never has to decide which of two
    simultaneously valid readings the host meant."""
    validator = validator_factory(schema_by_id[DESCRIPTOR_ID])
    assert validator.is_valid(INLINE)
    assert validator.is_valid(PULL)

    hybrid = {**PULL, "data": TREE}
    assert not validator.is_valid(hybrid)


def test_pull_mode_never_carries_payload_content(schema_by_id):
    pull_def = schema_by_id[DESCRIPTOR_ID]["$defs"]["pullPayload"]
    assert pull_def["additionalProperties"] is False
    assert "data" not in pull_def["properties"]


def test_both_modes_publish_the_same_integrity_metadata(schema_by_id):
    """Verification must not depend on which transport the host chose."""
    defs = schema_by_id[DESCRIPTOR_ID]["$defs"]
    common = {"mode", "media_type", "sha256", "size_bytes"}
    assert common <= set(defs["inlinePayload"]["required"])
    assert common <= set(defs["pullPayload"]["required"])


def test_size_ceiling_is_part_of_the_contract(validator_factory, schema_by_id):
    validator = validator_factory(schema_by_id[DESCRIPTOR_ID]["$defs"]["sizeBytes"])
    fifty_mib = 50 * 1024 * 1024
    assert validator.is_valid(fifty_mib)
    assert not validator.is_valid(fifty_mib + 1)
    assert not validator.is_valid(-1)


def test_pull_url_must_be_an_absolute_https_url(validator_factory, schema_by_id):
    validator = validator_factory(schema_by_id[DESCRIPTOR_ID])
    for bad in (
        "http://host.example.com/api/plugin-host/v1/invocations/x/payload",
        "/api/plugin-host/v1/invocations/x/payload",
        "https://cos.example.com/bucket/object?signature=abc#f",
    ):
        instance = {**PULL, "url": bad}
        if bad.startswith("https://"):
            # A third-party pre-signed URL is a policy violation the schema
            # cannot detect; assert only that the shape stays HTTPS-absolute.
            assert validator.is_valid(instance)
            continue
        assert not validator.is_valid(instance), bad


# --------------------------------------------------------------------------
# v3 is a superset of v2's non-payload envelope
# --------------------------------------------------------------------------


def test_v3_keeps_every_v2_field_except_the_inlined_tree(schema_by_id):
    v2 = set(schema_by_id[V2_REQUEST_ID]["properties"])
    v3 = set(schema_by_id[V3_REQUEST_ID]["properties"])
    assert v2 - v3 == {"tree"}, "v3 must not drop any v2 field other than the inlined tree"
    assert v3 - v2 == {"payload"}


def test_v3_rejects_a_lingering_top_level_tree(validator_factory, schema_by_id):
    validator = validator_factory(schema_by_id[V3_REQUEST_ID])
    request = {
        "contract_version": 3,
        "invocation_id": "inv-conformance-0001",
        "action_id": "upload-to-courseware",
        "user": {"id": "user-0001"},
        "project_id": "proj-0001",
        "source": {"tree_id": "tree-0001", "snapshot_id": None, "run_id": None},
        "payload": INLINE,
        "host_api_base_url": "https://host.example.com",
    }
    assert validator.is_valid(request)

    with_tree = copy.deepcopy(request)
    with_tree["tree"] = TREE
    assert not validator.is_valid(with_tree)


def test_options_stay_on_the_request_body_in_both_modes(schema_by_id):
    """Options are small, signed, and part of what the user confirmed, so
    they are never moved behind the payload descriptor where a plugin would
    have to fetch before it could know what was requested."""
    assert "options" in schema_by_id[V3_REQUEST_ID]["properties"]
    for branch in ("inlinePayload", "pullPayload"):
        assert "options" not in schema_by_id[DESCRIPTOR_ID]["$defs"][branch]["properties"]


def test_contract_version_vocabulary_grew_additively(schema_by_id):
    assert schema_by_id[FIELDS_ID]["$defs"]["contractVersion"]["enum"] == [1, 2, 3]


# --------------------------------------------------------------------------
# Host Access Token is unusable outside the payload endpoint
# --------------------------------------------------------------------------


CLAIMS = {
    "iss": "contenttree",
    "aud": ["contenttree-plugin-host", "https://host.example.com"],
    "sub": "plugin:com.example.courseware",
    "jti": "b2c3d4e5-0001",
    "invocation_id": "inv-conformance-0001",
    "deployment_id": "dep-0001",
    "scope": "invocation:payload:read",
    "iat": 1750000000,
    "nbf": 1750000000,
    "exp": 1750000600,
}


def test_host_access_token_pins_issuer_audience_scope(validator_factory, schema_by_id):
    validator = validator_factory(schema_by_id[CLAIMS_ID])
    assert validator.is_valid(CLAIMS)
    assert not validator.is_valid({**CLAIMS, "iss": "https://idp.example.com"})
    assert not validator.is_valid({**CLAIMS, "scope": "invocation:payload:*"})
    assert not validator.is_valid({**CLAIMS, "aud": ["contenttree-plugin-host"]})


@pytest.mark.parametrize("claim", ["invocation_id", "deployment_id", "scope", "exp", "nbf"])
def test_host_access_token_binding_claims_are_required(claim, validator_factory, schema_by_id):
    validator = validator_factory(schema_by_id[CLAIMS_ID])
    reduced = {k: v for k, v in CLAIMS.items() if k != claim}
    assert not validator.is_valid(reduced)


def test_host_access_token_carries_no_personal_data(schema_by_id):
    claims = schema_by_id[CLAIMS_ID]
    assert claims["additionalProperties"] is False
    forbidden = {"mobile", "username", "name", "email", "wechat_userid", "user", "tree"}
    assert forbidden & set(claims["properties"]) == set()


def test_plugin_and_user_subject_namespaces_are_disjoint(validator_factory, schema_by_id):
    validator = validator_factory(schema_by_id[CLAIMS_ID]["properties"]["sub"])
    assert validator.is_valid("plugin:com.example.courseware")
    assert not validator.is_valid("user-0001")
    assert not validator.is_valid("plugin:")
    assert not validator.is_valid("plugin:x\n")
