"""The optional AI assistant: providers, key handling and the per-account daily limit.

No test talks to a real provider: ``httpx.post`` is replaced by a recording fake.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from motionproof.ai import assistant
from motionproof.api.app import create_app
from tests.conftest import signed_in

API = "/api/v1"
KEY = "sk-test-SECRET-1234567890"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("MOTIONPROOF_AI", "MOTIONPROOF_AI_PROVIDER", "MOTIONPROOF_AI_KEY",
                 "MOTIONPROOF_AI_MODEL", "MOTIONPROOF_AI_BASE_URL", "MOTIONPROOF_AI_DAILY_LIMIT"):
        monkeypatch.delenv(name, raising=False)
    # nothing listens on this port, so the local provider reports "not reachable" quickly
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")


class FakeResponse:
    def __init__(self, data: dict[str, Any], code: int = 200):
        self._data, self.status_code = data, code

    def json(self) -> dict[str, Any]:
        return self._data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://x")
            raise httpx.HTTPStatusError(f"boom {KEY}", request=request,
                                        response=httpx.Response(self.status_code, request=request,
                                                                text=f"bad key {KEY}"))


def record(monkeypatch: pytest.MonkeyPatch, reply: FakeResponse) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def fake_post(url: str, **kw: Any) -> FakeResponse:
        calls.append({"url": url, **kw})
        return reply

    monkeypatch.setattr(assistant.httpx, "post", fake_post)
    return calls


REPORT_KEYS = ("experiment", "model", "synthetic_notice", "sampling", "task", "summary",
               "assumptions", "limitations")


def tiny_report() -> dict[str, Any]:
    return {"experiment": "e", "model": "m", "synthetic_notice": "x", "sampling": {}, "task": {},
            "summary": {"scenarios": {}, "all_constraints": {}, "constraints": [],
                        "failure_categories": [], "metrics": {}},
            "assumptions": [], "limitations": []}


# ------------------------------------------------------------------ configuration


def test_default_is_local_and_free_of_keys() -> None:
    st = assistant.status()
    assert st["provider"] == "ollama" and st["cloud"] is False
    assert st["available"] is False and "Ollama" in st["reason"]


def test_cloud_provider_needs_a_key_and_a_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIONPROOF_AI_PROVIDER", "anthropic")
    assert "MOTIONPROOF_AI_KEY" in assistant.status()["reason"]
    monkeypatch.setenv("MOTIONPROOF_AI_KEY", KEY)
    st = assistant.status()
    assert st["available"] and st["cloud"] and st["host"] == "api.anthropic.com"
    assert st["model"] == "claude-sonnet-5-5" and st["daily_limit"] == 30
    monkeypatch.setenv("MOTIONPROOF_AI_PROVIDER", "openai")
    assert "MOTIONPROOF_AI_MODEL" in assistant.status()["reason"]   # no default for openai
    monkeypatch.setenv("MOTIONPROOF_AI_MODEL", "some-model")
    assert assistant.status()["host"] == "api.openai.com"


def test_the_key_never_appears_in_the_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIONPROOF_AI_PROVIDER", "anthropic")
    monkeypatch.setenv("MOTIONPROOF_AI_KEY", KEY)
    assert KEY not in json.dumps(assistant.status())


def test_a_key_is_never_sent_over_plain_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIONPROOF_AI_PROVIDER", "openai")
    monkeypatch.setenv("MOTIONPROOF_AI_KEY", KEY)
    monkeypatch.setenv("MOTIONPROOF_AI_MODEL", "m")
    monkeypatch.setenv("MOTIONPROOF_AI_BASE_URL", "http://ai.example.com/v1")
    st = assistant.status()
    assert not st["available"] and "https" in st["reason"]
    monkeypatch.setenv("MOTIONPROOF_AI_BASE_URL", "http://localhost:1234/v1")  # a local server
    assert assistant.status()["available"]


def test_unknown_provider_and_the_off_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIONPROOF_AI_PROVIDER", "gemini")
    assert "unknown" in assistant.status()["reason"]
    monkeypatch.setenv("MOTIONPROOF_AI_PROVIDER", "anthropic")
    monkeypatch.setenv("MOTIONPROOF_AI_KEY", KEY)
    monkeypatch.setenv("MOTIONPROOF_AI", "off")
    assert not assistant.status()["available"]


# ------------------------------------------------------------------ requests


def test_anthropic_request_and_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIONPROOF_AI_PROVIDER", "anthropic")
    monkeypatch.setenv("MOTIONPROOF_AI_KEY", KEY)
    calls = record(monkeypatch, FakeResponse({"content": [{"type": "text", "text": "Because."}]}))
    out = assistant.explain(tiny_report(), "why?")
    assert out["available"] and out["answer"] == "Because." and out["cloud"]
    call = calls[0]
    assert call["url"] == "https://api.anthropic.com/v1/messages"
    assert call["headers"]["x-api-key"] == KEY and call["json"]["model"] == "claude-sonnet-5-5"
    assert "api.anthropic.com" in out["disclaimer"]            # says where the data went
    assert KEY not in json.dumps(out)


def test_openai_compatible_request_and_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIONPROOF_AI_PROVIDER", "openai")
    monkeypatch.setenv("MOTIONPROOF_AI_KEY", KEY)
    monkeypatch.setenv("MOTIONPROOF_AI_MODEL", "m1")
    monkeypatch.setenv("MOTIONPROOF_AI_BASE_URL", "https://llm.example.com/v1/")
    calls = record(monkeypatch, FakeResponse({"choices": [{"message": {"content": " Ok. "}}]}))
    out = assistant.explain(tiny_report(), "why?")
    assert out["answer"] == "Ok." and out["sent_to"] == "llm.example.com"
    assert calls[0]["url"] == "https://llm.example.com/v1/chat/completions"
    assert calls[0]["headers"]["Authorization"] == f"Bearer {KEY}"


@pytest.mark.parametrize("code, words", [(401, "refused the key"), (403, "refused the key"),
                                         (429, "rate limiting"), (404, "does not know the model"),
                                         (500, "HTTP 500")])
def test_provider_errors_are_explained_without_leaking_the_key(
        monkeypatch: pytest.MonkeyPatch, code: int, words: str) -> None:
    monkeypatch.setenv("MOTIONPROOF_AI_PROVIDER", "anthropic")
    monkeypatch.setenv("MOTIONPROOF_AI_KEY", KEY)
    record(monkeypatch, FakeResponse({}, code))
    out = assistant.explain(tiny_report(), "why?")
    assert not out["available"] and words in out["reason"]
    assert KEY not in json.dumps(out)


def test_network_failure_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIONPROOF_AI_PROVIDER", "anthropic")
    monkeypatch.setenv("MOTIONPROOF_AI_KEY", KEY)

    def down(url: str, **kw: Any) -> None:
        raise httpx.ConnectError(f"cannot connect, key {KEY}")

    monkeypatch.setattr(assistant.httpx, "post", down)
    out = assistant.explain(tiny_report(), "why?")
    assert out["reason"] == "could not reach anthropic" and KEY not in json.dumps(out)


# ------------------------------------------------------------------ the API route


@pytest.fixture(scope="module")
def api(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    client = signed_in(TestClient(create_app(tmp_path_factory.mktemp("ai_ws"))))
    pid = client.post(f"{API}/projects", json={"name": "ai"}).json()["id"]
    mid = client.post(f"{API}/models/reference", json={"project_id": pid}).json()["id"]
    cfg = {"name": "tiny", "task": {"type": "reversal", "target": {"shoulder": 1.5708},
                                     "joint": "shoulder"},
           "sampling": {"method": "monte_carlo", "samples": 3, "seed": 1},
           "constraints": [{"name": "lost", "metric": "lost_motion", "op": "<=", "limit": 0.0065}]}
    eid = client.post(f"{API}/experiments", json={"model_id": mid, "config": cfg}).json()["id"]
    job = client.post(f"{API}/experiments/{eid}/run").json()
    end = time.time() + 300
    while time.time() < end:
        j = client.get(f"{API}/jobs/{job['id']}").json()
        if j["status"] in ("completed", "failed", "cancelled"):
            assert j["status"] == "completed", j
            break
        time.sleep(0.3)
    return {"client": client, "experiment": eid}


def test_route_with_no_ai_configured_says_so(api: dict[str, Any]) -> None:
    r = api["client"].post(f"{API}/ai/explain", json={"experiment_id": api["experiment"],
                                                       "question": "why?"})
    assert r.status_code == 200 and r.json()["available"] is False
    assert api["client"].get(f"{API}/system").json()["ai"]["cloud"] is False


def test_route_daily_limit_counts_each_cloud_question(
        api: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIONPROOF_AI_PROVIDER", "anthropic")
    monkeypatch.setenv("MOTIONPROOF_AI_KEY", KEY)
    monkeypatch.setenv("MOTIONPROOF_AI_DAILY_LIMIT", "2")
    calls = record(monkeypatch, FakeResponse({"content": [{"type": "text", "text": "Answer."}]}))
    client, eid = api["client"], api["experiment"]
    ask = lambda: client.post(f"{API}/ai/explain",  # noqa: E731
                              json={"experiment_id": eid, "question": "why?"})
    assert client.get(f"{API}/system").json()["ai"]["used_today"] == 0
    first = ask()
    assert first.status_code == 200 and first.json()["answer"] == "Answer."
    assert ask().status_code == 200
    blocked = ask()
    assert blocked.status_code == 429 and "daily limit of 2" in blocked.json()["detail"]
    assert len(calls) == 2                       # the refused question was never sent
    system = client.get(f"{API}/system").json()["ai"]
    assert system["used_today"] == 2 and system["daily_limit"] == 2
    assert KEY not in client.get(f"{API}/system").text and KEY not in first.text


def test_the_local_provider_is_not_limited(
        api: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTIONPROOF_AI_DAILY_LIMIT", "1")
    client, eid = api["client"], api["experiment"]
    for _ in range(3):
        r = client.post(f"{API}/ai/explain", json={"experiment_id": eid, "question": "why?"})
        assert r.status_code == 200
