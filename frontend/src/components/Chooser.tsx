// Shown by any screen that needs a project, model or experiment before it can work. Instead of a
// dead end, it lists what exists in the workspace (real backend data) so one click selects it,
// and offers the labelled reference design as a quick start.
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useApp } from "../stores/app";
import type { ProjectDetail } from "../lib/types";

type What = "project" | "model" | "experiment";

const ROUTE_LABEL: Record<string, string> = {
  import: "CAD import", workbench: "Assembly workbench", features: "Features and datums", tolerances: "Tolerances",
  process: "Process batches", virtual: "Virtual assemblies", mechanics: "Mechanical model", asbuilt: "As-built inspection",
  hardware: "Hardware testing", calibration: "Calibration", builder: "Experiment builder", monitor: "Live monitor",
  adaptive: "Adaptive experiment", robustness: "Robustness", sensitivity: "Sensitivity", investigate: "Failure investigation",
  worstcase: "Worst case", workspace: "Workspace analysis", degradation: "Degradation", fidelity: "Model fidelity",
  challenge: "Engineering Challenge", optimisation: "Tolerance optimisation", comparison: "Design comparison",
  trust: "Model trust", reports: "Reports",
};

export function Chooser({ what }: { what: What }) {
  const { route, setProject, setModel, setExperiment, go, notify } = useApp();
  const [projects, setProjects] = useState<ProjectDetail[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    api.projects()
      .then((list) => Promise.all(list.map((p) => api.project(p.id))))
      .then((d) => { if (live) setProjects(d); })
      .catch((e: Error) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, []);

  const pickModel = (p: ProjectDetail, modelId: string) => { setProject(p.id); setModel(modelId); };
  const pickExperiment = (p: ProjectDetail, e: ProjectDetail["experiments"][number]) => {
    setProject(p.id); setModel(e.model_id); setExperiment(e.id);
  };
  const quickStart = async () => {
    setBusy(true);
    try {
      const target = projects?.[0] ?? await api.createProject("Sandbox", "Created from the quick start to explore the labelled reference design.");
      const m = await api.createReference(target.id);
      setProject(target.id); setModel(m.id);
      notify("ok", `Reference design added to ${target.name}`);
    } catch (e) { notify("error", (e as Error).message); } finally { setBusy(false); }
  };

  const screen = ROUTE_LABEL[route] ?? "This screen";
  const models = (projects ?? []).flatMap((p) => p.models.map((m) => ({ p, m })));
  const exps = (projects ?? []).flatMap((p) => p.experiments.map((e) => ({ p, e })))
    .sort((a, b) => b.e.created.localeCompare(a.e.created));

  return (
    <div className="page">
      <div className="chooser">
        <div className="chooser-head">
          <h1>{screen}</h1>
          <p className="muted">{screen} works on {what === "experiment" ? "an experiment's results" : `a ${what}`}. Choose one to continue.</p>
        </div>
        {error && <p className="neg small">{error}</p>}
        {!projects && !error && <p className="muted small">Reading the workspace…</p>}
        {projects && (
          <div className="chooser-body">
            {what === "project" && (projects.length === 0 ? <p className="muted">No projects yet.</p> : (
              <ul className="pick-list">{projects.map((p) => (
                <li key={p.id}><button onClick={() => setProject(p.id)}>
                  <span className="pick-name">{p.name}</span>
                  <span className="pick-meta">{p.models.length} models · {p.experiments.length} experiments</span>
                  <span className="pick-go">Use</span></button></li>))}</ul>))}
            {what === "model" && (models.length === 0 ? <p className="muted">No mechanical models in the workspace yet.</p> : (
              <ul className="pick-list">{models.map(({ p, m }) => (
                <li key={m.id}><button onClick={() => pickModel(p, m.id)}>
                  <span className="pick-name">{m.name}</span>
                  <span className="pick-meta">{p.name} · {m.synthetic ? "synthetic reference" : m.kind} · {m.id}</span>
                  <span className="pick-go">Use</span></button></li>))}</ul>))}
            {what === "experiment" && (exps.length === 0 ? <p className="muted">No experiments yet. Build one in the Experiment builder.</p> : (
              <ul className="pick-list">{exps.map(({ p, e }) => (
                <li key={e.id}><button onClick={() => pickExperiment(p, e)}>
                  <span className="pick-name">{e.name}</span>
                  <span className="pick-meta">{p.name} · {e.status}
                    {e.summary ? ` · ${e.summary.scenarios.completed} scenarios · ${e.summary.scenarios.failed} failed` : ""}</span>
                  <span className="pick-go">Use</span></button></li>))}</ul>))}
            <div className="chooser-alt">
              {what !== "experiment" && <button className="btn" disabled={busy} onClick={quickStart}
                title="Adds the synthetic NEMA 17 planetary-joint design generated by MotionProof (labelled synthetic)">
                {busy ? "Adding…" : "Start with the reference design"}</button>}
              {what === "experiment" && <button className="btn" onClick={() => go("builder")}>Open the experiment builder</button>}
              <button className="btn ghost" onClick={() => go("projects")}>Manage projects</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
