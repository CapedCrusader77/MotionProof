"""Contract checks over the whole API and CLI surface.

* every CLI command and sub-command answers ``--help`` with exit code 0;
* every REST route, called with missing or invalid input, answers with a client error (4xx) or
  success, never a server error (5xx) - so bad input is always reported, never a crash;
* every GET route without path parameters succeeds on an empty workspace.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import typer
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from motionproof.api.app import create_app
from motionproof.cli.main import app as cli_app
from tests.conftest import signed_in


def _commands(cmd: Any, path: tuple[str, ...] = ()) -> list[tuple[str, ...]]:
    out = [path]
    if hasattr(cmd, "commands"):  # typer vendors click; duck-type the group
        for name, sub in cmd.commands.items():
            out += _commands(sub, (*path, name))
    return out


ROOT_CMD = typer.main.get_command(cli_app)
COMMANDS = _commands(ROOT_CMD)


def test_cli_surface_is_large() -> None:
    assert len(COMMANDS) > 40


@pytest.mark.parametrize("path", COMMANDS, ids=lambda p: " ".join(p) or "<root>")
def test_cli_help(path: tuple[str, ...]) -> None:
    res = CliRunner().invoke(cli_app, [*path, "--help"])
    assert res.exit_code == 0, res.output
    assert "Usage" in res.output


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> TestClient:
    return signed_in(TestClient(create_app(tmp_path_factory.mktemp("contract_ws")),
                      raise_server_exceptions=False))


def _routes(client: TestClient) -> list[tuple[str, str, dict[str, Any]]]:
    spec = client.app.openapi()  # type: ignore[attr-defined]
    return [(m.upper(), p, op) for p, ops in spec["paths"].items() for m, op in ops.items()
            if m in ("get", "post", "put", "patch", "delete")]


def test_openapi_lists_routes(client: TestClient) -> None:
    assert len(_routes(client)) > 50


def test_no_route_crashes_on_bad_input(client: TestClient) -> None:
    failures = []
    for method, path, _ in _routes(client):
        url = re.sub(r"\{[^}]+\}", "does-not-exist", path)
        if method == "DELETE":
            continue  # nothing exists to delete; DELETE on unknown ids is covered below
        kwargs: dict[str, Any] = {}
        if method in ("POST", "PUT", "PATCH"):
            kwargs["json"] = {"not_a_field": 1}
        r = client.request(method, url, **kwargs)
        if r.status_code >= 500:
            failures.append(f"{method} {url} -> {r.status_code} {r.text[:200]}")
    assert not failures, "\n".join(failures)


def test_delete_unknown_is_client_error(client: TestClient) -> None:
    failures = []
    for method, path, _ in _routes(client):
        if method != "DELETE" or "{" not in path:
            continue
        r = client.delete(re.sub(r"\{[^}]+\}", "does-not-exist", path))
        if r.status_code >= 500 or r.status_code < 400:
            failures.append(f"DELETE {path} -> {r.status_code}")
    assert not failures, "\n".join(failures)


def test_collection_gets_succeed_on_empty_workspace(client: TestClient) -> None:
    signed_in(client)  # the bad-input sweep above also called /auth/logout
    failures = []
    for method, path, op in _routes(client):
        required = [p for p in op.get("parameters", []) if p.get("required")]
        if method != "GET" or "{" in path or required:
            continue
        r = client.get(path)
        if r.status_code != 200:
            failures.append(f"GET {path} -> {r.status_code} {r.text[:200]}")
    assert not failures, "\n".join(failures)


def test_cli_help_lists_every_group(tmp_path: Path) -> None:
    res = CliRunner().invoke(cli_app, ["--help"])
    for name in ("hardware", "measurements", "benchmark", "challenge"):
        assert name in res.output
