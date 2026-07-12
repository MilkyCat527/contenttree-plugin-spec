"""Deterministic HMAC vector tests (docs/security.md).

Recomputes all 3 published vectors *from primitives* (secret, timestamp,
body/request-target) rather than merely replaying a stored signing string,
and cross-checks the fixture's expected signature against the literal text
of docs/security.md so the two cannot silently drift apart: if a future
edit changes a vector in docs/security.md without updating
fixtures/security/hmac-vectors.json (or vice versa), this test fails.
"""
from __future__ import annotations

import hashlib
import hmac
import re

import pytest

from conftest import DOCS_DIR, FIXTURES_DIR, REPO_ROOT, load_json

VECTORS = load_json(FIXTURES_DIR / "security" / "hmac-vectors.json")
SECRET = VECTORS["secret_utf8"].encode("utf-8")
SECURITY_MD_TEXT = (DOCS_DIR / "security.md").read_text(encoding="utf-8")

SIGNATURE_RE = re.compile(r"^sha256=[0-9a-f]{64}$")


def _build_signing_string(vector: dict) -> str:
    if vector["scheme"] == "plugin-to-host":
        return f"plugin-to-host:{vector['timestamp']}.{vector['body']}"
    if vector["scheme"] == "host-to-plugin":
        return f"host-to-plugin:{vector['timestamp']}\n{vector['method']}\n{vector['request_target']}"
    raise ValueError(f"unknown scheme: {vector['scheme']!r}")


def _sign(signing_string: str) -> str:
    digest = hmac.new(SECRET, signing_string.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_exactly_three_vectors_are_published():
    assert len(VECTORS["vectors"]) == 3
    assert {v["scheme"] for v in VECTORS["vectors"]} == {"plugin-to-host", "host-to-plugin"}
    assert sum(1 for v in VECTORS["vectors"] if v["scheme"] == "plugin-to-host") == 1
    assert sum(1 for v in VECTORS["vectors"] if v["scheme"] == "host-to-plugin") == 2


@pytest.mark.parametrize("vector", VECTORS["vectors"], ids=[v["id"] for v in VECTORS["vectors"]])
def test_expected_signature_is_well_formed(vector):
    assert SIGNATURE_RE.match(vector["expected_signature_header"]), (
        f"{vector['id']}: expected_signature_header must be 'sha256=' + 64 lowercase hex chars"
    )


@pytest.mark.parametrize("vector", VECTORS["vectors"], ids=[v["id"] for v in VECTORS["vectors"]])
def test_signing_string_is_built_correctly_from_primitives(vector):
    """Independently reconstructs the signing string from the fixture's raw
    components (timestamp/body or timestamp/method/request-target) and
    confirms it matches the fixture's own stored signing_string, guarding
    against a typo in either field."""
    rebuilt = _build_signing_string(vector)
    assert rebuilt == vector["signing_string"]


@pytest.mark.parametrize("vector", VECTORS["vectors"], ids=[v["id"] for v in VECTORS["vectors"]])
def test_recomputed_hmac_matches_expected_signature(vector):
    """The core recompute-from-scratch assertion: HMAC-SHA256(secret,
    signing_string) must equal the documented expected signature, computed
    here using only the primitive fields, independent of any code path in
    docs/security.md's own reproduction snippet."""
    signing_string = _build_signing_string(vector)
    assert _sign(signing_string) == vector["expected_signature_header"]


@pytest.mark.parametrize("vector", VECTORS["vectors"], ids=[v["id"] for v in VECTORS["vectors"]])
def test_docs_security_md_contains_the_same_expected_signature(vector):
    """Cross-check against the published prose so the fixture and docs
    cannot silently diverge: docs/security.md MUST contain this exact
    'sha256=...' string verbatim."""
    assert vector["expected_signature_header"] in SECURITY_MD_TEXT, (
        f"{vector['id']}: expected_signature_header {vector['expected_signature_header']!r} "
        "not found verbatim in docs/security.md — docs and fixture have drifted"
    )


@pytest.mark.parametrize("vector", VECTORS["vectors"], ids=[v["id"] for v in VECTORS["vectors"]])
def test_docs_security_md_contains_the_same_secret_and_timestamp(vector):
    assert VECTORS["secret_utf8"] in SECURITY_MD_TEXT
    assert vector["timestamp"] in SECURITY_MD_TEXT


def test_docs_security_md_contains_the_callback_vector_body_verbatim():
    callback_vector = next(v for v in VECTORS["vectors"] if v["scheme"] == "plugin-to-host")
    assert callback_vector["body"] in SECURITY_MD_TEXT


def test_docs_security_md_contains_both_status_request_targets_verbatim():
    for vector in VECTORS["vectors"]:
        if vector["scheme"] == "host-to-plugin":
            assert vector["request_target"] in SECURITY_MD_TEXT


def test_callback_vector_body_is_schema_valid(validator_factory, schema_by_id):
    """The frozen callback vector body must itself remain a valid
    v2/completion-event.schema.json instance — the HMAC vectors are meant
    to be reproducible against a real, schema-valid wire payload, not an
    arbitrary opaque string."""
    import json

    callback_vector = next(v for v in VECTORS["vectors"] if v["scheme"] == "plugin-to-host")
    instance = json.loads(callback_vector["body"])
    schema = schema_by_id["https://schemas.contenttree.dev/plugin-spec/v2/completion-event.schema.json"]
    validator = validator_factory(schema)
    validator.validate(instance)


def test_clock_skew_tolerance_is_documented_as_300_seconds():
    assert "300 seconds" in SECURITY_MD_TEXT
    assert "now - 300 <= timestamp <= now + 300" in SECURITY_MD_TEXT


def test_callback_body_limit_is_documented_as_64_kib():
    assert "65536 bytes (64 KiB)" in SECURITY_MD_TEXT
