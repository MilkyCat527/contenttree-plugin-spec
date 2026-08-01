"""Governance-surface rules: restricted options subset, publisher risk
declarations, and the hosted artifact descriptor.

These assertions are deliberately expressed as *behavioral probes against
the published schemas* rather than as a re-statement of the schema text:
each case describes a decision a host has to make ("may a plugin declare
this?") and pins the answer, so a future schema edit that quietly widens
the accepted surface fails here even if every fixture still passes.
"""
from __future__ import annotations

import pytest

FIELDS_ID = "https://schemas.contenttree.dev/plugin-spec/common/fields.schema.json"
OPTIONS_ID = "https://schemas.contenttree.dev/plugin-spec/common/options-schema.schema.json"
DESCRIPTOR_ID = "https://schemas.contenttree.dev/plugin-spec/artifact-descriptor.schema.json"


def _field_validator(schema_by_id, validator_factory, def_name: str):
    return validator_factory(schema_by_id[FIELDS_ID]["$defs"][def_name])


# --------------------------------------------------------------------------
# egress domains must be enumerable
# --------------------------------------------------------------------------

EGRESS_CASES = [
    ("courseware.example.com", True, "plain FQDN"),
    ("cdn.eu.courseware.example.com", True, "multi-label FQDN"),
    ("a-b.example.com", True, "internal hyphen"),
    ("*", False, "bare wildcard"),
    ("*.example.com", False, "wildcard label"),
    ("example", False, "single label / bare TLD"),
    ("Example.com", False, "uppercase would break byte comparison against an allowlist"),
    ("https://example.com", False, "scheme is not part of a DNS name"),
    ("example.com:443", False, "port is not part of a DNS name"),
    ("example.com/path", False, "path is not part of a DNS name"),
    ("-example.com", False, "label may not start with a hyphen"),
    ("example.com\n", False, "trailing line terminator must not sneak past the anchor"),
]


@pytest.mark.parametrize(
    "value,expected,reason",
    EGRESS_CASES,
    ids=[f"{v!r}-{'ok' if ok else 'rejected'}" for v, ok, _ in EGRESS_CASES],
)
def test_egress_domain_rule(value, expected, reason, schema_by_id, validator_factory):
    validator = _field_validator(schema_by_id, validator_factory, "egressDomain")
    assert validator.is_valid(value) is expected, f"{value!r} ({reason})"


def test_retention_mode_is_a_closed_vocabulary(schema_by_id, validator_factory):
    validator = _field_validator(schema_by_id, validator_factory, "retentionPolicy")
    assert validator.is_valid({"mode": "none"})
    assert validator.is_valid({"mode": "stored", "days": 30})
    assert not validator.is_valid({"mode": "forever"})
    assert not validator.is_valid({"mode": "stored", "days": -1})
    assert not validator.is_valid({"mode": "stored", "unbounded": True})


def test_data_handling_cannot_suppress_host_derived_categories(schema_by_id):
    """The publisher declaration has no 'categories'/'exclude' surface at
    all: a host derives data categories from granted scopes and the action's
    input_contract, and a plugin can only add narrative on top."""
    data_handling = schema_by_id[FIELDS_ID]["$defs"]["dataHandling"]
    assert data_handling["additionalProperties"] is False
    assert set(data_handling["properties"]) == {
        "purposes",
        "retention",
        "egress_domains",
        "subprocessors",
        "privacy_url",
        "processing_location",
    }


def test_capabilities_default_to_false_so_legacy_manifests_are_unchanged(schema_by_id):
    caps = schema_by_id[FIELDS_ID]["$defs"]["pluginCapabilities"]
    assert caps["additionalProperties"] is False
    for name, definition in caps["properties"].items():
        assert definition["default"] is False, f"capability {name} must default to false"


def test_hmac_key_id_is_an_opaque_public_label(schema_by_id, validator_factory):
    validator = _field_validator(schema_by_id, validator_factory, "hmacKeyId")
    assert validator.is_valid("a1b2c3d4e5f60718")
    assert not validator.is_valid("")
    assert not validator.is_valid("has space")
    assert not validator.is_valid("x" * 65)


# --------------------------------------------------------------------------
# restricted options subset
# --------------------------------------------------------------------------

REJECTED_TOP_LEVEL_KEYWORDS = [
    "$ref",
    "$defs",
    "oneOf",
    "anyOf",
    "allOf",
    "not",
    "if",
    "then",
    "else",
    "patternProperties",
    "unevaluatedProperties",
    "propertyNames",
    "dependentSchemas",
]


@pytest.mark.parametrize("keyword", REJECTED_TOP_LEVEL_KEYWORDS)
def test_options_schema_rejects_unsupported_top_level_keyword(
    keyword, schema_by_id, validator_factory
):
    validator = validator_factory(schema_by_id[OPTIONS_ID])
    instance = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"mode": {"type": "string"}},
        keyword: True,
    }
    assert not validator.is_valid(instance), (
        f"{keyword} must be rejected outright, not silently ignored: a host and a "
        "plugin can never be allowed to disagree about what a declaration means"
    )


