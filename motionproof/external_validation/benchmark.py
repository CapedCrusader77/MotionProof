"""External experimental benchmark suite X1..X7 (separate from synthetic benchmarks A..N).

Statuses: PASS, FAIL, NOT RUN, INCOMPATIBLE DATA, INSUFFICIENT DATA. A benchmark passes only
when its pre-registered acceptance criterion holds; failures are reported in full.
"""

from __future__ import annotations

import platform
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import motionproof
from motionproof.external_validation.datasets.registry import ADAPTER_VERSION, DATASETS
from motionproof.external_validation.experiments.protocols import PROTOCOLS, SUPERSEDED
from motionproof.external_validation.experiments.runs import run
from motionproof.external_validation.reports.record import list_runs, save


def run_all(root: Path) -> list[dict[str, Any]]:
    """Run every current protocol. Superseded protocols are not rerun; their recorded runs
    are listed by ``write_results``."""
    return [save(root, run(pid, root)) for pid in PROTOCOLS if pid not in SUPERSEDED]


def _headline(r: dict[str, Any]) -> str:
    if r.get("reason"):
        return str(r["reason"])
    if r.get("headline"):
        return str(r["headline"])
    if "rmse_ratio_model_to_baseline" in r:
        return f"validation RMSE model/baseline {r['rmse_ratio_model_to_baseline']:.3f}"
    parts = []
    for key in ("axes", "joints"):
        for name, sub in r.get(key, {}).items():
            if "rmse_ratio_model_to_baseline" in sub:
                parts.append(f"{name} {sub['status']} ({sub['rmse_ratio_model_to_baseline']:.2f})")
    return "; ".join(parts)


def write_results(records: list[dict[str, Any]], path: Path,
                  root: Path | None = None) -> Path:
    L = ["# External validation results", "",
         f"Generated {datetime.now(UTC).isoformat(timespec='seconds')} with MotionProof "
         f"{motionproof.__version__} (adapter {ADAPTER_VERSION}) on {platform.platform()}, by "
         "`uv run motionproof external benchmark`.", "",
         "Every number below comes from these runs on **public experimental data of other "
         "robots**. They show how well MotionProof's model components reproduce measured "
         "behaviour of those systems on trials that were not used for fitting. They are not "
         "measurements of the MotionProof reference gearbox and do not validate it; "
         "project-specific physical validation (benchmark J) is still NOT RUN.", "",
         "Acceptance criteria were committed before the first run "
         "(`motionproof/external_validation/experiments/protocols.py`), except for X7: it "
         "was written after its published value was known, and only its tolerance model "
         "was fixed beforehand. X7 compares with one published number, not with "
         "measurement series. X1 (transmission-error-v4), X4 (kuka-inverse-v2) and X5 "
         "(nist-tracking-v2) are revisions written after their earlier versions had run and "
         "failed: each adds one physical effect the earlier residuals showed to be missing, "
         "with data split and acceptance unchanged. They are not blind; the earlier runs are "
         "listed under superseded protocols. X8 is a blind test of the X1 revision: its "
         "protocol was committed (40d911f) before any axis 1 file was downloaded.", "",
         "| ID | Validation | System | Status | Headline | Run |", "|---|---|---|---|---|---|"]
    for rec in records:
        r = rec["result"]
        L.append(f"| {r['benchmark']} | {r['title']} | {r['system']} | **{r['status']}** | "
                 f"{_headline(r)} | {rec['id']} |")
    for rec in records:
        r = rec["result"]
        L += ["", f"## {r['benchmark']}. {r['title']}", "", f"- Status: **{r['status']}**",
              f"- Quantity: {r['quantity']}", f"- Baseline: {r['baseline']}",
              f"- Model: {r['model']}", f"- Acceptance: {r['acceptance']}",
              f"- Identification: {r['split']['identification']}",
              f"- Validation: {r['split']['validation']}"]
        if r.get("reason"):
            L.append(f"- Reason: {r['reason']}")
        if r.get("headline"):
            L.append(f"- Result: {r['headline']}")
        L += [f"- {line}" for line in r.get("details", [])]
        rows = []
        if "metrics" in r:
            rows.append(("all", r))
        rows += list(r.get("axes", {}).items()) + list(r.get("joints", {}).items())
        if rows:
            L += ["", "| Part | Status | Validation RMSE model | Validation RMSE baseline | "
                  "Ratio | Model NRMSE |", "|---|---|---|---|---|---|"]
            for name, sub in rows:
                m = sub.get("metrics", {})
                mv = (m.get("model", {}).get("validation")
                      or m.get("validation", {}).get("model", {}))
                bv = (m.get("baseline", {}).get("validation")
                      or m.get("validation", {}).get("baseline", {}))
                if mv:
                    L.append(f"| {name} | {sub.get('status', r['status'])} | {mv['rmse']:.4g} | "
                             f"{bv.get('rmse', float('nan')):.4g} | "
                             f"{sub['rmse_ratio_model_to_baseline']:.3f} | "
                             f"{(mv.get('nrmse') or float('nan')):.3f} |")
        info = DATASETS[r["dataset"]]
        L += ["", f"- Data: {info.citation}", f"- Licence: {info.licence}",
              f"- Report: `external_data/runs/{rec['id']}/report.md`; reproduce: "
              f"`{r['reproduce']}`"]
    if root is not None:
        old = [r for r in list_runs(root) if r["protocol"] in SUPERSEDED]
        if old:
            L += ["", "## Superseded protocols (kept on record)", "",
                  "These runs are not counted above. They stay on record with their original "
                  "status.", "",
                  "| Run | Protocol | Recorded status | Why superseded |", "|---|---|---|---|"]
            for r in old:
                L.append(f"| {r['id']} | {r['protocol']} | {r['status']} | "
                         f"{SUPERSEDED[r['protocol']]} |")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
    return path
