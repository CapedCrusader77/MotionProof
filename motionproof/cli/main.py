"""``motionproof`` command line interface. Works without the web application.

Exit codes: 0 success, 1 engineering result is negative (failures found, not reproduced,
model blocked), 2 usage or input error.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

import motionproof
from motionproof import services
from motionproof.core.units import length_factor
from motionproof.persistence.store import NotFound, Store

app = typer.Typer(help="MotionProof: tolerance-to-dynamics verification for mechanical "
                       "assemblies.", no_args_is_help=True, add_completion=False)
model_app = typer.Typer(help="Mechanical model files.", no_args_is_help=True)
tolerance_app = typer.Typer(help="Tolerance specifications.", no_args_is_help=True)
assembly_app = typer.Typer(help="Virtual as-manufactured assemblies.", no_args_is_help=True)
experiment_app = typer.Typer(help="Virtual manufacturing experiments.", no_args_is_help=True)
calibration_app = typer.Typer(help="Calibration against measurements.", no_args_is_help=True)
reference_app = typer.Typer(help="Synthetic reference design.", no_args_is_help=True)
for name, sub in (("model", model_app), ("tolerance", tolerance_app),
                  ("assembly", assembly_app), ("experiment", experiment_app),
                  ("calibration", calibration_app), ("reference", reference_app)):
    app.add_typer(sub, name=name)

console = Console()
err = Console(stderr=True)
HomeOpt = Annotated[Path | None, typer.Option("--home", help="Workspace directory "
                                              "(default: ./workspace or $MOTIONPROOF_HOME).")]


def fail(message: str, code: int = 2) -> None:
    err.print(f"[red]error:[/red] {message}")
    raise typer.Exit(code)


def guard(fn: Any) -> Any:
    """Turn expected errors into clean messages and exit code 2."""
    import functools

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except typer.Exit:
            raise
        except NotFound as exc:
            fail(str(exc.args[0]))
        except ValidationError as exc:
            lines = [f"  {'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors()]
            fail("invalid configuration:" + "".join(f"\n{x}" for x in lines))
        except (ValueError, KeyError, FileNotFoundError, RuntimeError) as exc:
            fail(str(exc.args[0]) if exc.args else str(exc))
    return wrapper


def _model(path: Path) -> Any:
    from motionproof.model import MechanicalModel

    return MechanicalModel.load(path)


def _experiment(home: Path | None, exp: str) -> Any:
    from motionproof.experiments.runner import Experiment

    p = Path(exp)
    if (p / "manifest.json").is_file():
        return Experiment.open(p)
    return Experiment.open(Store(home).experiment(exp)["directory"])


def _default_project(store: Store) -> str:
    projects = store.projects()
    return str(projects[-1]["id"] if projects else store.create_project("default")["id"])


@app.callback(invoke_without_command=True)
def main(version: Annotated[bool, typer.Option("--version", help="Show the version.")] = False
         ) -> None:
    if version:
        console.print(f"motionproof {motionproof.__version__}")
        raise typer.Exit


@app.command()
@guard
def doctor() -> None:
    """Check the environment: dependencies, MuJoCo, CAD kernel, workspace."""
    import importlib

    table = Table("check", "result")
    ok = True
    for mod in ("numpy", "scipy", "mujoco", "trimesh", "cadquery", "OCP", "fastapi",
                "matplotlib", "yaml", "pydantic"):
        try:
            m = importlib.import_module(mod)
            table.add_row(mod, f"[green]{getattr(m, '__version__', 'ok')}[/green]")
        except Exception as exc:
            ok = False
            table.add_row(mod, f"[red]missing ({exc})[/red]")
    try:
        from motionproof.simulation.tasks import StaticHold

        with tempfile.TemporaryDirectory() as tmp:
            from motionproof.reference.nema17_arm import write_reference_project

            m = _model(write_reference_project(tmp))
            r = m.simulate(StaticHold(pose={"shoulder": 0.0}), keep_trace=False)
            table.add_row("reference simulation",
                          "[green]ok[/green]" if r.valid else "[red]invalid[/red]")
            ok &= r.valid
    except Exception as exc:
        ok = False
        table.add_row("reference simulation", f"[red]{exc}[/red]")
    from motionproof.ai.assistant import status

    ai = status()
    table.add_row("optional AI (Ollama)", "available" if ai["available"]
                  else f"not available: {ai['reason']} (not required)")
    console.print(table)
    raise typer.Exit(0 if ok else 1)


@app.command()
@guard
def inspect(file: Path, as_json: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Inspect a CAD or model file (STEP, STL, OBJ, URDF, MJCF) without importing it."""
    from motionproof.cad.importers import inspect_file

    with tempfile.TemporaryDirectory() as tmp:
        info = inspect_file(file, tmp)
    if as_json:
        console.print_json(json.dumps(info))
        return
    console.print(f"[bold]{info['file']}[/bold]  format {info['format']}  "
                  f"units {info['units'].get('geometry')}  sha256 {info['sha256'][:16]}")
    table = Table("component", "valid", "volume mm³", "mass kg", "bbox")
    for c in info["components"]:
        vol = "-" if c["volume_mm3"] is None else f"{c['volume_mm3']:.2f}"
        mass = "-" if c["mass_kg"] is None else f"{c['mass_kg']:.4f}"
        bbox = "-" if not c["bbox"] else " x ".join(
            f"{b - a:.2f}" for a, b in zip(*c["bbox"], strict=True))
        table.add_row(c["name"], str(c["valid"]), vol, mass, bbox)
    console.print(table)
    for w in info["warnings"]:
        console.print(f"[yellow]warning:[/yellow] {w}")


@app.command()
@guard
def serve(host: str = "127.0.0.1", port: int = 8000, home: HomeOpt = None) -> None:
    """Start the API (and the built web application, when frontend/dist exists)."""
    import uvicorn

    from motionproof.api.app import create_app

    uvicorn.run(create_app(home), host=host, port=port, log_level="info")


