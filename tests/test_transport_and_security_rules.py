"""Transport-level rules (docs/security.md): HTTPS-origin-only enforcement
for host_api_base_url (with the documented local-test exception), normalized
host_api_route_prefix validation, the browser assertion's required claims +
the one-time (single-use jti) semantic marker, and the exact callback response
field set.
"""
from __future__ import annotations

import pytest

from conftest import DOCS_DIR

SECURITY_MD_TEXT = (DOCS_DIR / "security.md").read_text(encoding="utf-8")
PROTOCOL_MD_TEXT = (DOCS_DIR / "protocol.md").read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# host_api_base_url HTTPS-origin rule + local test exception
# --------------------------------------------------------------------------

HOST_API_BASE_URL_CASES = [
    ("https://host.example.com", True, "plain https origin"),
    ("https://host.example.com:8443", True, "https origin with explicit port"),
    ("http://localhost", True, "documented local test exception (bare localhost)"),
    ("http://localhost:4010", True, "documented local test exception (localhost with port)"),
    ("http://127.0.0.1", True, "documented local test exception (bare loopback IP)"),
    ("http://127.0.0.1:4010", True, "documented local test exception (loopback IP with port)"),
    ("http://host.example.com", False, "plain http, non-local — MUST be rejected"),
    ("https://host.example.com/api", False, "path component not allowed (anti-SSRF origin-only rule)"),
    ("https://host.example.com/NewContentTree", False, "gateway route prefix must remain a separate field"),
    ("https://host.example.com?x=1", False, "query component not allowed"),
    ("https://host.example.com#frag", False, "fragment component not allowed"),
    ("https://host.example.com\n", False, "line terminator after origin"),
    ("ftp://host.example.com", False, "non-HTTP(S) scheme"),
    ("http://169.254.169.254", False, "non-localhost private/link-local IP is NOT part of the documented exception"),
    ("http://example.localhost", False, "hostname merely containing 'localhost' is not the literal localhost host"),
]


@pytest.mark.parametrize(
    "value,expected_valid,reason",
    HOST_API_BASE_URL_CASES,
    ids=[f"{v!r}-{'valid' if ok else 'invalid'}" for v, ok, _ in HOST_API_BASE_URL_CASES],
)
def test_host_api_base_url_https_origin_rule(value, expected_valid, reason, schema_by_id, validator_factory):
    fields = schema_by_id["https://schemas.contenttree.dev/plugin-spec/common/fields.schema.json"]
    validates = validator_factory(fields["$defs"]["hostApiBaseUrl"]).is_valid(value)
    assert validates is expected_valid, f"{value!r} ({reason}): expected schema validity={expected_valid}, got {validates}"


def test_host_api_base_url_local_exception_is_documented():
    assert "http://localhost" in SECURITY_MD_TEXT
    assert "127.0.0.1" in SECURITY_MD_TEXT
    assert "local conformance testing" in SECURITY_MD_TEXT


# --------------------------------------------------------------------------
# Optional host_api_route_prefix normalized absolute-path rule
# --------------------------------------------------------------------------

HOST_API_ROUTE_PREFIX_CASES = [
    ("/NewContentTree", True, "single-segment gateway mount"),
    ("/gateway/ContentTree-v2", True, "multi-segment gateway mount"),
    ("/~tenant/@contenttree:prod", True, "unencoded RFC 3986 pchar segments"),
    ("", False, "present-but-empty is invalid; omit the optional field instead"),
    ("/", False, "root mount is represented by omission, not slash"),
    ("NewContentTree", False, "relative path"),
    ("/NewContentTree/", False, "trailing slash"),
    ("/NewContentTree?tenant=one", False, "query"),
    ("/NewContentTree#fragment", False, "fragment"),
    ("/New%43ontentTree", False, "percent encoding"),
    ("/New\\ContentTree", False, "backslash"),
    ("/gateway//NewContentTree", False, "empty segment"),
    ("/gateway/./NewContentTree", False, "dot segment"),
    ("/gateway/../NewContentTree", False, "dot-dot segment"),
    ("https://gateway.example.com/NewContentTree", False, "scheme and authority"),
    ("//gateway.example.com/NewContentTree", False, "authority"),
    ("/NewContentTree\n", False, "line terminator after otherwise valid prefix"),
]