REJECTED_FIELD_KEYWORDS = ["pattern", "format", "$ref", "oneOf", "not", "contentEncoding"]


@pytest.mark.parametrize("keyword", REJECTED_FIELD_KEYWORDS)
def test_options_schema_rejects_unsupported_field_keyword(
    keyword, schema_by_id, validator_factory
):
    validator = validator_factory(schema_by_id[OPTIONS_ID])
    instance = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"mode": {"type": "string", keyword: "whatever"}},
    }
    assert not validator.is_valid(instance)


def test_options_schema_caps_field_count_at_twenty(schema_by_id, validator_factory):
    validator = validator_factory(schema_by_id[OPTIONS_ID])
    twenty = {
        "type": "object",
        "additionalProperties": False,
        "properties": {f"f{i:02d}": {"type": "string"} for i in range(20)},
    }
    twenty_one = {
        "type": "object",
        "additionalProperties": False,
        "properties": {f"f{i:02d}": {"type": "string"} for i in range(21)},
    }
    assert validator.is_valid(twenty)
    assert not validator.is_valid(twenty_one)


def test_options_schema_nesting_depth_is_capped_at_two(schema_by_id, validator_factory):
    validator = validator_factory(schema_by_id[OPTIONS_ID])
    scalar_array = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"tags": {"type": "array", "items": {"type": "string"}}},
    }
    array_of_arrays = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "matrix": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}}
        },
    }
    assert validator.is_valid(scalar_array)
    assert not validator.is_valid(array_of_arrays)


def test_options_ui_widget_vocabulary_is_closed(schema_by_id, validator_factory):
    validator = validator_factory(schema_by_id[OPTIONS_ID])
    allowed = schema_by_id[OPTIONS_ID]["$defs"]["uiHint"]["properties"]["widget"]["enum"]
    assert allowed == ["text", "textarea", "select", "radio", "checkbox", "number"]
    for widget in allowed:
        assert validator.is_valid(
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {"mode": {"type": "string", "x-contenttree-ui": {"widget": widget}}},
            }
        )
    assert not validator.is_valid(
        {
            "type": "object",
            "additionalProperties": False,
            "properties": {"mode": {"type": "string", "x-contenttree-ui": {"widget": "iframe"}}},
        }
    )


def test_manifest_options_schema_is_the_restricted_subset(schema_by_id):
    manifest = schema_by_id["https://schemas.contenttree.dev/plugin-spec/manifest.schema.json"]
    ep = manifest["$defs"]["extensionPoint"]["properties"]
    assert ep["options_schema"]["$ref"] == "common/options-schema.schema.json"


# --------------------------------------------------------------------------
# hosted artifact descriptor
# --------------------------------------------------------------------------

ARTIFACT_PATH_CASES = [
    ("scf_bootstrap", True, "plain root-level file"),
    ("bin/scf_bootstrap", True, "nested file"),
    ("sbom.spdx.json", True, "dotted file name"),
    ("/usr/bin/env", False, "absolute path"),
    ("../escape", False, "parent traversal"),
    ("a/../escape", False, "traversal in the middle"),
    ("a\\b", False, "backslash separator"),
    ("a//b", False, "empty segment"),
    ("a%2fb", False, "percent encoding"),
    ("scf_bootstrap\n", False, "trailing line terminator"),
]


@pytest.mark.parametrize(
    "value,expected,reason",
    ARTIFACT_PATH_CASES,
    ids=[f"{v!r}-{'ok' if ok else 'rejected'}" for v, ok, _ in ARTIFACT_PATH_CASES],
)
def test_artifact_relative_path_rule(value, expected, reason, schema_by_id, validator_factory):
    definition = schema_by_id[DESCRIPTOR_ID]["$defs"]["artifactRelativePath"]
    assert validator_factory(definition).is_valid(value) is expected, f"{value!r} ({reason})"


def test_descriptor_does_not_carry_its_own_artifact_digest(schema_by_id):
    """A descriptor living inside the artifact cannot state that artifact's
    digest without being self-referential; the host computes the content
    address after upload and treats it, not this document, as identity."""
    descriptor = schema_by_id[DESCRIPTOR_ID]
    assert descriptor["additionalProperties"] is False
    digest_like = [k for k in descriptor["properties"] if "sha" in k or "digest" in k]
    assert digest_like == []


def test_descriptor_separates_deployment_configuration_from_options(schema_by_id):
    """Deployment configuration keys are uppercase and may be marked secret;
    per-invocation options are identifier-shaped and have no secret marker at
    all. The two surfaces must not converge."""
    descriptor = schema_by_id[DESCRIPTOR_ID]
    config_field = descriptor["$defs"]["configurationField"]["properties"]
    assert "x-contenttree-secret" in config_field

    option_field = schema_by_id[OPTIONS_ID]["$defs"]["optionField"]["properties"]
    assert not any("secret" in key for key in option_field)
