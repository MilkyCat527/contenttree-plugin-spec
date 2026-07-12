"""Explicit, self-checking guarantees for two of the task's hard
requirements:

1. No test in this suite requires network access. tests/conftest.py's
   session-scoped `_forbid_all_network_sockets` autouse fixture already
   makes any outbound `socket.socket()` call a hard failure for the whole
   session; this module additionally asserts that guard fixture exists and
   is wired as autouse (so a future refactor can't accidentally drop it
   silently), and independently proves a blocked socket raises.
2. No file in this repository's tests/fixtures references a product
   implementation repository (host or plugin codebases) by path or import.
   This repository's own rule (G3, README.md "Non-goals") is that no
   implementation code is consulted or shared; this test greps this
   repository's own tracked-in-S2 sources for tell-tale signs of such a
   reference (e.g. sibling-repo relative paths, or hardcoded absolute
   paths to a checkout of an implementation repo) and fails if found.
"""
from __future__ import annotations

import re
import socket

import pytest

from conftest import REPO_ROOT

CONFTEST_SOURCE = (REPO_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")

# Words that would suggest this suite reaches into a sibling implementation
# repository rather than staying self-contained. Deliberately conservative
# (a handful of generic terms) to avoid false positives on legitimate prose
# like "host" / "plugin" (used everywhere, correctly, as protocol roles).
SUSPICIOUS_PATH_PATTERNS = [
    r"\.\./\.\./",       # reaching two or more levels above this repo
    r"/ContentTree/",     # sibling product repo checkout paths
    r"contenttree-service",
    r"contenttree-host",
    r"contenttree-plugin-runtime",
]


def test_network_guard_fixture_is_registered_and_autouse():
    assert "_forbid_all_network_sockets" in CONFTEST_SOURCE
    assert re.search(r"@pytest\.fixture\(autouse=True,\s*scope=\"session\"\)\s*\ndef _forbid_all_network_sockets", CONFTEST_SOURCE), (
        "the network-forbidding fixture must be autouse + session-scoped so it "
        "applies to every test without each test needing to request it explicitly"
    )


def test_blocked_socket_actually_raises_when_invoked():
    with pytest.raises(RuntimeError):
        socket.socket()


@pytest.mark.parametrize("pattern", SUSPICIOUS_PATH_PATTERNS)
def test_no_test_or_fixture_source_references_a_product_repo(pattern):
    self_path = REPO_ROOT / "tests" / "test_no_network_no_product_repo.py"
    offenders = []
    for directory in ["tests", "fixtures"]:
        base = REPO_ROOT / directory
        for path in base.rglob("*"):
            if not path.is_file() or path == self_path or "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if re.search(pattern, text):
                offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, f"pattern {pattern!r} found in: {offenders}"


def test_requirements_and_pyproject_declare_no_git_or_path_dependencies():
    """Every dependency in requirements.txt/pyproject.toml must be a plain
    PyPI package pin — never a git+ URL or local path, which could
    otherwise smuggle in implementation-repo code as a 'dependency'."""
    for filename in ["requirements.txt", "pyproject.toml"]:
        text = (REPO_ROOT / filename).read_text(encoding="utf-8")
        assert "git+" not in text
        assert "file://" not in text
        assert "contenttree-service" not in text
