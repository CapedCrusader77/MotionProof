"""Optional AI assistant. Core functionality never depends on it.

Providers (``MOTIONPROOF_AI_PROVIDER``): ``ollama`` (default, local, no key), ``anthropic`` and
``openai`` (any OpenAI-compatible chat endpoint). The cloud providers need ``MOTIONPROOF_AI_KEY``
in the server's environment; the key is read there only, never stored, never sent to the browser
and never put in a response or an error message.

The assistant only ever sees a compact evidence digest built from stored experiment results.
It is instructed to explain and to cite that evidence; every number shown to the user in the
application comes from the engineering engine, never from the language model.

Environment:
  MOTIONPROOF_AI=off              disable completely
  MOTIONPROOF_AI_PROVIDER         ollama | anthropic | openai
  MOTIONPROOF_AI_KEY              API key for anthropic / openai
  MOTIONPROOF_AI_MODEL            model name (anthropic defaults to claude-sonnet-5-5;
                                  openai needs one)
  MOTIONPROOF_AI_BASE_URL         OpenAI-compatible endpoint, default https://api.openai.com/v1
  MOTIONPROOF_AI_DAILY_LIMIT      cloud questions per account per day (default 30)
  OLLAMA_HOST                     Ollama address, default http://127.0.0.1:11434
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlparse

import httpx

SYSTEM = (
    "You are an assistant inside MotionProof, a mechanical tolerance-analysis tool. Explain "
    "the supplied experiment evidence to a mechanical engineer. Rules: use only numbers that "
    "appear in the evidence and quote them exactly; never invent tolerances, measurements or "
    "results; never claim a design is safe, certified or validated; refer to the evidence item "
    "(constraint name, metric, parameter) behind every statement; when the evidence does not "
    "answer the question, say so and suggest which experiment would."
)
CLOUD = ("anthropic", "openai")
ANTHROPIC_URL = "https://api.anthropic.com"
ANTHROPIC_DEFAULT_MODEL = "claude-sonnet-5-5"
OPENAI_URL = "https://api.openai.com/v1"


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def provider() -> str:
    return _env("MOTIONPROOF_AI_PROVIDER", "ollama").lower()


def enabled() -> bool:
    return _env("MOTIONPROOF_AI", "on").lower() not in ("off", "0", "false")


def daily_limit() -> int:
    try:
        return max(1, int(_env("MOTIONPROOF_AI_DAILY_LIMIT", "30")))
    except ValueError:
        return 30


def _endpoint() -> str:
    if provider() == "anthropic":
        return ANTHROPIC_URL
    return _env("MOTIONPROOF_AI_BASE_URL", OPENAI_URL).rstrip("/")


def _host(url: str) -> str:
    return urlparse(url).hostname or url


def _model() -> str:
    default = ANTHROPIC_DEFAULT_MODEL if provider() == "anthropic" else ""
    return _env("MOTIONPROOF_AI_MODEL") or default


def _cloud_problem() -> str | None:
    """Why the configured cloud provider cannot be used, or None."""
    if not _env("MOTIONPROOF_AI_KEY"):
        return "MOTIONPROOF_AI_KEY is not set on the server"
    if not _model():
        return "MOTIONPROOF_AI_MODEL is not set on the server"
    url = urlparse(_endpoint())
    if url.scheme != "https" and url.hostname not in ("localhost", "127.0.0.1", "::1"):
        return "MOTIONPROOF_AI_BASE_URL must use https, so the key is not sent in clear text"
    return None


def status() -> dict[str, Any]:
    """What the assistant is configured to do. Makes no request to a cloud provider (no cost)
    and never includes the key."""
    prov = provider()
    base: dict[str, Any] = {"provider": prov, "cloud": prov in CLOUD}
    if not enabled():
        return base | {"available": False, "reason": "disabled by MOTIONPROOF_AI=off"}
    if prov in CLOUD:
        problem = _cloud_problem()
        if problem:
            return base | {"available": False, "reason": problem}
        return base | {"available": True, "model": _model(), "host": _host(_endpoint()),
                       "daily_limit": daily_limit()}
    if prov != "ollama":
        return base | {"available": False, "reason": f"unknown MOTIONPROOF_AI_PROVIDER {prov!r} "
                                                     "(use ollama, anthropic or openai)"}
    url = _env("OLLAMA_HOST", "http://127.0.0.1:11434")
    try:
        r = httpx.get(f"{url}/api/tags", timeout=0.6)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return base | {"available": False, "reason": "no local Ollama server reachable"}
    if not models:
        return base | {"available": False,
                       "reason": "Ollama is running but has no models installed"}
    return base | {"available": True, "models": models,
                   "model": _env("MOTIONPROOF_AI_MODEL") or models[0]}


def evidence_digest(report: dict[str, Any]) -> dict[str, Any]:
    """The only data handed to the language model."""
    s = report["summary"]
    sens = report.get("sensitivity")
    return {
        "experiment": report["experiment"], "model": report["model"],
        "synthetic": bool(report["synthetic_notice"]), "sampling": report["sampling"],
        "task": report["task"], "scenarios": s["scenarios"],
        "all_constraints": s["all_constraints"], "constraints": s["constraints"],
        "failure_categories": s["failure_categories"],
        "metrics": {k: {q: round(v[q], 6) for q in ("mean", "p05", "p95", "max")}
                    for k, v in s["metrics"].items()},
        "sensitivity_metric": sens["metric"] if sens else None,
        "rank_correlation_top": [
            {k: r[k] for k in ("parameter", "rho", "interval", "direction")}
            for r in sens["rank_correlation"]["rows"][:8]] if sens else [],
        "assumptions": report["assumptions"], "limitations": report["limitations"],
    }


def _ask_ollama(model: str, prompt: str) -> str:
    url = _env("OLLAMA_HOST", "http://127.0.0.1:11434")
    r = httpx.post(f"{url}/api/generate", timeout=120, json={
        "model": model, "system": SYSTEM, "prompt": prompt, "stream": False,
        "options": {"temperature": 0.1}})
    r.raise_for_status()
    return str(r.json().get("response", "")).strip()


def _ask_anthropic(model: str, prompt: str) -> str:
    r = httpx.post(f"{ANTHROPIC_URL}/v1/messages", timeout=120, headers={
        "x-api-key": _env("MOTIONPROOF_AI_KEY"), "anthropic-version": "2023-06-01"}, json={
        "model": model, "max_tokens": 1024, "system": SYSTEM,
        "messages": [{"role": "user", "content": prompt}]})
    r.raise_for_status()
    return "".join(b.get("text", "") for b in r.json().get("content", [])
                   if b.get("type") == "text").strip()


def _ask_openai(model: str, prompt: str) -> str:
    r = httpx.post(f"{_endpoint()}/chat/completions", timeout=120, headers={
        "Authorization": f"Bearer {_env('MOTIONPROOF_AI_KEY')}"}, json={
        "model": model, "messages": [{"role": "system", "content": SYSTEM},
                                     {"role": "user", "content": prompt}]})
    r.raise_for_status()
    return str(r.json()["choices"][0]["message"]["content"]).strip()


def _failure(prov: str, exc: Exception) -> str:
    """A reason for the user. Never includes the provider's response body or the request, which
    can echo part of the key."""
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (401, 403):
            return f"{prov} refused the key (HTTP {code}); check MOTIONPROOF_AI_KEY"
        if code == 429:
            return f"{prov} is rate limiting this key (HTTP 429); try again later"
        if code == 404:
            return f"{prov} does not know the model {_model()!r} (HTTP 404)"
        return f"{prov} request failed (HTTP {code})"
    if isinstance(exc, httpx.TimeoutException):
        return f"{prov} did not answer in time"
    if isinstance(exc, httpx.HTTPError):
        return f"could not reach {prov}"
    return f"{prov} returned an answer MotionProof could not read"


def explain(report: dict[str, Any], question: str) -> dict[str, Any]:
    st = status()
    digest = evidence_digest(report)
    base = {"provider": st["provider"], "cloud": st["cloud"]}
    if not st["available"]:
        return base | {"available": False, "reason": st["reason"], "evidence": digest}
    prompt = (f"Evidence (JSON):\n{json.dumps(digest)}\n\nQuestion: {question}\n\n"
              "Answer concisely and cite the evidence items you rely on.")
    ask = {"ollama": _ask_ollama, "anthropic": _ask_anthropic,
           "openai": _ask_openai}[st["provider"]]
    try:
        answer = ask(st["model"], prompt)
    except Exception as exc:
        return base | {"available": False, "reason": _failure(st["provider"], exc),
                       "evidence": digest}
    where = (f" The question and the evidence summary shown here were sent to {st['host']}."
             if st["cloud"] else "")
    return base | {"available": True, "model": st["model"], "answer": answer, "evidence": digest,
                   "sent_to": st.get("host"),
                   "disclaimer": "Generated explanation. Verify against the evidence shown; all "
                                 "quantitative results come from the engineering engine." + where}
