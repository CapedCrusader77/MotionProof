"""Engineering reports: JSON, Markdown, CSV and PDF, all from stored experiment data."""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from motionproof.experiments.runner import Experiment
from motionproof.sensitivity.analysis import analyse
from motionproof.statistics.robustness import summarise

REPORT_VERSION = "motionproof.report/1"

LIMITATIONS = [
    "Results are model predictions conditional on the supplied geometry, tolerance "
    "distributions, drive-train parameters and task. They are not a certification.",
    "Rigid multibody dynamics (MuJoCo) with a reduced-order drive train: no gear-tooth "
    "contact, bearing contact, structural deformation, thermal or fatigue effects.",
    "Backlash is a lost-motion relation derived from centre distance and clearance; "
    "tooth-profile errors are not modelled.",
    "Sub-threshold friction preload can creep out (soft friction constraint), so trapped "
    "windup is under-estimated.",
    "Values marked 'assumed' are placeholders and carry no evidential weight.",
]


def build(experiment: Experiment, sensitivity_metric: str | None = None) -> dict[str, Any]:
    m = experiment.manifest
    results = experiment.results()
    summary = summarise(m, results)
    spec = m["model"]["spec"]
    sens = None
    if sensitivity_metric is None and m["config"]["constraints"]:
        sensitivity_metric = m["config"]["constraints"][0]["metric"]
    if sensitivity_metric:
        x, metrics, _ = experiment.metric_matrix()
        if len(x) >= 8 and sensitivity_metric in metrics:
            sens = analyse(experiment.names, x, metrics, sensitivity_metric)
    failures = []
    for r in results:
        for i, f in enumerate(r["failures"], start=1):
            failures.append({"id": f"F-{r['id']}-{i}", "scenario": r["id"], **f,
                             "operating": r["operating"], "seed": m["config"]["sampling"]["seed"],
                             "replicate": r["replicate"]})
    extras = {}
    for name in ("worst_case", "allocation", "calibration", "comparison", "sobol"):
        p = experiment.directory / f"{name}.json"
        if p.is_file():
            extras[name] = json.loads(p.read_text(encoding="utf-8"))
            if name == "worst_case":
                extras[name].pop("history", None)
                extras[name].get("confirmation", {}).pop("trace", None)
    return {
        "report_version": REPORT_VERSION,
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "experiment": {"id": m["id"], "name": m["name"], "created": m["created"]},
        "model": {k: m["model"][k] for k in ("name", "synthetic", "fingerprint",
                                             "geometry_fingerprint", "fidelity")},
        "synthetic_notice": "SYNTHETIC REFERENCE DESIGN - not measured hardware"
        if m["model"]["synthetic"] else None,
        "assumptions": spec.get("assumptions", []),
        "task": m["config"]["task"],
        "sampling": {**m["config"]["sampling"], "scenarios": len(m["design"]["values"]),
                     "independent_draws": m["design"]["independent"],
                     "notes": m["design"]["notes"]},
        "tolerances": [{k: t.get(k) for k in ("id", "component", "parameter", "nominal",
                                               "lower", "upper", "unit", "distribution",
                                               "source", "confidence", "verification")}
                       for t in spec["tolerances"]],
        "correlations": spec.get("correlations", []),
        "operating": m["config"]["operating"],
        "constraints": m["config"]["constraints"],
        "summary": summary,
        "sensitivity": sens,
        "failures": failures[:500],
        "failure_count": len(failures),
        "analyses": extras,
        "versions": m["versions"],
        "limitations": LIMITATIONS,
        "reproduce": f"motionproof experiment replay {m['id']} <scenario id>",
    }


