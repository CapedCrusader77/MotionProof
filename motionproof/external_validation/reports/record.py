"""Validation run records, reports and plots.

Each run is stored as ``<root>/runs/VALIDATION_NNN/`` with:
* ``record.json``: protocol, status, trial IDs, parameters, metrics, transformations,
  evidence, dataset manifest entries (checksums) of the files used, adapter and MotionProof
  versions, and the command that reproduces the run;
* ``report.md``: human-readable report;
* ``*.png``: measured-versus-predicted and residual plots.
Runs are never overwritten; a repeat run gets a new ID.
"""

from __future__ import annotations

import json
import platform
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

import motionproof
from motionproof.external_validation.datasets.registry import ADAPTER_VERSION, DATASETS
from motionproof.external_validation.provenance.store import load_manifest


def runs_dir(root: Path) -> Path:
    return Path(root) / "runs"


def next_id(root: Path) -> str:
    d = runs_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    n = [int(p.name.split("_")[1]) for p in d.glob("VALIDATION_*") if p.name[11:].isdigit()]
    return f"VALIDATION_{(max(n) + 1 if n else 1):03d}"


def _clean(o: Any) -> Any:
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items() if not k.startswith("_")}
    if isinstance(o, list | tuple):
        return [_clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, float) and not np.isfinite(o):
        return None
    return o


def _plots(result: dict[str, Any], out: Path) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    series = []
    if "plot" in result:
        series.append(("", result["plot"], result.get("residual_histogram")))
    for key in ("axes", "joints"):
        for name, sub in result.get(key, {}).items():
            if isinstance(sub, dict) and "plot" in sub:
                series.append((name, sub["plot"], sub.get("residual_histogram")))
    files = []
    for name, p, hist in series:
        fig, axs = plt.subplots(1, 2, figsize=(11, 3.6), gridspec_kw={"width_ratios": [3, 1]})
        ax = axs[0]
        ax.plot(p["x"], p["measured"], lw=0.9, color="#1d1d1b", label="measured")
        ax.plot(p["x"], p["predicted"], lw=0.9, color="#c0392b", label="MotionProof model")
        if "baseline" in p:
            ax.plot(p["x"], p["baseline"], lw=0.7, color="#7f8c8d", ls="--", label="baseline")
        ax.set_xlabel(p["x_label"])
        ax.set_ylabel(p["y_label"])
        ax.set_title(f"{name} validation trial {p['trial']}".strip(), fontsize=9)
        ax.legend(fontsize=8)
        ax2 = axs[1]
        if hist:
            e = np.asarray(hist["edges"])
            ax2.bar((e[:-1] + e[1:]) / 2, hist["counts"], width=np.diff(e), color="#c0392b")
            ax2.set_title("validation residuals", fontsize=9)
        else:
            r = np.asarray(p["measured"]) - np.asarray(p["predicted"])
            ax2.hist(r, bins=40, color="#c0392b")
            ax2.set_title("residuals (plotted trial)", fontsize=9)
        fig.tight_layout()
        f = out / f"plot{('_' + name) if name else ''}.png"
        fig.savefig(f, dpi=110)
        plt.close(fig)
        files.append(f.name)
    return files


def _fmt(v: Any) -> str:
    return f"{v:.4g}" if isinstance(v, float) else str(v)


