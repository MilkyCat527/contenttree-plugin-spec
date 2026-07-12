"""Structural validity of every published JSON Schema document.

Covers:
- All JSON/YAML in the repository parses cleanly (this module: schemas;
  test_openapi_structure.py: the two OpenAPI documents).
- Every schema is a valid Draft 2020-12 meta-schema
  (``Draft202012Validator.check_schema``).
- Every ``$ref`` in every schema resolves *locally*, with no network
  fallback (the registry's ``retrieve`` callback raises instead of
  fetching), per the schema_registry fixture in conftest.py.
- ``FormatChecker`` is wired in and actually enforces "date-time" / "uri"
  formats (not merely present-but-inert), verified with inline positive and
  negative probes independent of the fixtures/ directory.
"""
from __future__ import annotations

from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry

from conftest import all_schema_paths, load_json


def _iter_refs(node: Any, path: str = "$"):
    """Yield (json_pointer_path, ref_string) for every $ref found anywhere
    in a schema document, including inside $defs, properties, if/then/else,
    allOf, etc. This is a generic structural walk, not schema-keyword-aware
    beyond recognizing dict/list containers, which is sufficient here since
    every $ref in this repository is a plain string value."""
    if isinstance(node, dict):
        for key, value in node.items():
            child_path = f"{path}.{key}"
            if key == "$ref" and isinstance(value, str):
                yield child_path, value
            else:
                yield from _iter_refs(value, child_path)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            yield from _iter_refs(item, f"{path}[{i}]")


SCHEMA_PATHS = all_schema_paths()


@pytest.mark.parametrize("schema_path", SCHEMA_PATHS, ids=[p.name for p in SCHEMA_PATHS])
def test_schema_parses_as_json(schema_path):
    load_json(schema_path)  # raises json.JSONDecodeError on failure


@pytest.mark.parametrize("schema_path", SCHEMA_PATHS, ids=[p.name for p in SCHEMA_PATHS])
def test_schema_is_valid_draft2020_12(schema_path, check_schema_is_valid_meta_schema):
    doc = load_json(schema_path)
    assert doc.get("$schema") == "https://json-schema.org/draft/2020-12/schema", (
        f"{schema_path} must declare the Draft 2020-12 $schema explicitly"
    )
    check_schema_is_valid_meta_schema(doc)


@pytest.mark.parametrize("schema_path", SCHEMA_PATHS, ids=[p.name for p in SCHEMA_PATHS])
def test_schema_declares_stable_id(schema_path):
    doc = load_json(schema_path)
    assert doc.get("$id", "").startswith("https://schemas.contenttree.dev/plugin-spec/"), (
        f"{schema_path} must declare a stable $id under the plugin-spec namespace"
    )


@pytest.mark.parametrize("schema_path", SCHEMA_PATHS, ids=[p.name for p in SCHEMA_PATHS])
def test_every_ref_resolves_locally_no_network(schema_path, schema_registry: Registry):
    doc = load_json(schema_path)
    base_uri = doc["$id"]
    resolver = schema_registry.resolver(base_uri=base_uri)
    refs = list(_iter_refs(doc))
    # fields.schema.json is the shared $defs source and legitimately has no
    # outgoing $refs of its own; callback-success-response.schema.json's
    # properties are all inline booleans with no shared $defs to reference.
    # Every other schema in this repository does have at least one $ref.
    schemas_without_refs = {"fields.schema.json", "callback-success-response.schema.json"}
    if schema_path.name not in schemas_without_refs:
        assert refs, f"{schema_path} was expected to contain at least one $ref"
    for pointer_path, ref in refs:
        # .lookup() raises referencing.exceptions.Unresolvable (or invokes
        # the forbidden-network retrieve hook, which itself raises) if the
        # $ref cannot be resolved against the local registry alone.
        resolved = resolver.lookup(ref)
        assert resolved.contents is not None, (
            f"{schema_path}:{pointer_path} $ref {ref!r} resolved to empty contents"
        )


def test_additionalproperties_false_object_schemas_are_closed(schema_documents):
    """Every top-level object schema with additionalProperties: false must
    also declare `type: object` and a `properties` map (sanity check that
    the closed-world assertion is actually attached to an object schema,
    not accidentally vacuous)."""
    for rel_path, doc in schema_documents.items():
        if doc.get("additionalProperties") is False:
            assert doc.get("type") == "object", f"{rel_path}: additionalProperties:false without type:object"
            assert "properties" in doc, f"{rel_path}: additionalProperties:false without properties"


# --- FormatChecker sanity (independent of fixtures/) ------------------------

FORMAT_PROBES = [
    ("date-time", "2025-06-15T14:13:20Z", True),
    ("date-time", "2025-06-15 14:13:20", False),
    ("date-time", "not-a-timestamp", False),
    ("uri", "https://example.com/path", True),
    ("uri", "not a uri at all", False),
]


@pytest.mark.parametrize("fmt,value,expected", FORMAT_PROBES, ids=[f"{f}:{v!r}" for f, v, _ in FORMAT_PROBES])
def test_format_checker_enforces_formats(fmt, value, expected):
    checker = FormatChecker()
    assert checker.conforms(value, fmt) is expected


def test_occurred_at_schema_rejects_malformed_date_time(validator_factory, schema_by_id):
    schema = schema_by_id["https://schemas.contenttree.dev/plugin-spec/v2/completion-event.schema.json"]
    validator = validator_factory(schema)
    bad = {
        "event_id": "evt-format-probe-0001",
        "sequence": 1,
        "state": "succeeded",
        "occurred_at": "not-a-real-timestamp",
        "result_mode": "none",
    }
    errors = list(validator.iter_errors(bad))
    assert any(e.validator == "format" for e in errors), (
        "expected a 'format' validation error for a malformed occurred_at value"
    )