@reference_app.command("create")
@guard
def reference_create(directory: Path) -> None:
    """Write the synthetic NEMA 17 planetary-joint reference model to DIRECTORY."""
    from motionproof.reference.nema17_arm import write_reference_project

    path = write_reference_project(directory)
    console.print(f"reference model written to {path}")
    console.print("[yellow]synthetic design: every value is an illustrative assumption[/yellow]")


@model_app.command("validate")
@guard
def model_validate(model_file: Path,
                   as_json: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Validate a model file and print its readiness report."""
    rep = services.readiness(_model(model_file))
    if as_json:
        console.print_json(json.dumps(rep))
    else:
        table = Table("area", "status", "detail")
        colours = {"ok": "green", "warning": "yellow", "error": "red", "info": "cyan"}
        for c in rep["checks"]:
            table.add_row(c["area"], f"[{colours[c['status']]}]{c['status']}[/]", c["message"])
        console.print(table)
        console.print(f"readiness: [bold]{rep['status']}[/bold]  fidelity: {rep['fidelity']}")
    raise typer.Exit(1 if rep["status"] == "blocked" else 0)


@tolerance_app.command("inspect")
@guard
def tolerance_inspect(model_file: Path) -> None:
    """List tolerances, fit classes, capability indices and validation findings."""
    rev = services.tolerance_review(_model(model_file))
    spec = _model(model_file).spec
    table = Table("id", "nominal", "limits", "unit", "distribution", "mean", "std",
                  "out of spec", "confidence")
    for t, r in zip(spec.tolerances, rev["review"], strict=True):
        table.add_row(t.id, f"{t.nominal:g}", f"{t.lower:+g}/{t.upper:+g}", t.unit,
                      t.distribution.type, f"{r['mean']:.5g}", f"{r['std']:.3g}",
                      f"{100 * r['fraction_out_of_spec']:.2f}%", t.confidence.value)
    console.print(table)
    for f in rev["fits"]:
        console.print(f"fit {f['fit']}: {f['class']} fit, clearance "
                      f"{f['min_clearance']:+.4f} to {f['max_clearance']:+.4f} {f['unit']}")
    for r in rev["review"]:
        if r["capability"]:
            c = r["capability"]
            console.print(f"capability {c['tolerance']}: Cp {c['cp']:.2f}, Cpk {c['cpk']:.2f} "
                          f"({c['basis']} process data)")
    for f in rev["findings"]:
        colour = {"error": "red", "warning": "yellow"}.get(f["severity"], "cyan")
        console.print(f"[{colour}]{f['severity']}[/] {f['tolerance'] or '-'}: {f['message']}")


@assembly_app.command("generate-variants")
@guard
def assembly_generate(model_file: Path, samples: int = 10, seed: int = 0,
                      method: str = "monte_carlo",
                      output: Annotated[Path | None, typer.Option("--output", "-o")] = None
                      ) -> None:
    """Generate virtual as-manufactured variants and their derived assembly quantities."""
    data = services.generate_variants(_model(model_file), method, samples, seed)  # type: ignore[arg-type]
    if output:
        output.write_text(json.dumps(data, indent=1), encoding="utf-8")
        console.print(f"{len(data['variants'])} variants written to {output}")
    table = Table("variant", "backlash mrad", "radial play µm", "fits", "violations",
                  "out of spec")
    for v in data["variants"][:25]:
        j = next(iter(v["joints"].values()), None)
        fits = ", ".join(f"{f['clearance'] * 1000:+.1f}" for f in v["fits"])
        table.add_row(v["id"], "-" if j is None else f"{j['backlash'] * 1e3:.3f}",
                      "-" if j is None else f"{j['radial_play'] * 1e6:.1f}", fits,
                      str(len(v["violations"])), str(len(v["out_of_spec"])))
    console.print(table)


@experiment_app.command("run")
@guard
def experiment_run(experiment_file: Path, home: HomeOpt = None) -> None:
    """Run an experiment defined in YAML (keys: model, plus the experiment configuration)."""
    from motionproof.experiments.runner import Experiment, ExperimentConfig
    from motionproof.statistics.robustness import summarise

    raw = yaml.safe_load(experiment_file.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "model" not in raw:
        fail("the experiment file needs a 'model' key with the path of a model.yaml")
    model_path = (experiment_file.parent / raw.pop("model")).resolve()
    config = ExperimentConfig.model_validate(raw)
    model = _model(model_path)
    store = Store(home)
    pid = _default_project(store)
    mid = next((m["id"] for m in store.models(pid)
                if Path(m["directory"]) == model.directory), None)
    if mid is None:
        mid = store._next_id("MDL")
        store.register_model(mid, pid, model.spec.name, model.spec.source.kind,
                             model.spec.synthetic, model.directory)
    eid, directory = store.new_experiment_dir(pid)
    exp = Experiment.create(model, config, directory, eid)
    store.register_experiment(eid, pid, mid, config.name, directory)
    console.print(f"experiment [bold]{eid}[/bold]: {exp.total} scenarios "
                  f"({config.sampling.method}, seed {config.sampling.seed})")
    with console.status("running") as status:
        out = exp.run(model, progress=lambda p: status.update(
            f"{p['done']}/{p['total']}  passed {p['passed']}  failed {p['failed']}  "
            f"invalid {p['invalid']}"))
    summary = summarise(exp.manifest, exp.results())
    store.update_experiment(eid, out["status"], {
        "scenarios": summary["scenarios"], "all_constraints": summary["all_constraints"],
        "failure_categories": summary["failure_categories"]})
    _print_summary(summary)
    console.print(f"stored in {directory}  ({out['elapsed']:.1f} s)")
    raise typer.Exit(1 if summary["scenarios"]["failed"] else 0)


def _print_summary(summary: dict[str, Any]) -> None:
    sc = summary["scenarios"]
    console.print(f"completed {sc['completed']}/{sc['total']}: {sc['passed']} passed, "
                  f"{sc['failed']} failed, {sc['invalid']} invalid")
    table = Table("constraint", "requirement", "pass fraction", "interval", "min margin")
    for name, c in {**summary["constraints"], "ALL": summary["all_constraints"]}.items():
        iv = c.get("interval")
        frac = c.get("pass_fraction")
        table.add_row(
            name, f"{c['metric']} {c['op']} {c['limit']:g}" if "metric" in c else "all",
            "-" if frac is None else f"{100 * frac:.1f}%",
            f"{100 * iv[0]:.1f}-{100 * iv[1]:.1f}% ({c['interval_method']})" if iv
            else c.get("note", "-"),
            "-" if c.get("min_margin") is None else f"{c['min_margin']:+.3f}")
    console.print(table)
    for cat, n in summary["failure_categories"].items():
        console.print(f"failure category {cat}: {n} scenarios")


@experiment_app.command("inspect")
@guard
def experiment_inspect(experiment: str, home: HomeOpt = None) -> None:
    """Show an experiment's configuration and robustness summary."""
    from motionproof.statistics.robustness import summarise

    exp = _experiment(home, experiment)
    m = exp.manifest
    console.print(f"[bold]{m['id']}[/bold] {m['name']}  created {m['created']}")
    console.print(f"model {m['model']['name']}  fingerprint {m['model']['fingerprint']}  "
                  f"fidelity {m['model']['fidelity']}")
    console.print(f"sampling {m['config']['sampling']}  scenarios {exp.total}")
    if exp.results():
        _print_summary(summarise(m, exp.results()))


@experiment_app.command("replay")
@guard
def experiment_replay(experiment: str,
                      scenario: Annotated[str | None, typer.Argument()] = None,
                      home: HomeOpt = None) -> None:
    """Replay one scenario (or, without SCENARIO, every stored scenario) and compare."""
    exp = _experiment(home, experiment)
    ids = [scenario] if scenario else [r["id"] for r in exp.results()]
    model = exp.model()
    bad = []
    for sid in ids:
        if not exp.replay(sid, model)["reproduced"]:
            bad.append(sid)
    if bad:
        console.print(f"[red]NOT reproduced:[/red] {bad[:20]}")
        raise typer.Exit(1)
    console.print(f"[green]reproduced[/green] {len(ids)} scenario(s) exactly")


@experiment_app.command("analyse")
@guard
def experiment_analyse(experiment: str, metric: str, home: HomeOpt = None) -> None:
    """Sensitivity of METRIC to the manufacturing and operating variables."""
    from motionproof.sensitivity.analysis import analyse

    exp = _experiment(home, experiment)
    x, metrics, _ = exp.metric_matrix()
    a = analyse(exp.names, x, metrics, metric)
    console.print(f"{a['rank_correlation']['method']} - {a['rank_correlation']['caveat']}")
    table = Table("parameter", "rho", "95% interval", "direction")
    for r in a["rank_correlation"]["rows"][:15]:
        table.add_row(r["parameter"], f"{r['rho']:+.2f}",
                      f"{r['interval'][0]:+.2f} .. {r['interval'][1]:+.2f}", r["direction"])
    console.print(table)
    r2 = a["regression"].get("r_squared")
    if r2 is not None:
        console.print(f"linear regression R² = {r2:.2f}")


@experiment_app.command("compare")
@guard
def experiment_compare(experiment: str, scenario_a: str, scenario_b: str,
                       home: HomeOpt = None) -> None:
    """Compare the inputs and metrics of two stored scenarios."""
    exp = _experiment(home, experiment)
    res = {r["id"]: r for r in exp.results()}
    for s in (scenario_a, scenario_b):
        if s not in res:
            fail(f"scenario {s!r} not found")
    a, b = res[scenario_a], res[scenario_b]
    table = Table("quantity", scenario_a, scenario_b, "difference")
    for section in ("values", "operating", "metrics"):
        for k in sorted(set(a[section]) | set(b[section])):
            va, vb = a[section].get(k), b[section].get(k)
            if va is None or vb is None or va == vb:
                continue
            table.add_row(f"{section[:-1]}:{k}", f"{va:.6g}", f"{vb:.6g}", f"{vb - va:+.3g}")
    console.print(table)
    console.print(f"{scenario_a}: {'passed' if a['passed'] else 'FAILED'}   "
                  f"{scenario_b}: {'passed' if b['passed'] else 'FAILED'}")


@experiment_app.command("export")
@guard
def experiment_export(experiment: str, scenario: str, output: Path,
                      home: HomeOpt = None) -> None:
    """Export one scenario (inputs, results, trace) as a self-contained JSON file."""
    exp = _experiment(home, experiment)
    rep = exp.replay(scenario)
    payload = {"experiment": exp.manifest["id"], "model": {
        k: v for k, v in exp.manifest["model"].items() if k != "directory"},
        "config": exp.manifest["config"], "versions": exp.manifest["versions"],
        "scenario": rep["replayed"] | {"id": scenario}, "reproduced": rep["reproduced"]}
    output.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    console.print(f"scenario {scenario} written to {output}")


@app.command()
@guard
def optimise(experiment: str, metric: str, direction: str = "maximise",
             algorithm: str = "differential_evolution", budget: int = 300, seed: int = 0,
             minimise: Annotated[bool, typer.Option(help="Also minimise the failure.")] = False,
             home: HomeOpt = None) -> None:
    """Worst-case search: find the configuration with the worst METRIC."""
    from motionproof.optimisation import worst_case

    exp = _experiment(home, experiment)
    model = exp.model()
    with console.status("searching") as status:
        res = worst_case.search(model, exp.config, metric, direction, algorithm,  # type: ignore[arg-type]
                                budget, seed, progress=lambda p: status.update(
                                    f"{p['done']} evaluations, best {p['best']}"))
    worst_case.save(res, exp.directory / "worst_case.json")
    console.print(f"{res['algorithm']}: {res['evaluations']} evaluations")
    console.print(f"{metric}: nominal {res['nominal_value']:.6g} -> worst found "
                  f"{res['confirmed_value']:.6g} (confirmed by fresh simulation: "
                  f"{res['confirmation_matches']})")
    console.print(f"violates a constraint: [bold]{res['is_failure']}[/bold]")
    console.print(res["note"])
    if minimise and res["is_failure"]:
        mini = worst_case.minimise_failure(model, exp.config, res["configuration"])
        worst_case.save(mini, exp.directory / "minimise.json")
        console.print(f"minimised: {len(mini['essential_parameters'])} parameters are enough "
                      f"to keep the failure: {sorted(mini['essential_parameters'])}")
    raise typer.Exit(1 if res["is_failure"] else 0)


@calibration_app.command("fit")
@guard
def calibration_fit(measurements: Path, config_file: Annotated[Path, typer.Option(
        "--config", "-c", help="YAML with: model, plus the calibration configuration.")],
        holdout: Annotated[Path | None, typer.Option(help="Separate holdout CSV.")] = None,
        output: Annotated[Path | None, typer.Option("--output", "-o")] = None) -> None:
    """Fit model parameters to a measurement CSV and assess them on holdout data."""
    from motionproof.calibration.fit import CalibrationConfig, calibrate, read_csv

    raw = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    model = _model((config_file.parent / raw.pop("model")).resolve())
    cfg = CalibrationConfig.model_validate(raw)
    res = calibrate(model, cfg, read_csv(measurements, cfg),
                    read_csv(holdout, cfg) if holdout else None)
    table = Table("parameter", "estimate", "std error", "bounds")
    for p in res["parameters"]:
        se = "-" if p["std_error"] is None else f"{p['std_error']:.3g}"
        table.add_row(f"{p['joint']}.{p['name']}", f"{p['estimate']:.6g}", se,
                      f"{p['lower']:g} .. {p['upper']:g}")
    console.print(table)
    for sig, e in res["calibration"]["errors"].items():
        h = res["holdout"]["errors"][sig]
        console.print(f"{sig}: calibration RMSE {e['rmse']:.4g}, holdout RMSE {h['rmse']:.4g} "
                      f"({res['holdout']['split']})")
    for w in res["warnings"]:
        console.print(f"[yellow]warning:[/yellow] {w}")
    if output:
        output.write_text(json.dumps(res, indent=1), encoding="utf-8")
    raise typer.Exit(0 if res["assessment"] == "holdout_consistent" else 1)


@app.command()
@guard
def report(experiment: str, output: Annotated[Path | None, typer.Option(
        "--output", "-o", help="Directory for report files.")] = None,
        home: HomeOpt = None) -> None:
    """Write the engineering report (JSON, Markdown, CSV, PDF) for an experiment."""
    from motionproof.reporting.report import write_all

    files = write_all(_experiment(home, experiment), output)
    for kind, path in files.items():
        console.print(f"{kind}: {path}")


if __name__ == "__main__":
    app()


@assembly_app.command("compare-poses")
@guard
def assembly_compare_poses(reference: Path, moved: Path,
                           output: Annotated[Path | None, typer.Option("--output", "-o")] = None
                           ) -> None:
    """Derive joints from two STEP exports of the same assembly in different poses."""
    from motionproof.cad.configurations import compare_configurations

    res = compare_configurations(reference, moved)
    if output:
        output.write_text(json.dumps(res, indent=1), encoding="utf-8")
    console.print(f"{res['solids']} solids: {len(res['fixed'])} fixed, "
                  f"{sum(len(j['components']) for j in res['joints'])} moved, "
                  f"{len(res['unmatched'])} unmatched")
    for j in res["joints"]:
        if j["type"] == "prismatic":
            console.print(f"[bold]prismatic[/bold] along {[round(v, 5) for v in j['axis']]}, "
                          f"travel {j['travel_mm']:.4f} mm")
        else:
            console.print(f"[bold]{j['type']}[/bold] axis {[round(v, 5) for v in j['axis']]} "
                          f"through {[round(v, 4) for v in j['point_mm']]} mm, "
                          f"angle {j['angle_deg']:.4f} deg")
        console.print(f"  moving parts: {', '.join(j['components'])}")
        console.print(f"  fit residual: {j['max_residual_mm']:.2e} mm")
    if res["unmatched"]:
        console.print(f"[yellow]unmatched:[/yellow] {', '.join(res['unmatched'])}")
    console.print(res["note"])


# =========================================================================== advanced commands

scan_app = typer.Typer(help="As-built inspection from point clouds.", no_args_is_help=True)
mfg_app = typer.Typer(help="Process-aware manufacturing variation.", no_args_is_help=True)
workspace_app = typer.Typer(help="Workspace reliability maps.", no_args_is_help=True)
degradation_app = typer.Typer(help="Lifetime degradation projections.", no_args_is_help=True)
hardware_app = typer.Typer(help="Hardware-in-the-loop tests.", no_args_is_help=True)
challenge_app = typer.Typer(help="The MotionProof Engineering Challenge.", no_args_is_help=True)
benchmark_app = typer.Typer(help="Reproducible benchmark suite.", no_args_is_help=True)
for _name, _sub in (("scan", scan_app), ("manufacturing", mfg_app),
                    ("workspace", workspace_app), ("degradation", degradation_app),
                    ("hardware", hardware_app), ("challenge", challenge_app),
                    ("benchmark", benchmark_app)):
    app.add_typer(_sub, name=_name)


def _yaml_with_model(path: Path) -> tuple[Any, dict[str, Any]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "model" not in raw:
        fail(f"{path.name} needs a 'model' key with the path of a model.yaml")
    return _model((path.parent / raw.pop("model")).resolve()), raw


def _dump(data: Any, output: Path | None) -> None:
    if output:
        output.write_text(json.dumps(data, indent=1, default=float), encoding="utf-8")
        console.print(f"written {output}")


@scan_app.command("inspect")
@guard
def scan_inspect(scan: Path, units: Annotated[str | None, typer.Option(
        help="Length unit of the scan (mm, cm, m, in). Never assumed.")] = None) -> None:
    """Read a point cloud and report size, units, noise and cleaning results."""
    from motionproof.scans import pointcloud as P

    c = P.read_point_cloud(scan, units=units)
    s = c.summary()
    console.print(f"{s['points']} points, units {s['units'] or '[yellow]NOT STATED[/yellow]'}, "
                  f"extents {[round(v, 4) for v in s['extents']]}")
    clean = P.remove_outliers(P.remove_duplicates(c))
    for h in clean.history:
        console.print(f"  {h}")
    console.print(f"local noise estimate {P.noise_estimate(clean):.4g} (scan units)")


@scan_app.command("compare")
@guard
def scan_compare(scan: Path, nominal: Path,
                 units: Annotated[str, typer.Option(help="Unit of the scan.")],
                 nominal_units: Annotated[str | None, typer.Option(
                     help="Unit of an STL/OBJ nominal (STEP is mm).")] = None,
                 lock: Annotated[str, typer.Option(help="Comma-separated locked DOF, e.g. "
                                                        "rz,tz")] = "",
                 accept_rms: Annotated[float | None, typer.Option()] = None,
                 limit: Annotated[float | None, typer.Option(help="Deviation limit, mm")] = None,
                 cylinder: Annotated[str | None, typer.Option(
                     help="Measure a cylinder: px,py,pz,dx,dy,dz,radius[,start,length] (mm)")]
                 = None,
                 output: Annotated[Path | None, typer.Option("--output", "-o")] = None) -> None:
    """Align a scan to nominal geometry and report deviations (and a cylinder diameter)."""
    import numpy as np

    from motionproof.scans import inspection as I
    from motionproof.scans import pointcloud as P
    from motionproof.scans import registration as R

    c = P.remove_outliers(P.remove_duplicates(P.read_point_cloud(scan, units=units)))
    pts = c.in_mm()
    nom = R.Nominal.from_file(nominal, nominal_units)
    locked = tuple(x for x in lock.split(",") if x)
    reg = R.icp(pts, nom, init=R.coarse_align(pts, nom), lock=locked,
                noise=P.noise_estimate(c) * length_factor(units) * 1000, accept_rms=accept_rms)
    console.print(f"registration: {reg.method}, RMS {reg.rms:.4g} mm, max {reg.max_residual:.4g}"
                  f" mm, {reg.inliers}/{reg.points} points, converged {reg.converged}")
    for d in reg.diagnostics:
        console.print(f"[yellow]  {d}[/yellow]")
    console.print("valid for inspection: " + ("[green]yes[/green]" if reg.valid_for_inspection
                                              else "[red]NO - do not use dimensions[/red]"))
    aligned = reg.apply(pts)
    dev = I.deviation(aligned, nom, limit)
    console.print(f"deviation mm: mean {dev['mean']:+.4g}, std {dev['std']:.4g}, RMS "
                  f"{dev['rms']:.4g}, min {dev['min']:+.4g}, max {dev['max']:+.4g}; coverage "
                  f"{dev['coverage']['fraction_of_nominal_surface']:.1%} of the nominal surface")
    out: dict[str, Any] = {"registration": reg.to_dict(), "deviation": {
        k: v for k, v in dev.items() if k not in ("heatmap", "missing")}}
    if cylinder:
        v = [float(x) for x in cylinder.split(",")]
        if len(v) not in (7, 9):
            fail("--cylinder needs 7 or 9 numbers")
        mask = I.select_near_cylinder(aligned, np.array(v[:3]), np.array(v[3:6]), v[6], 0.3,
                                      *(v[7:9] if len(v) == 9 else (None, None)))
        fit = I.fit_cylinder(aligned[mask], np.array(v[3:6]))
        console.print(f"cylinder: diameter {fit.diameter:.5f} mm (std error "
                      f"{fit.diameter_std_error:.2g}), {fit.points} points, "
                      f"{fit.arc_coverage_deg:.0f} deg covered")
        for w in fit.warnings:
            console.print(f"[yellow]  {w}[/yellow]")
        out["cylinder"] = fit.to_dict()
    _dump(out, output)
    raise typer.Exit(0 if reg.valid_for_inspection else 1)


@mfg_app.command("batch")
@guard
def manufacturing_batch(process_file: Path, output: Annotated[Path | None, typer.Option(
        "--output", "-o")] = None) -> None:
    """Generate a virtual production batch (YAML: process, plan)."""
    from motionproof.process.model import (
        BatchPlan,
        ProcessModel,
        batch_summary,
        generate_batch,
        variance_components,
    )

    raw = yaml.safe_load(process_file.read_text(encoding="utf-8"))
    pm, plan = ProcessModel.model_validate(raw["process"]), BatchPlan.model_validate(raw["plan"])
    b = generate_batch(pm, plan)
    table = Table("feature", "process", "mean", "std", "Cp", "Cpk", "out of spec")
    summ = batch_summary(pm, b)
    for k, s in summ.items():
        table.add_row(k, s["process"], f"{s['mean']:.5f}", f"{s['std']:.3g}",
                      "-" if s["cp"] is None else f"{s['cp']:.2f}",
                      "-" if s["cpk"] is None else f"{s['cpk']:.2f}",
                      f"{100 * s['out_of_spec_fraction']:.2f}%")
    console.print(f"{b['parts']} parts (virtual batch from the stated model, not production "
                  "data)")
    console.print(table)
    for f in pm.features:
        try:
            vc = variance_components(b["actual"][f.feature], b["batch"], b["setup"])
            console.print(f"{f.feature}: batch {vc['batch_std']:.3g}, setup "
                          f"{vc['setup_std']:.3g}, part {vc['part_std']:.3g}")
            for note in vc["notes"]:
                console.print(f"[yellow]  {note}[/yellow]")
        except ValueError as exc:
            console.print(f"{f.feature}: {exc}")
    _dump(summ, output)


@experiment_app.command("adaptive")
@guard
def experiment_adaptive(config_file: Path, initial: int = 30, budget: int = 150,
                        population: int = 5000, seed: int = 0,
                        output: Annotated[Path | None, typer.Option("--output", "-o")] = None
                        ) -> None:
    """Adaptive experiment: Gaussian-process active learning near the failure boundary."""
    import numpy as np

    from motionproof.adaptive.sampler import run_adaptive
    from motionproof.experiments.runner import ExperimentConfig, evaluate_scenario
    from motionproof.tolerances.sampling import VariableSpace

    model, raw = _yaml_with_model(config_file)
    cfg = ExperimentConfig.model_validate(raw)
    space = VariableSpace.from_model(model.spec, cfg.operating)

    def g(x: np.ndarray) -> float:
        res = evaluate_scenario(model, cfg, dict(zip(space.names, x.tolist(), strict=True)))
        if not res["valid"]:
            return -1.0
        m = min((c["margin"] for c in res["constraints"].values()), default=-1.0)
        return min(m, -1e-3) if any(f["severity"] == "assembly_violation"
                                    for f in res["failures"]) else m

    with console.status("adaptive sampling") as status:
        res = run_adaptive(g, lambda n, s: space.design("monte_carlo", n, s).values,
                           space.bounds(), initial, budget, population, seed,
                           progress=lambda p: status.update(
                               f"{p['done']} simulations, predicted failure fraction "
                               f"{p['predicted_failure_fraction']:.4f}"))
    s, sur = res["simulations"], res["surrogate"]
    console.print(f"true simulations {s['total']} ({s['initial']} initial, {s['adaptive']} "
                  f"adaptive), simulated failures {s['failures_simulated']}")
    console.print(f"surrogate PREDICTION over {sur['population']} population points: failure "
                  f"fraction {sur['predicted_failure_fraction']:.4g}, uncertain points "
                  f"{sur['uncertain_points']}, LOO Q2 {sur['leave_one_out_q2']:.2f}")
    console.print(f"stopped: {res['stopping_reason']}")
    for w in res["warnings"]:
        console.print(f"[yellow]{w}[/yellow]")
    _dump(res, output)


@workspace_app.command("analyse")
@guard
def workspace_analyse(config_file: Path, output: Annotated[Path | None, typer.Option(
        "--output", "-o")] = None) -> None:
    """Workspace map (YAML: model, grid, samples, seed, position_tolerance, payload_mass)."""
    from motionproof.tolerances.sampling import VariableSpace
    from motionproof.workspace.maps import reliability_map

    model, raw = _yaml_with_model(config_file)
    space = VariableSpace.from_model(model.spec)
    rows = [dict(zip(space.names, r.tolist(), strict=True)) for r in
            space.design("monte_carlo", int(raw.get("samples", 30)),
                         int(raw.get("seed", 0))).values]
    res = reliability_map(model, raw["grid"], rows, raw.get("position_tolerance"),
                          float(raw.get("payload_mass", 0.0)))
    table = Table("pose", "reachable", "RMS error mm", "max mm", "within tol", "near singular")
    for c in res["cells"]:
        table.add_row(", ".join(f"{k}={v:g}" for k, v in c["pose"].items()),
                      str(c["reachable"]),
                      f"{c['error_rms'] * 1e3:.3f}" if c["reachable"] else "-",
                      f"{c['error_max'] * 1e3:.3f}" if c["reachable"] else "-",
                      f"{c['within_tolerance']:.1%}" if "within_tolerance" in c else "-",
                      str(c.get("near_singular", "-")))
    console.print(f"{res['level']}, {res['variants']} variants; {res['collision']}")
    console.print(table)
    _dump(res, output)


@degradation_app.command("run")
@guard
def degradation_run(config_file: Path, output: Annotated[Path | None, typer.Option(
        "--output", "-o")] = None) -> None:
    """Lifetime projection (YAML: model, mechanisms, cycles, constraints, pose or task)."""
    from pydantic import TypeAdapter

    from motionproof.degradation.model import Mechanism, lifetime_experiment
    from motionproof.experiments.runner import Constraint
    from motionproof.simulation.tasks import Task

    model, raw = _yaml_with_model(config_file)
    res = lifetime_experiment(
        model, [Mechanism.model_validate(m) for m in raw["mechanisms"]], raw["cycles"],
        [Constraint.model_validate(c) for c in raw["constraints"]],
        task=TypeAdapter(Task).validate_python(raw["task"]) if raw.get("task") else None,
        pose=raw.get("pose"), payload_mass=float(raw.get("payload_mass", 0.0)))
    console.print(f"[bold]{res['label']}[/bold] ({res['level']})")
    for name, c in res["threshold_crossings"].items():
        console.print(f"{name}: " + (f"crossed at {c['cycles']:.0f} cycles ({c['note']})"
                                     if c["cycles"] is not None else c["note"]))
    _dump(res, output)


@hardware_app.command("devices")
@guard
def hardware_devices() -> None:
    """List available devices (the simulated device is always present)."""
    from motionproof.hardware.device import list_devices

    for d in list_devices():
        console.print(f"{d['id']:12} {d['kind']:10} "
                      f"{'available' if d['available'] else 'unavailable'}  {d['description']}")


@hardware_app.command("test")
@guard
def hardware_test(config_file: Path,
                  confirm: Annotated[bool, typer.Option(
                      "--confirm", help="Required: confirms the rig may move.")] = False,
                  device: Annotated[str, typer.Option(help="'simulated' or a serial port")]
                  = "simulated",
                  csv_out: Annotated[Path | None, typer.Option("--csv")] = None) -> None:
    """Run a test (YAML: model, test, limits, optional simulated_truth)."""
    from motionproof.hardware.device import (
        HardwareTest,
        SafetyLimits,
        SerialDevice,
        SimulatedDevice,
        compare_with_simulation,
        run_test,
    )

    model, raw = _yaml_with_model(config_file)
    test, limits = HardwareTest.model_validate(raw["test"]), SafetyLimits.model_validate(
        raw["limits"])
    dev: Any = SimulatedDevice(model, raw.get("simulated_truth")) if device == "simulated" \
        else SerialDevice(device)
    s = run_test(dev, test, limits, confirm_actuation=confirm)
    console.print(f"[bold]{s.source}[/bold]: {s.status}"
                  + (f" - {s.abort_reason}" if s.abort_reason else ""))
    console.print(f"{len(s.samples)} samples, {s.lost_packets} lost, {s.malformed} malformed")
    if len(s.samples) >= 10:
        cmp_ = compare_with_simulation(s, model)
        for k, v in cmp_["signals"].items():
            console.print(f"{k}: RMSE {v['rmse']:.4g} rad, max {v['max_abs']:.4g} rad")
        if "measured_lost_motion" in cmp_:
            console.print(f"lost motion measured {cmp_['measured_lost_motion']:.4g} rad, "
                          f"predicted {cmp_['predicted_lost_motion']:.4g} rad")
    if csv_out:
        s.write_csv(csv_out)
    raise typer.Exit(0 if s.status == "completed" else 1)


@challenge_app.command("run")
@guard
def challenge_run(config_file: Path, output: Annotated[Path | None, typer.Option(
        "--output", "-o")] = None) -> None:
    """Find the cheapest tolerance specification meeting the requirements (YAML)."""
    from motionproof.challenge.engine import Challenge, ChallengeConfig, comparison

    model, raw = _yaml_with_model(config_file)
    cfg = ChallengeConfig.model_validate(raw)
    with console.status("searching") as status:
        res = Challenge(model, cfg).run(progress=lambda p: status.update(
            f"{p['done']} candidates, best feasible cost {p['best_cost']}"))
    console.print(res["objective"])
    console.print(f"{res['search']['candidates']} candidates, "
                  f"{res['search']['scenario_evaluations']} scenario evaluations "
                  f"({res['search']['fidelity']} search)")
    table = Table("candidate", "cost", "pass", "lower bound", "feasible")
    for c in sorted(res["candidates"], key=lambda c: c["cost"])[:15]:
        table.add_row(c["id"], f"{c['cost']:.4g}", f"{c['pass_fraction']:.1%}",
                      f"{c['lower_bound']:.3f}", "yes" if c["feasible"] else "no")
    console.print(table)
    console.print(f"cost axis: {res['cost_label']}")
    if res["chosen"]:
        cmp_ = comparison(res, model)
        v = cmp_["verified"]
        console.print(f"[green]chosen {res['chosen']}[/green], verified at Level 2 on fresh "
                      f"scenarios: pass {v['proposed']['pass_fraction']:.1%} (lower bound "
                      f"{v['proposed']['lower_bound']:.3f}) vs original "
                      f"{v['original']['pass_fraction']:.1%}")
        for t in cmp_["tolerances"]:
            console.print(f"  {t['tolerance']}: {[round(x, 6) for x in t['original_limits']]} -> "
                          f"{[round(x, 6) for x in t['proposed_limits']]} {t['unit']} "
                          f"(scale {t['scale']:.3f}, shift {t['shift']:+.4g})")
    for n in res["notes"]:
        console.print(f"[yellow]{n}[/yellow]")
    _dump(res, output)
    raise typer.Exit(0 if res["chosen"] else 1)


@benchmark_app.command("list")
def benchmark_list() -> None:
    """List the benchmarks."""
    from motionproof.benchmarks.suite import BENCHMARKS

    for k, (name, _) in BENCHMARKS.items():
        console.print(f"{k}  {name}")


@benchmark_app.command("run")
@guard
def benchmark_run(names: Annotated[list[str] | None, typer.Argument()] = None,
                  write: Annotated[Path | None, typer.Option(
                      help="Write the Markdown results file (e.g. BENCHMARK_RESULTS.md)")]
                  = None) -> None:
    """Run all benchmarks, or the named ones."""
    from motionproof.benchmarks.suite import run, write_markdown

    results = run(names or None)
    for r in results:
        colour = {"PASS": "green", "FAIL": "red", "ERROR": "red"}.get(r["status"], "yellow")
        n = len(r["checks"])
        console.print(f"[{colour}]{r['status']:8}[/] {r['id']} {r['title']} "
                      f"({sum(c['passed'] for c in r['checks'])}/{n}, {r['seconds']} s)")
        for c in r["checks"]:
            if not c["passed"]:
                console.print(f"         FAIL {c['quantity']}: expected {c['expected']}, "
                              f"actual {c['actual']}")
    if write:
        write_markdown(results, write)
        console.print(f"written {write}")
    raise typer.Exit(0 if all(r["status"] in ("PASS", "NOT RUN") for r in results) else 1)


@hardware_app.command("analyse")
@guard
def hardware_analyse(session_csv: Path, test_file: Annotated[Path, typer.Option(
        "--test", help="YAML with the 'test' block that was run")],
        motor_counts_per_rev: Annotated[float | None, typer.Option(
            help="Raw input counts per motor revolution (200 x microsteps)")] = None,
        nominal_ratio: Annotated[float | None, typer.Option()] = None,
        flank: Annotated[str, typer.Option(
            help="arrival (no net load) or load (one-sided load holds one flank)")] = "arrival",
        output: Annotated[Path | None, typer.Option("--output", "-o")] = None) -> None:
    """Model-independent analysis of a recorded session: lost motion, error, ratio."""
    if flank not in ("arrival", "load"):
        fail("--flank must be 'arrival' or 'load'")
    from motionproof.hardware.analysis import analyse, load_session_csv
    from motionproof.hardware.device import HardwareTest

    raw = yaml.safe_load(test_file.read_text(encoding="utf-8"))
    test = HardwareTest.model_validate(raw.get("test", raw))
    res = analyse(test, load_session_csv(session_csv), motor_counts_per_rev, nominal_ratio,
                  flank)  # type: ignore[arg-type]
    console.print(f"{res['samples']} samples at {res['sample_rate_hz']:.0f} Hz, output "
                  f"resolution {res.get('output_resolution_rad', float('nan')) * 1e3:.3f} mrad")
    table = Table("point", "command rad", "output rad", "error mrad", "std mrad")
    for p in res["settle_points"]:
        if "output" in p:
            table.add_row(p["label"], f"{p['command']:.5f}", f"{p['output']:.5f}",
                          f"{p['error'] * 1e3:+.3f}", f"{p['output_std'] * 1e3:.3f}")
    console.print(table)
    if "lost_motion" in res:
        console.print(f"lost motion {res['lost_motion'] * 1e3:.3f} mrad "
                      f"({res['lost_motion_note']})")
    for k, v in res.get("repeatability", {}).items():
        console.print(f"repeatability at {k}: range {v['range'] * 1e3:.3f} mrad over {v['n']}")
    if "measured_ratio" in res:
        console.print(f"measured ratio {res['measured_ratio']:.4f}"
                      + (f" ({100 * res['ratio_error']:+.2f} % vs nominal)"
                         if "ratio_error" in res else ""))
    if "ratio_note" in res:
        console.print(res["ratio_note"])
    _dump(res, output)


measure_app = typer.Typer(help="Measured component dimensions.", no_args_is_help=True)
app.add_typer(measure_app, name="measurements")


@measure_app.command("template")
@guard
def measurements_template(model_file: Path, parts: int = 5,
                          output: Annotated[Path, typer.Option("--output", "-o")] = Path(
                              "measurements.csv")) -> None:
    """Write an empty measurement sheet for the model's dimensional tolerances."""
    import csv as _csv

    spec = _model(model_file).spec
    tols = [t for t in spec.tolerances if t.category in ("dimensional", "geometric")
            and t.unit in ("mm", "m", "in", "um", "cm")]
    with output.open("w", newline="", encoding="utf-8") as f:
        f.write("# Fill 'value', 'unit', 'instrument' and 'resolution' for every part you "
                "measure. Leave rows you do not measure empty.\n")
        w = _csv.writer(f)
        w.writerow(["part_id", "tolerance", "value", "unit", "instrument", "resolution",
                    "date", "operator", "notes"])
        for p in range(1, parts + 1):
            for t in tols:
                w.writerow([f"P{p:02d}", t.id, "", t.unit, "", "", "", "",
                            f"{t.component}: {t.parameter}, limits {t.lower_limit:g} to "
                            f"{t.upper_limit:g}"])
    console.print(f"{len(tols)} tolerances x {parts} parts written to {output}")


@measure_app.command("summary")
@guard
def measurements_summary(model_file: Path, data: Path) -> None:
    """Statistics, capability and resolution checks of measured dimensions."""
    from motionproof.manufacturing import measurements as M

    spec = _model(model_file).spec
    s = M.summary(M.load(data, spec), spec)
    table = Table("tolerance", "parts", "mean", "std", "min", "max", "out of spec", "Cp", "Cpk")
    for k, v in s["tolerances"].items():
        table.add_row(k, str(v["n_parts"]), f"{v['mean']:.5f}",
                      "-" if "std" not in v else f"{v['std']:.4g}", f"{v['min']:.5f}",
                      f"{v['max']:.5f}", str(v["out_of_spec"]),
                      f"{v['cp']:.2f}" if "cp" in v else "-",
                      f"{v['cpk']:.2f}" if "cpk" in v else "-")
    console.print(f"{s['parts']} measured parts")
    console.print(table)
    for k, v in s["tolerances"].items():
        for w in v["warnings"]:
            console.print(f"[yellow]{k}: {w}[/yellow]")


@measure_app.command("apply")
@guard
def measurements_apply(model_file: Path, data: Path,
                       output: Annotated[Path, typer.Option("--output", "-o")],
                       mode: str = "normal") -> None:
    """Write a NEW model file whose measured tolerances use distributions from the data."""
    from motionproof.manufacturing import measurements as M

    if mode not in ("normal", "empirical"):
        fail("--mode must be normal or empirical")
    model = _model(model_file)
    if output.resolve().parent != model.directory.resolve():
        fail("write the new model file next to the original so its geometry paths resolve")
    if output.resolve() == (model.directory / "model.yaml").resolve() or \
            output.resolve() == model_file.resolve():
        fail("refusing to overwrite the original model; choose another file name")
    spec = M.apply(model.spec, M.load(data, model.spec), data.name, mode)  # type: ignore[arg-type]
    output.write_text(f"# Derived from {model_file.name} with measurements from {data.name}\n"
                      + yaml.safe_dump(spec.model_dump(mode="json", by_alias=True,
                                                       exclude_none=True), sort_keys=False),
                      encoding="utf-8")
    console.print(f"written {output}")


@measure_app.command("evaluate")
@guard
def measurements_evaluate(data: Path, experiment_file: Annotated[Path, typer.Option(
        "--experiment", help="experiment YAML (model, task, constraints)")]) -> None:
    """Simulate every physically measured part with the experiment's task and constraints."""
    from motionproof.experiments.runner import ExperimentConfig, evaluate_scenario
    from motionproof.manufacturing import measurements as M

    model, raw = _yaml_with_model(experiment_file)
    cfg = ExperimentConfig.model_validate(raw)
    parts = M.part_rows(M.load(data, model.spec), model.spec)
    payload = cfg.task.payload_mass
    table = Table("part", "measured", "result", *[c.name for c in cfg.constraints])
    failed = 0
    for pid, p in parts.items():
        res = evaluate_scenario(model, cfg, p["values"] | {"op.payload_mass": payload})
        failed += not res["passed"]
        table.add_row(pid, str(len(p["measured"])), "pass" if res["passed"] else "FAIL",
                      *[f"{res['constraints'][c.name]['value']:.5g}"
                        if c.name in res["constraints"] else "-" for c in cfg.constraints])
    console.print(table)
    unmeasured = sorted({u for p in parts.values() for u in p["unmeasured"]})
    if unmeasured:
        console.print(f"[yellow]{len(unmeasured)} tolerances were not measured and are held at "
                      f"their design value: {', '.join(unmeasured[:8])}"
                      f"{' ...' if len(unmeasured) > 8 else ''}[/yellow]")
    raise typer.Exit(1 if failed else 0)