def to_csv(experiment: Experiment) -> str:
    results = experiment.results()
    buf = io.StringIO()
    if not results:
        return ""
    metric_keys = sorted({k for r in results for k in r["metrics"]})
    op_keys = sorted({k for r in results for k in r["operating"]})
    cons = [c["name"] for c in experiment.manifest["config"]["constraints"]]
    w = csv.writer(buf)
    w.writerow(["scenario", "replicate", "valid", "passed", "failure_categories",
                *[f"value:{n}" for n in experiment.names if not n.startswith("op.")],
                *[f"operating:{k}" for k in op_keys], *[f"metric:{k}" for k in metric_keys],
                *[f"margin:{c}" for c in cons]])
    for r in results:
        w.writerow([r["id"], r["replicate"], r["valid"], r["passed"],
                    "|".join(sorted({f["category"] for f in r["failures"]})),
                    *[r["values"].get(n, "") for n in experiment.names
                      if not n.startswith("op.")],
                    *[r["operating"].get(k, "") for k in op_keys],
                    *[r["metrics"].get(k, "") for k in metric_keys],
                    *[r["constraints"].get(c, {}).get("margin", "") for c in cons]])
    return buf.getvalue()


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def to_markdown(rep: dict[str, Any]) -> str:
    s = rep["summary"]
    sc = s["scenarios"]
    lines = [f"# Engineering report: {rep['experiment']['name']}", ""]
    if rep["synthetic_notice"]:
        lines += [f"> **{rep['synthetic_notice']}**", ""]
    lines += [
        f"- Experiment `{rep['experiment']['id']}`, generated {rep['generated']}",
        f"- Model: {rep['model']['name']} (fingerprint `{rep['model']['fingerprint']}`, "
        f"fidelity {rep['model']['fidelity']})",
        f"- Sampling: {rep['sampling']['method']}, {rep['sampling']['scenarios']} scenarios, "
        f"seed {rep['sampling']['seed']}, {rep['sampling']['replicates']} replicate(s)",
        f"- Task: `{rep['task']['type']}`", "",
        "## Result", "",
        f"{sc['completed']} of {sc['total']} scenarios completed: {sc['passed']} passed, "
        f"{sc['failed']} failed, {sc['invalid']} invalid simulations, {sc['out_of_spec']} with "
        "at least one dimension outside its specification limits.", "",
    ]
    a = s["all_constraints"]
    iv = a.get("interval")
    lines.append(f"All constraints satisfied simultaneously: {_pct(a.get('pass_fraction'))}"
                 + (f" (interval {_pct(iv[0])} to {_pct(iv[1])}, {a['interval_method']})"
                    if iv else f" ({a.get('note', 'no interval')})"))
    if a.get("note") and iv:
        lines.append(f"Note: {a['note']}.")
    lines += ["", "| Constraint | Requirement | Pass fraction | Interval | Min margin |",
              "|---|---|---|---|---|"]
    for name, c in s["constraints"].items():
        civ = c.get("interval")
        lines.append(f"| {name} | {c['metric']} {c['op']} {c['limit']:g} | "
                     f"{_pct(c.get('pass_fraction'))} | "
                     f"{_pct(civ[0]) + ' to ' + _pct(civ[1]) if civ else 'not available'} | "
                     f"{c['min_margin']:.3f} |" if c["min_margin"] is not None
                     else f"| {name} | {c['metric']} {c['op']} {c['limit']:g} | n/a | n/a | n/a |")
    lines += ["", "### Failure categories", ""]
    lines += [f"- {k}: {v} scenarios" for k, v in s["failure_categories"].items()] or ["- none"]
    lines += ["", "## Performance distributions", "",
              "| Metric | Mean | 5% | Median | 95% | Max |", "|---|---|---|---|---|---|"]
    for k, v in s["metrics"].items():
        lines.append(f"| {k} | {v['mean']:.5g} | {v['p05']:.5g} | {v['p50']:.5g} | "
                     f"{v['p95']:.5g} | {v['max']:.5g} |")
    if rep["sensitivity"]:
        sens = rep["sensitivity"]
        lines += ["", f"## Sensitivity of `{sens['metric']}`", "",
                  f"Method: {sens['rank_correlation']['method']}. "
                  f"{sens['rank_correlation']['caveat']}.", "",
                  "| Parameter | Spearman rho | 95% interval | Direction |", "|---|---|---|---|"]
        for r in sens["rank_correlation"]["rows"][:10]:
            lines.append(f"| {r['parameter']} | {r['rho']:+.2f} | {r['interval'][0]:+.2f} to "
                         f"{r['interval'][1]:+.2f} | {r['direction']} |")
        r2 = sens["regression"].get("r_squared")
        if r2 is not None:
            lines += ["", f"Linear regression explains R² = {r2:.2f} of the variance; "
                          "standardised coefficients are a variance share only as far as "
                          "that fit holds."]
    wc = rep["analyses"].get("worst_case")
    if wc:
        lines += ["", "## Worst-case search", "",
                  f"{wc['algorithm']}, {wc['evaluations']} evaluations, seed {wc['seed']}: "
                  f"`{wc['metric']}` {wc['direction']}d to {wc['confirmed_value']:.5g} "
                  f"(nominal {wc['nominal_value']:.5g}). Confirmed by a fresh simulation: "
                  f"{'yes' if wc['confirmation_matches'] else 'NO'}; violates a constraint: "
                  f"{'yes' if wc['is_failure'] else 'no'}. {wc['note']}."]
    lines += ["", "## Manufacturing inputs", "",
              "| Tolerance | Nominal | Limits | Unit | Distribution | Confidence |",
              "|---|---|---|---|---|---|"]
    for t in rep["tolerances"]:
        lines.append(f"| {t['id']} | {t['nominal']:g} | {t['lower']:+g} / {t['upper']:+g} | "
                     f"{t['unit']} | {t['distribution']['type']} | {t['confidence']} |")
    lines += ["", "## Assumptions", ""] + [f"- {x}" for x in rep["assumptions"]]
    lines += ["", "## Limitations", ""] + [f"- {x}" for x in rep["limitations"]]
    lines += ["", "## Reproducibility", "",
              f"- Seed {rep['sampling']['seed']}; the full design matrix is stored in the "
              "experiment manifest.", f"- Replay: `{rep['reproduce']}`",
              "- Software: " + ", ".join(f"{k} {v}" for k, v in rep["versions"].items()), ""]
    return "\n".join(lines)