@pytest.mark.parametrize(
    "value,expected_valid,reason",
    HOST_API_ROUTE_PREFIX_CASES,
    ids=[f"{v!r}-{'valid' if ok else 'invalid'}" for v, ok, _ in HOST_API_ROUTE_PREFIX_CASES],
)
def test_host_api_route_prefix_normalized_absolute_path_rule(
    value, expected_valid, reason, schema_by_id, validator_factory
):
    fields = schema_by_id["https://schemas.contenttree.dev/plugin-spec/common/fields.schema.json"]
    validates = validator_factory(fields["$defs"]["hostApiRoutePrefix"]).is_valid(value)
    assert validates is expected_valid, f"{value!r} ({reason}): expected schema validity={expected_valid}, got {validates}"


def test_v2_invoke_route_prefix_is_optional_and_uses_shared_definition(schema_by_id):
    schema = schema_by_id["https://schemas.contenttree.dev/plugin-spec/v2/invoke-request.schema.json"]
    assert "host_api_base_url" in schema["required"]
    assert "host_api_route_prefix" not in schema["required"]
    assert schema["properties"]["host_api_base_url"]["$ref"].endswith("#/$defs/hostApiBaseUrl")
    assert schema["properties"]["host_api_route_prefix"]["$ref"].endswith("#/$defs/hostApiRoutePrefix")


def test_gateway_callback_url_construction_is_documented():
    template = "{host_api_base_url}{host_api_route_prefix or ''}/api/plugin-host/"
    assert template in PROTOCOL_MD_TEXT
    assert template in SECURITY_MD_TEXT


def test_https_only_no_redirects_rule_is_documented():
    text = SECURITY_MD_TEXT
    assert "MUST be made over HTTPS" in text
    assert "MUST NOT follow redirects" in text
    for surface in ["host_api_base_url", "endpoints.operation_status", "launch_url", "result_url"]:
        assert surface in text, f"HTTPS-only rule prose must name {surface!r} as an in-scope surface"


# --------------------------------------------------------------------------
# Browser assertion required claims + one-time (single-use jti) semantics
# --------------------------------------------------------------------------


def test_assertion_claims_schema_requires_all_nine_claims(schema_by_id):
    schema = schema_by_id["https://schemas.contenttree.dev/plugin-spec/v2/interaction-assertion-claims.schema.json"]
    expected = {"iss", "aud", "sub", "exp", "iat", "jti", "invocation_id", "tree_id", "purpose"}
    assert set(schema["required"]) == expected


def test_jti_single_use_semantic_marker_is_documented():
    """docs/security.md must contain an explicit, unambiguous one-time-use
    marker for jti — not merely mention the claim name."""
    assert "single-use" in SECURITY_MD_TEXT
    assert "jti" in SECURITY_MD_TEXT
    # The specific normative sentence establishing single-use semantics.
    assert "MUST be treated as **single-use**" in SECURITY_MD_TEXT or "MUST be treated as single-use" in SECURITY_MD_TEXT
    assert "already consumed" in SECURITY_MD_TEXT


def test_rs256_only_algorithm_rule_is_documented():
    assert "RS256 only" in SECURITY_MD_TEXT
    assert '`none`' in SECURITY_MD_TEXT or "none" in SECURITY_MD_TEXT


def test_assertion_purpose_is_fixed_audience_confusion_guard(schema_by_id):
    fields = schema_by_id["https://schemas.contenttree.dev/plugin-spec/common/fields.schema.json"]
    purpose_def = fields["$defs"]["assertionPurpose"]
    assert purpose_def["const"] == "plugin_interaction"


# --------------------------------------------------------------------------
# Exact callback response field set (cross-referenced with docs/protocol.md)
# --------------------------------------------------------------------------


