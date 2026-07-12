"""Index-driven fixture conformance tests.

Every fixture instance under ``fixtures/`` is validated against exactly one
target schema. Per the task requirements, the mapping from fixture instance
-> target schema -> expected valid/invalid outcome is kept entirely OUTSIDE
the instance being validated (``fixtures/index.json``), never via an
in-band marker such as a ``__schema__`` property (which strict
``additionalProperties: false`` schemas would reject anyway).
"""
from __future__ import annotations

from pathlib import Path

import pytest
from jsonschema import FormatChecker

from conftest import FIXTURES_DIR, REPO_ROOT, load_json


def _load_index() -> list[dict]:
    return load_json(FIXTURES_DIR / "index.json")


INDEX = _load_index()


def _case_id(entry: dict) -> str:
    return entry["fixture"].removeprefix("fixtures/")


@pytest.mark.parametrize("entry", INDEX, ids=[_case_id(e) for e in INDEX])
def test_fixture_matches_expected_validity(entry, validator_factory, schema_by_id, schema_documents):
    fixture_path = REPO_ROOT / entry["fixture"]
    assert fixture_path.is_file(), f"fixture listed in index.json does not exist: {fixture_path}"

    instance = load_json(fixture_path)
    schema_doc = schema_documents[entry["schema"]]
    validator = validator_factory(schema_doc)

    errors = list(validator.iter_errors(instance))
    if entry["valid"]:
        assert errors == [], (
            f"{entry['fixture']} was expected to be VALID against {entry['schema']} "
            f"but raised: {[e.message for e in errors]}"
        )
    else:
        assert errors != [], (
            f"{entry['fixture']} was expected to be INVALID against {entry['schema']} "
            "but validated cleanly — fixture or schema drift."
        )


def test_index_has_no_duplicate_fixture_entries():
    seen = set()
    for entry in INDEX:
        assert entry["fixture"] not in seen, f"duplicate index entry for {entry['fixture']}"
        seen.add(entry["fixture"])


def test_index_covers_every_fixture_file_on_disk():
    indexed = {entry["fixture"] for entry in INDEX}
    on_disk = {
        p.relative_to(REPO_ROOT).as_posix()
        for p in FIXTURES_DIR.rglob("*.json")
        if p.name != "index.json" and "security" not in p.parts
    }
    missing_from_index = on_disk - indexed
    missing_on_disk = indexed - on_disk
    assert not missing_from_index, f"fixtures present on disk but not listed in index.json: {missing_from_index}"
    assert not missing_on_disk, f"index.json references fixtures that do not exist on disk: {missing_on_disk}"


def test_no_fixture_instance_carries_an_in_band_schema_marker():
    """Guards the 'metadata kept OUTSIDE the instance' requirement itself:
    no fixture may smuggle its own target-schema pointer via a __schema__
    (or similar) property, which strict additionalProperties: false schemas
    would reject anyway and which would defeat the point of the external
    index."""
    banned_keys = {"__schema__", "$schema_under_test", "__target_schema__"}
    for entry in INDEX:
        instance = load_json(REPO_ROOT / entry["fixture"])
        if isinstance(instance, dict):
            present = banned_keys & instance.keys()
            assert not present, f"{entry['fixture']} carries an in-band schema marker: {present}"


@pytest.mark.parametrize("entry", [e for e in INDEX if e["valid"]], ids=[_case_id(e) for e in INDEX if e["valid"]])
def test_valid_fixtures_pass_with_format_checker_enabled(entry, schema_documents, schema_registry):
    """Redundant-by-design double-check that FormatChecker is actually
    exercised (not merely constructed) for every valid fixture, since a
    validator built without format_checker=... would silently skip format
    assertions."""
    from jsonschema import Draft202012Validator

    schema_doc = schema_documents[entry["schema"]]
    validator = Draft202012Validator(schema_doc, registry=schema_registry, format_checker=FormatChecker())
    validator.validate(load_json(REPO_ROOT / entry["fixture"]))