def to_pdf(rep: dict[str, Any], experiment: Experiment, path: str | Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    out = Path(path)
    results = [r for r in experiment.results() if r["valid"]]
    md = to_markdown(rep).splitlines()
    with PdfPages(out) as pdf:
        # text pages
        per_page = 58
        for start in range(0, len(md), per_page):
            fig = plt.figure(figsize=(8.27, 11.69))
            fig.text(0.06, 0.965, "MotionProof engineering report", fontsize=9, color="#555")
            y = 0.94
            for line in md[start:start + per_page]:
                size, weight = 7.5, "normal"
                if line.startswith("# "):
                    line, size, weight = line[2:], 14, "bold"
                elif line.startswith("## "):
                    line, size, weight = line[3:], 11, "bold"
                elif line.startswith("### "):
                    line, size, weight = line[4:], 9, "bold"
                fig.text(0.06, y, line[:150].replace("`", "").replace("**", ""), fontsize=size,
                         fontweight=weight, family="DejaVu Sans Mono" if "|" in line
                         else "DejaVu Sans", va="top")
                y -= 0.0155
            pdf.savefig(fig)
            plt.close(fig)
        # distributions of constrained metrics
        cons = rep["constraints"]
        if results and cons:
            fig, axes = plt.subplots(min(len(cons), 4), 1, figsize=(8.27, 11.69), squeeze=False)
            for ax, c in zip(axes[:, 0], cons[:4], strict=False):
                vals = np.array([r["metrics"][c["metric"]] for r in results])
                ax.hist(vals, bins=30, color="#3d6a9e")
                ax.axvline(c["limit"], color="#b3402a", linestyle="--",
                           label=f"limit {c['op']} {c['limit']:g}")
                ax.set_title(f"{c['name']}: {c['metric']} (n = {len(vals)})", fontsize=10)
                ax.set_ylabel("scenarios")
                ax.legend(fontsize=8)
            fig.tight_layout()
            pdf.savefig(fig)
            plt.close(fig)
        if rep["sensitivity"]:
            rows = rep["sensitivity"]["rank_correlation"]["rows"][:12][::-1]
            fig, ax = plt.subplots(figsize=(8.27, 6))
            rho = [r["rho"] for r in rows]
            err = [[r["rho"] - r["interval"][0] for r in rows],
                   [r["interval"][1] - r["rho"] for r in rows]]
            ax.barh([r["parameter"] for r in rows], rho, xerr=err, color="#3d6a9e",
                    ecolor="#333", capsize=2)
            ax.axvline(0, color="#333", linewidth=0.8)
            ax.set_xlabel("Spearman rank correlation (95% interval)")
            ax.set_title(f"Sensitivity of {rep['sensitivity']['metric']} - association, "
                         "not causation", fontsize=10)
            fig.tight_layout()
            pdf.savefig(fig)
            plt.close(fig)
    return out


def write_all(experiment: Experiment, directory: str | Path | None = None) -> dict[str, str]:
    out = Path(directory) if directory else experiment.directory / "report"
    out.mkdir(parents=True, exist_ok=True)
    rep = build(experiment)
    (out / "report.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    (out / "report.md").write_text(to_markdown(rep), encoding="utf-8")
    (out / "scenarios.csv").write_text(to_csv(experiment), encoding="utf-8", newline="")
    to_pdf(rep, experiment, out / "report.pdf")
    return {k: str(out / f) for k, f in (("json", "report.json"), ("markdown", "report.md"),
                                         ("csv", "scenarios.csv"), ("pdf", "report.pdf"))}