def test_callback_response_field_set_matches_docs_protocol_narrative(schema_by_id):
    schema = schema_by_id["https://schemas.contenttree.dev/plugin-spec/v2/callback-success-response.schema.json"]
    assert set(schema["properties"].keys()) == {"accepted", "duplicate", "applied", "late", "stale"}
    for field in ["accepted", "duplicate", "applied", "late", "stale"]:
        assert field in PROTOCOL_MD_TEXT, f"docs/protocol.md must narrate the {field!r} callback response field"


def test_accepted_is_the_only_required_callback_response_field(schema_by_id):
    schema = schema_by_id["https://schemas.contenttree.dev/plugin-spec/v2/callback-success-response.schema.json"]
    assert schema["required"] == ["accepted"]


def test_cookie_requirements_are_documented():
    for attr in ["HttpOnly", "Secure", "SameSite=Lax"]:
        assert attr in SECURITY_MD_TEXT, f"docs/security.md must document the {attr!r} cookie attribute requirement"


def test_csrf_header_name_is_documented_and_matches_schema_description(schema_by_id):
    assert "X-ContentTree-CSRF-Token" in SECURITY_MD_TEXT
    schema = schema_by_id["https://schemas.contenttree.dev/plugin-spec/v2/interaction-assertion-exchange-response.schema.json"]
    assert "csrf_token" in schema["properties"]


def test_browser_handoff_uses_fixed_fragment_parameter_and_never_query_transport():
    assert "#contenttree_assertion=<percent-encoded JWT>" in PROTOCOL_MD_TEXT
    assert "#contenttree_assertion=<percent-encoded JWT>" in SECURITY_MD_TEXT
    assert "MUST NOT place the JWT in the path or query" in PROTOCOL_MD_TEXT
    assert "MUST NOT be placed in the path or query" in SECURITY_MD_TEXT
    assert "preserving any" in PROTOCOL_MD_TEXT
    assert "existing query string" in PROTOCOL_MD_TEXT


def test_browser_handoff_location_has_machine_readable_fragment_contract(schema_by_id):
    schema = schema_by_id[
        "https://schemas.contenttree.dev/plugin-spec/v2/browser-assertion-handoff-location.schema.json"
    ]
    assert schema["$ref"].endswith(
        "#/$defs/browserAssertionHandoffLocation"
    )
    fields = schema_by_id[
        "https://schemas.contenttree.dev/plugin-spec/common/fields.schema.json"
    ]
    handoff = fields["$defs"]["browserAssertionHandoffLocation"]
    assert handoff["format"] == "uri"
    assert handoff["pattern"].startswith("^https://")
    assert "#contenttree_assertion=" in handoff["pattern"]
    assert handoff["pattern"].endswith("$")


def test_browser_handoff_fragment_precondition_and_malformed_handling_are_documented():
    assert "fragment-free before handoff" in PROTOCOL_MD_TEXT
    assert "fragment-free before host handoff" in SECURITY_MD_TEXT
    assert "Duplicate or empty `contenttree_assertion` parameters are malformed" in PROTOCOL_MD_TEXT
    assert "duplicate `contenttree_assertion`" in SECURITY_MD_TEXT
    assert "MUST NOT exchange on malformed input" in SECURITY_MD_TEXT


def test_browser_bootstrap_clears_fragment_and_avoids_persistence():
    assert "history.replaceState" in PROTOCOL_MD_TEXT
    assert "history.replaceState" in SECURITY_MD_TEXT
    assert "same-origin" in PROTOCOL_MD_TEXT
    assert "same-origin `POST /auth/contenttree/exchange`" in SECURITY_MD_TEXT
    assert "MUST NOT log or persist the assertion token" in PROTOCOL_MD_TEXT
    assert "MUST NOT log or persist assertion-token material" in SECURITY_MD_TEXT


def test_host_handoff_response_hardening_headers_are_documented():
    assert "Cache-Control: no-store" in SECURITY_MD_TEXT
    assert "Referrer-Policy: no-referrer" in SECURITY_MD_TEXT
