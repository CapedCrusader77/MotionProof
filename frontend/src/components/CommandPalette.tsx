import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../lib/api";
import type { ExperimentRow, ModelRow, Project } from "../lib/types";
import { useApp, type Route } from "../stores/app";

interface Command { id: string; label: string; hint: string; run: () => void }

/** Global command palette (Ctrl+K / Cmd+K). Every command navigates or acts for real. */
export function CommandPalette() {
  const { go, setProject, setModel, setExperiment, projectId, toggleTheme } = useApp();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const [data, setData] = useState<{ projects: Project[]; models: ModelRow[]; experiments: ExperimentRow[] }>({ projects: [], models: [], experiments: [] });
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setOpen((o) => !o); }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  useEffect(() => {
    if (!open) return;
    setQ(""); setSel(0);
    window.setTimeout(() => input.current?.focus(), 0);
    Promise.all([api.projects(), projectId ? api.models(projectId) : Promise.resolve([]), projectId ? api.experiments(projectId) : Promise.resolve([])])
      .then(([projects, models, experiments]) => setData({ projects, models, experiments }), () => undefined);
  }, [open, projectId]);
  const commands = useMemo<Command[]>(() => {
    const nav = (label: string, route: Route, hint = "go to"): Command => ({ id: `nav-${route}-${label}`, label, hint, run: () => go(route) });
    return [
      nav("Import CAD", "import", "action"), nav("Import point cloud", "asbuilt", "action"), nav("Create tolerance", "tolerances", "action"),
      nav("Create experiment", "builder", "action"), nav("Run adaptive experiment", "adaptive", "action"), nav("Inspect failure", "investigate", "action"),
      nav("Compare models (design comparison)", "comparison", "action"), nav("Open reliability map", "workspace", "action"),
      nav("Open hardware monitor", "hardware", "action"), nav("Generate report", "reports", "action"), nav("Launch Engineering Challenge", "challenge", "action"),
      nav("Run benchmarks", "benchmarks", "action"), nav("External validation", "external", "action"), nav("Model trust panel", "trust", "action"), nav("Process batches", "process", "action"),
      nav("Lifetime degradation", "degradation", "action"), nav("Multi-fidelity comparison", "fidelity", "action"),
      nav("Assembly workbench", "workbench"), nav("Virtual assemblies", "virtual"), nav("Mechanical model", "mechanics"), nav("Robustness", "robustness"),
      nav("Sensitivity", "sensitivity"), nav("Worst case", "worstcase"), nav("Tolerance optimisation", "optimisation"), nav("Calibration", "calibration"),
      nav("Live monitor", "monitor"), nav("Settings", "settings"),
      { id: "theme", label: "Toggle theme", hint: "action", run: toggleTheme },
      ...data.projects.map((p) => ({ id: `p-${p.id}`, label: `Open project ${p.name}`, hint: p.id, run: () => { setProject(p.id); go("projects"); } })),
      ...data.models.map((m) => ({ id: `m-${m.id}`, label: `Open model ${m.name}`, hint: m.id, run: () => { setModel(m.id); go("workbench"); } })),
      ...data.experiments.map((e) => ({ id: `e-${e.id}`, label: `Open experiment ${e.name}`, hint: e.id, run: () => { setExperiment(e.id); setModel(e.model_id); go("robustness"); } })),
      ...data.experiments.map((e) => ({ id: `r-${e.id}`, label: `Run experiment ${e.name}`, hint: e.id, run: () => {
        setExperiment(e.id); setModel(e.model_id); void api.runExperiment(e.id).then(() => go("monitor"), () => go("monitor")); } })),
    ];
  }, [data, go, setProject, setModel, setExperiment, toggleTheme]);
  const shown = commands.filter((c) => `${c.label} ${c.hint}`.toLowerCase().includes(q.toLowerCase())).slice(0, 12);
  if (!open) return null;
  const pick = (c: Command | undefined) => { if (c) { setOpen(false); c.run(); } };
  return (
    <div className="modal-back" onMouseDown={(e) => { if (e.target === e.currentTarget) setOpen(false); }}>
      <div className="panel modal" role="dialog" aria-modal="true" aria-label="Command palette" style={{ alignSelf: "flex-start", marginTop: "12vh" }}>
        <input ref={input} className="input" style={{ height: 38, border: 0, borderBottom: "1px solid var(--border)", borderRadius: 0 }}
          placeholder="Type a command, project, model or experiment…" value={q} aria-label="Command"
          onChange={(e) => { setQ(e.target.value); setSel(0); }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, shown.length - 1)); }
            if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
            if (e.key === "Enter") pick(shown[sel]);
          }} />
        <div className="list" role="listbox">{shown.length === 0 ? <div className="empty">No matching command</div> : shown.map((c, i) => (
          <button key={c.id} role="option" aria-selected={i === sel} className={`list-item ${i === sel ? "selected" : ""}`} onMouseEnter={() => setSel(i)} onClick={() => pick(c)}>
            <span className="name">{c.label}</span><span className="faint small">{c.hint}</span></button>))}</div>
        <div className="panel-foot">↑ ↓ to move · Enter to run · Esc to close</div>
      </div>
    </div>
  );
}