def report_md(rec: dict[str, Any]) -> str:
    r = rec["result"]
    info = DATASETS[r["dataset"]]
    L = [f"# {rec['id']}: {r['title']}", "",
         f"**Status: {r['status']}** (benchmark {r['benchmark']}, protocol `{r['protocol']}`)",
         "", f"- System: {r['system']}", f"- Quantity compared: {r['quantity']}",
         f"- Baseline: {r['baseline']}", f"- MotionProof model: {r['model']}",
         f"- Acceptance (pre-registered): {r['acceptance']}",
         f"- Identification: {r['split']['identification']}",
         f"- Validation: {r['split']['validation']}", f"- Unused: {r['split']['unused']}",
         f"- Scope: {r['scope']}", ""]
    if r.get("reason"):
        L += [f"Reason: {r['reason']}", ""]

    def metric_rows(name: str, m: dict[str, Any]) -> None:
        if "model" in m and "baseline" in m:
            L.extend([f"### {name}", "", "| Set | Model | RMSE | MAE | max abs | mean error | "
                      "NRMSE | R^2 |", "|---|---|---|---|---|---|---|---|"])
            for which in ("model", "baseline"):
                for split, e in m[which].items():
                    L.append(f"| {split} | {which} | {_fmt(e['rmse'])} | {_fmt(e['mae'])} | "
                             f"{_fmt(e['max_abs'])} | {_fmt(e['mean_error'])} | "
                             f"{_fmt(e['nrmse'])} | {_fmt(e['r2'])} |")
            L.append("")
        elif "validation" in m:
            L.extend([f"### {name}", "", "| Set | Model | RMSE | MAE |", "|---|---|---|---|"])
            for split in ("identification", "validation"):
                for which in ("model", "baseline"):
                    e = m[split].get(which)
                    if e:
                        L.append(f"| {split} | {which} | {_fmt(e['rmse'])} | "
                                 f"{_fmt(e['mae'])} |")
            L.append("")

    if "metrics" in r:
        metric_rows("Metrics", r["metrics"])
        if "rmse_ratio_model_to_baseline" in r:
            L += [f"RMSE ratio model / baseline (validation): "
                  f"{r['rmse_ratio_model_to_baseline']:.3f}", ""]
    for key in ("axes", "joints"):
        for name, sub in r.get(key, {}).items():
            if "metrics" in sub:
                metric_rows(f"{name}: {sub['status']}", sub["metrics"])
                L += [f"RMSE ratio model / baseline: {sub['rmse_ratio_model_to_baseline']:.3f}",
                      ""]
    if r.get("fit"):
        L += ["## Fitted parameters", "", "```json", json.dumps(_clean(r["fit"]), indent=1)[:4000],
              "```", ""]
    for p in rec.get("plots", []):
        L += [f"![{p}]({p})", ""]
    L += ["## Transformations", ""] + [f"- {t}" for t in r.get("transformations", [])] + [""]
    if r.get("limitations"):
        L += ["## Limitations", ""] + [f"- {t}" for t in r["limitations"]] + [""]
    L += ["## Data", "", f"- Dataset: {info.title}", f"- Source: {info.url}",
          f"- Version: {info.version}", f"- Licence: {info.licence}",
          f"- Citation: {info.citation}", f"- Files used: {len(rec['files'])} (checksums in "
          "record.json)", "", "## Reproduce", "", f"```bash\n{r['reproduce']}\n```", "",
          f"Recorded {rec['created_utc']} with MotionProof {rec['motionproof_version']}, "
          f"adapter {rec['adapter_version']}, {rec['platform']}.", ""]
    return "\n".join(L)


def save(root: Path, result: dict[str, Any]) -> dict[str, Any]:
    rid = next_id(root)
    out = runs_dir(root) / rid
    out.mkdir(parents=True)
    manifest = load_manifest(root, result["dataset"])["files"]
    files = {rel: manifest[rel] for rel in result.get("files_used", []) if rel in manifest}
    rec = {"id": rid, "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
           "motionproof_version": motionproof.__version__, "adapter_version": ADAPTER_VERSION,
           "platform": platform.platform(), "result": _clean(result), "files": files}
    rec["plots"] = _plots(result, out) if result["status"] in ("PASS", "FAIL") else []
    (out / "record.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
    (out / "report.md").write_text(report_md(rec), encoding="utf-8")
    return rec


def load(root: Path, rid: str) -> dict[str, Any]:
    p = runs_dir(root) / rid / "record.json"
    if not p.exists():
        raise FileNotFoundError(f"no validation run {rid} in {runs_dir(root)}")
    data: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
    return data


def list_runs(root: Path) -> list[dict[str, Any]]:
    out = []
    for p in sorted(runs_dir(root).glob("VALIDATION_*/record.json")):
        r = json.loads(p.read_text(encoding="utf-8"))
        out.append({"id": r["id"], "protocol": r["result"]["protocol"],
                    "benchmark": r["result"]["benchmark"], "status": r["result"]["status"],
                    "dataset": r["result"]["dataset"], "created_utc": r["created_utc"]})
    return out
