"""Optional local AI assistant (Ollama). Core functionality never depends on it.

The assistant only ever sees a compact evidence digest built from stored experiment results.
It is instructed to explain and to cite that evidence; every number shown to the user in the
application comes from the engineering engine, never from the language model.

Disable completely with ``MOTIONPROOF_AI=off``.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
MODEL = os.environ.get("MOTIONPROOF_AI_MODEL", "")

SYSTEM = (
    "You are an assistant inside MotionProof, a mechanical tolerance-analysis tool. Explain "
    "the supplied experiment evidence to a mechanical engineer. Rules: use only numbers that "
    "appear in the evidence and quote them exactly; never invent tolerances, measurements or "
    "results; never claim a design is safe, certified or validated; refer to the evidence item "
    "(constraint name, metric, parameter) behind every statement; when the evidence does not "
    "answer the question, say so and suggest which experiment would."
)


def enabled() -> bool:
    return os.environ.get("MOTIONPROOF_AI", "on").lower() not in ("off", "0", "false")


def status() -> dict[str, Any]:
    if not enabled():
        return {"available": False, "reason": "disabled by MOTIONPROOF_AI=off"}
    try:
        r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=0.6)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return {"available": False, "reason": "no local Ollama server reachable"}
    if not models:
        return {"available": False, "reason": "Ollama is running but has no models installed"}
    return {"available": True, "models": models, "model": MODEL or models[0]}


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


def explain(report: dict[str, Any], question: str) -> dict[str, Any]:
    st = status()
    digest = evidence_digest(report)
    if not st["available"]:
        return {"available": False, "reason": st["reason"], "evidence": digest}
    prompt = (f"Evidence (JSON):\n{json.dumps(digest)}\n\nQuestion: {question}\n\n"
              "Answer concisely and cite the evidence items you rely on.")
    try:
        r = httpx.post(f"{OLLAMA_URL}/api/generate", timeout=120, json={
            "model": st["model"], "system": SYSTEM, "prompt": prompt, "stream": False,
            "options": {"temperature": 0.1}})
        r.raise_for_status()
        answer = r.json().get("response", "").strip()
    except Exception as exc:
        return {"available": False, "reason": f"Ollama request failed: {exc}",
                "evidence": digest}
    return {"available": True, "model": st["model"], "answer": answer, "evidence": digest,
            "disclaimer": "Generated explanation. Verify against the evidence shown; all "
                          "quantitative results come from the engineering engine."}
