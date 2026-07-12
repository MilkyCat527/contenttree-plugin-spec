"""Structural validation of the OpenAPI 3.1 documents.

This intentionally does not pull in a full OpenAPI validator dependency;
instead it asserts the specific, load-bearing shapes called out by the
conformance requirements: exact paths/methods, security scheme wiring, the
X-ContentTree-Timestamp/Signature headers, request/response schema $refs,
and the Set-Cookie response header on the assertion exchange endpoint. It
also verifies every $ref in both documents resolves to a real file + JSON
pointer on disk (openapi/*.yaml reference ../schemas/*.schema.json).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from conftest import OPENAPI_DIR, REPO_ROOT, all_openapi_paths, load_json, load_yaml

OPENAPI_PATHS = all_openapi_paths()


@pytest.mark.parametrize("path", OPENAPI_PATHS, ids=[p.name for p in OPENAPI_PATHS])
def test_openapi_parses_as_yaml(path):
    doc = load_yaml(path)
    assert isinstance(doc, dict)


@pytest.mark.parametrize("path", OPENAPI_PATHS, ids=[p.name for p in OPENAPI_PATHS])
def test_openapi_declares_version_3_1(path):
    doc = load_yaml(path)
    assert doc.get("openapi", "").startswith("3.1"), f"{path} must declare openapi: 3.1.x"
    assert "info" in doc and "title" in doc["info"] and "version" in doc["info"]
    assert doc["info"].get("license", {}).get("identifier") == "Apache-2.0"
    assert "paths" in doc and doc["paths"], f"{path} must declare at least one path"


def _iter_doc_refs(node: Any, path: str = "$"):
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}"
            if key == "$ref" and isinstance(value, str):
                yield child, value
            else:
                yield from _iter_doc_refs(value, child)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            yield from _iter_doc_refs(item, f"{path}[{i}]")


@pytest.mark.parametrize("path", OPENAPI_PATHS, ids=[p.name for p in OPENAPI_PATHS])
def test_openapi_refs_resolve_to_real_files_and_pointers_no_network(path):
    doc = load_yaml(path)
    refs = list(_iter_doc_refs(doc))
    assert refs, f"{path} was expected to $ref at least one schema document"
    for pointer_path, ref in refs:
        assert not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", ref), (
            f"{path}:{pointer_path} $ref {ref!r} looks like a network URL; "
            "all OpenAPI $refs in this repository MUST be local relative file paths"
        )
        file_part, _, json_pointer = ref.partition("#")
        target = (path.parent / file_part).resolve()
        assert target.is_file(), f"{path}:{pointer_path} $ref {ref!r} does not resolve to a file ({target})"
        target_doc = load_json(target)
        if json_pointer:
            node = target_doc
            for segment in json_pointer.strip("/").split("/"):
                segment = segment.replace("~1", "/").replace("~0", "~")
                assert isinstance(node, dict) and segment in node, (
                    f"{path}:{pointer_path} $ref {ref!r} JSON pointer segment {segment!r} not found"
                )
                node = node[segment]


# --------------------------------------------------------------------------
# plugin-host-api.yaml: exact endpoint/method/header/security shape
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def host_api_doc():
    return load_yaml(OPENAPI_DIR / "plugin-host-api.yaml")


def test_host_api_has_no_contract_version_1_surface(host_api_doc):
    # v1 is synchronous-only and has no host-exposed API at all.
    assert list(host_api_doc["paths"].keys()) == [
        "/api/plugin-host/v1/invocations/{invocation_id}/events"
    ]


def test_host_api_submit_completion_event_shape(host_api_doc):
    op = host_api_doc["paths"]["/api/plugin-host/v1/invocations/{invocation_id}/events"]["post"]
    assert op["operationId"] == "submitCompletionEvent"
    assert op["security"] == [{"pluginToHostHmac": []}]

    param_names = {p["name"]: p for p in op["parameters"]}
    assert "invocation_id" in param_names
    assert param_names["invocation_id"]["in"] == "path"
    assert param_names["invocation_id"]["required"] is True
    assert param_names["invocation_id"]["schema"]["$ref"] == "../schemas/common/fields.schema.json#/$defs/invocationId"

    assert "X-ContentTree-Timestamp" in param_names
    ts_param = param_names["X-ContentTree-Timestamp"]
    assert ts_param["in"] == "header"
    assert ts_param["required"] is True
    assert ts_param["schema"]["pattern"] == "^[0-9]+$"

    body_schema = op["requestBody"]["content"]["application/json"]["schema"]
    assert body_schema["$ref"] == "../schemas/v2/completion-event.schema.json"
    assert op["requestBody"]["required"] is True

    responses = op["responses"]
    assert set(responses.keys()) == {"200", "400", "401", "404", "413"}
    assert (
        responses["200"]["content"]["application/json"]["schema"]["$ref"]
        == "../schemas/v2/callback-success-response.schema.json"
    )


def test_host_api_security_scheme_definition(host_api_doc):
    scheme = host_api_doc["components"]["securitySchemes"]["pluginToHostHmac"]
    assert scheme["type"] == "apiKey"
    assert scheme["in"] == "header"
    assert scheme["name"] == "X-ContentTree-Signature"


# --------------------------------------------------------------------------
# plugin-api.yaml: exact endpoint/method/header/security shape
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def plugin_api_doc():
    return load_yaml(OPENAPI_DIR / "plugin-api.yaml")


def test_plugin_api_declares_exactly_four_paths(plugin_api_doc):
    assert set(plugin_api_doc["paths"].keys()) == {
        "/v1/actions/{action_id}/invoke",
        "/v2/actions/{action_id}/invoke",
        "/operations/{operation_id}",
        "/auth/contenttree/exchange",
    }


def test_plugin_api_v1_invoke_shape(plugin_api_doc):
    op = plugin_api_doc["paths"]["/v1/actions/{action_id}/invoke"]["post"]
    assert op["operationId"] == "invokeActionV1"
    assert "security" not in op, "v1 invoke is not documented as requiring the HMAC security schemes"
    body_schema = op["requestBody"]["content"]["application/json"]["schema"]
    assert body_schema["$ref"] == "../schemas/v1/invoke-request.schema.json"
    assert (
        op["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "../schemas/v1/invoke-response.schema.json"
    )
    assert set(op["responses"].keys()) == {"200", "400", "404"}


def test_plugin_api_v2_invoke_shape(plugin_api_doc):
    op = plugin_api_doc["paths"]["/v2/actions/{action_id}/invoke"]["post"]
    assert op["operationId"] == "invokeActionV2"
    body_schema = op["requestBody"]["content"]["application/json"]["schema"]
    assert body_schema["$ref"] == "../schemas/v2/invoke-request.schema.json"
    assert (
        op["responses"]["202"]["content"]["application/json"]["schema"]["$ref"]
        == "../schemas/v2/invoke-accepted-response.schema.json"
    )
    assert set(op["responses"].keys()) == {"202", "400", "404"}


def test_plugin_api_operation_status_shape(plugin_api_doc):
    op = plugin_api_doc["paths"]["/operations/{operation_id}"]["get"]
    assert op["operationId"] == "getOperationStatus"
    assert op["security"] == [{"hostToPluginHmac": []}]

    param_names = {p["name"]: p for p in op["parameters"]}
    assert param_names["operation_id"]["schema"]["$ref"] == "../schemas/common/fields.schema.json#/$defs/operationId"
    assert param_names["X-ContentTree-Timestamp"]["required"] is True
    assert param_names["X-ContentTree-Timestamp"]["schema"]["pattern"] == "^[0-9]+$"

    assert (
        op["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "../schemas/v2/operation-status.schema.json"
    )
    assert set(op["responses"].keys()) == {"200", "400", "401", "404"}


def test_plugin_api_assertion_exchange_shape(plugin_api_doc):
    op = plugin_api_doc["paths"]["/auth/contenttree/exchange"]["post"]
    assert op["operationId"] == "exchangeInteractionAssertion"
    assert "security" not in op or op.get("security") is None, (
        "assertion exchange is authenticated by JWT verification of the request body itself, "
        "not by the X-ContentTree-Signature securitySchemes used elsewhere in this document"
    )
    body_schema = op["requestBody"]["content"]["application/json"]["schema"]
    assert body_schema["$ref"] == "../schemas/v2/interaction-assertion-exchange-request.schema.json"

    ok = op["responses"]["200"]
    assert (
        ok["content"]["application/json"]["schema"]["$ref"]
        == "../schemas/v2/interaction-assertion-exchange-response.schema.json"
    )
    assert "Set-Cookie" in ok["headers"], "200 response MUST document the Set-Cookie session header"
    assert set(op["responses"].keys()) == {"200", "400", "401"}


def test_plugin_api_security_scheme_definition(plugin_api_doc):
    scheme = plugin_api_doc["components"]["securitySchemes"]["hostToPluginHmac"]
    assert scheme["type"] == "apiKey"
    assert scheme["in"] == "header"
    assert scheme["name"] == "X-ContentTree-Signature"


def test_no_contract_version_1_endpoint_carries_hmac_security(plugin_api_doc):
    v1_op = plugin_api_doc["paths"]["/v1/actions/{action_id}/invoke"]["post"]
    assert "security" not in v1_op, "contract_version 1 is synchronous-only and has no HMAC signing scheme"
