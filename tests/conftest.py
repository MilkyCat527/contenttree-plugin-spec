"""Shared pytest fixtures for the contenttree-plugin-spec conformance suite.

This module builds a *local-only* JSON Schema registry: every schema
document under ``schemas/`` is loaded from disk once per test session and
registered under its own ``$id``. ``$ref`` resolution (including the
``../common/fields.schema.json#/$defs/...`` style relative refs used
throughout this repository) is then handled entirely by the ``referencing``
library resolving against that in-memory registry — no network access is
ever attempted. The registry's ``retrieve`` callback is a hard failure
(``_forbid_network_retrieve``) rather than a real HTTP fetch, so a typo'd or
dangling ``$ref`` fails the test suite loudly instead of silently reaching
the network.

Nothing in this package is a host/plugin SDK: these are test fixtures and
pytest assertions only, exercising the published schemas/OpenAPI/docs from
the S1 stack PR.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMAS_DIR = REPO_ROOT / "schemas"
OPENAPI_DIR = REPO_ROOT / "openapi"
DOCS_DIR = REPO_ROOT / "docs"
FIXTURES_DIR = REPO_ROOT / "fixtures"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def all_schema_paths() -> list[Path]:
    return sorted(SCHEMAS_DIR.rglob("*.schema.json"))


def all_openapi_paths() -> list[Path]:
    return sorted(OPENAPI_DIR.glob("*.yaml"))


def _forbid_network_retrieve(uri: str):
    raise RuntimeError(
        "Conformance suite attempted to resolve a $ref outside the local "
        f"schema registry ({uri!r}). All $refs in this repository MUST "
        "resolve to a file under schemas/ with no network fallback; this "
        "is either a dangling $ref in the artifact under test or a typo "
        "in a fixture's expectations."
    )


@pytest.fixture(scope="session")
def schema_documents() -> dict[str, dict]:
    """Map of repo-relative POSIX path -> parsed schema document."""
    out: dict[str, dict] = {}
    for path in all_schema_paths():
        rel = path.relative_to(REPO_ROOT).as_posix()
        out[rel] = load_json(path)
    return out


@pytest.fixture(scope="session")
def schema_registry(schema_documents: dict[str, dict]) -> Registry:
    resources = []
    for doc in schema_documents.values():
        resource = Resource.from_contents(doc, default_specification=DRAFT202012)
        resources.append((doc["$id"], resource))
    return Registry(retrieve=_forbid_network_retrieve).with_resources(resources)


@pytest.fixture(scope="session")
def schema_by_id(schema_documents: dict[str, dict]) -> dict[str, dict]:
    return {doc["$id"]: doc for doc in schema_documents.values()}


@pytest.fixture(scope="session")
def validator_factory(schema_registry: Registry):
    """Returns a callable(schema_dict) -> Draft202012Validator bound to the
    local registry and a FormatChecker (format assertions enabled)."""

    def _make(schema: dict) -> Draft202012Validator:
        return Draft202012Validator(
            schema, registry=schema_registry, format_checker=FormatChecker()
        )

    return _make


@pytest.fixture(scope="session")
def check_schema_is_valid_meta_schema():
    """Returns a callable that runs Draft202012Validator.check_schema."""

    def _check(schema: dict) -> None:
        Draft202012Validator.check_schema(schema)

    return _check


@pytest.fixture(scope="session")
def openapi_documents() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in all_openapi_paths():
        rel = path.relative_to(REPO_ROOT).as_posix()
        out[rel] = load_yaml(path)
    return out


@pytest.fixture(scope="session")
def fixtures_index() -> list[dict]:
    index_path = FIXTURES_DIR / "index.json"
    return load_json(index_path)


@pytest.fixture(autouse=True, scope="session")
def _forbid_all_network_sockets():
    """Session-wide guard: this conformance suite MUST NOT touch the
    network (schemas/OpenAPI resolution is local-only; HMAC vectors are
    recomputed in-process; no product implementation repo is ever
    fetched/imported). Any attempt to open an outbound socket during the
    test session is a hard failure, not merely "unexpected but passing"."""
    import socket

    real_socket = socket.socket

    class _NetworkAccessForbidden(RuntimeError):
        pass

    def _blocked_socket(*args, **kwargs):
        raise _NetworkAccessForbidden(
            "The conformance suite attempted to open a network socket. "
            "All schema/OpenAPI resolution and HMAC computation in this "
            "suite is local-only by design; this indicates a test or "
            "fixture regression, not a legitimate network need."
        )

    socket.socket = _blocked_socket
    try:
        yield
    finally:
        socket.socket = real_socket


__all__ = [
    "REPO_ROOT",
    "SCHEMAS_DIR",
    "OPENAPI_DIR",
    "DOCS_DIR",
    "FIXTURES_DIR",
    "load_json",
    "load_yaml",
    "all_schema_paths",
    "all_openapi_paths",
    "SchemaError",
]
