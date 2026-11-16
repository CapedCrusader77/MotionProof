import { Fragment, useState } from "react";
import { Trash2 } from "lucide-react";
import { api } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import { useApp } from "../stores/app";
import { Alert, Badge, Empty, Field, Load, Modal, Panel, pct } from "../components/ui";
import type { ExperimentRow, ProjectDetail } from "../lib/types";

const date = (iso: string) => new Date(iso).toLocaleString();
const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });

/** Passed / failed / invalid shares of an experiment's scenarios, drawn to scale. */
function OutcomeBar({ e }: { e: ExperimentRow }) {
  const s = e.summary?.scenarios;
  if (!s || s.total === 0) return <span className="faint">–</span>;
  const w = (n: number) => `${(100 * n) / s.total}%`;
  return (
    <span className="outcome" role="img" aria-label={`${s.passed} passed, ${s.failed} failed, ${s.invalid} invalid of ${s.total}`}
      title={`${s.passed} passed · ${s.failed} failed · ${s.invalid} invalid · ${s.total - s.completed} not run`}>
      <span className="ok" style={{ width: w(s.passed) }} /><span className="bad" style={{ width: w(s.failed) }} />
      <span className="inv" style={{ width: w(s.invalid) }} />
    </span>
  );
}

/** Where the project stands in the workflow, from its real models and experiments. */
function nextStep(p: ProjectDetail): { text: string; action: string; route: "import" | "builder" | "monitor" | "robustness"; exp?: ExperimentRow } {
  if (p.models.length === 0) return { text: "No mechanical model yet. Import CAD or add the labelled reference design.", action: "Import CAD", route: "import" };
  const exps = [...p.experiments].sort((a, b) => b.created.localeCompare(a.created));
  const running = exps.find((e) => e.status === "running" || e.status === "queued");
  if (running) return { text: `${running.name} is running.`, action: "Open live monitor", route: "monitor", exp: running };
  const done = exps.find((e) => e.summary);
  if (done) return { text: `Latest results: ${done.name}, ${pct(done.summary!.all_constraints.pass_fraction)} of valid scenarios pass every constraint.`,
    action: "Review robustness", route: "robustness", exp: done };
  return { text: "A model is ready. Define the task, sampling and constraints of a first experiment.", action: "Build experiment", route: "builder" };
}

export function statusBadge(status: string) {
  const kind = status === "completed" ? "ok" : status === "failed" ? "bad" : status === "running" ? "info" : "plain";
  return <Badge kind={kind}>{status}</Badge>;
}

/** Plain status text; only a failed run is coloured. */
const statusText = (status: string) => <span className={status === "failed" ? "neg" : status === "running" ? "" : "muted"}>{status}</span>;

export function ProjectsScreen() {
  const { projectId, setProject, setModel, setExperiment, go, notify } = useApp();
  const projects = useAsync(() => api.projects(), []);
  const detail = useAsync(projectId ? () => api.project(projectId) : null, [projectId]);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [toDelete, setToDelete] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState("");

  const create = async () => {
    setBusy(true);
    try {
      const p = await api.createProject(name.trim(), description.trim());
      setProject(p.id);
      setCreating(false); setName(""); setDescription("");
      projects.reload();
      notify("ok", `Project ${p.name} created`);
    } catch (e) { notify("error", (e as Error).message); } finally { setBusy(false); }
  };
  const addReference = async () => {
    if (!projectId) return;
    setBusy(true);
    try {
      const m = await api.createReference(projectId);
      setModel(m.id);
      detail.reload(); projects.reload();
      notify("ok", "Synthetic reference model added");
      go("workbench");
    } catch (e) { notify("error", (e as Error).message); } finally { setBusy(false); }
  };
  const remove = async () => {
    if (!toDelete) return;
    try {
      await api.deleteProject(toDelete);
      if (toDelete === projectId) setProject(null);
      projects.reload();
      notify("ok", "Project deleted");
    } catch (e) { notify("error", (e as Error).message); }
    setToDelete(null);
  };

  return (
    <div className="page">
      <div className="page-head">
        <h1>Projects</h1><span className="sub">Engineering projects in this workspace</span><span className="spacer" />
        <button className="btn primary" onClick={() => setCreating(true)}>New project</button>
      </div>
      <div className="row project-layout" style={{ flex: 1, alignItems: "stretch" }}>
        <Panel title="All projects" flush style={{ width: 300, flex: "none", alignSelf: "flex-start", maxHeight: "100%" }}>
          {(projects.data?.length ?? 0) > 3 && <div style={{ padding: 6, borderBottom: "1px solid var(--border)" }}>
            <input className="input" placeholder="Filter projects" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter projects" /></div>}
          <Load state={projects}>{(all) => { const list = all.filter((x) => `${x.name} ${x.id}`.toLowerCase().includes(filter.toLowerCase())); return list.length === 0 && all.length > 0 ? <p className="muted small" style={{ padding: 10 }}>No project matches “{filter}”.</p> : list.length === 0 ? (
            <Empty title="No projects yet" action={<button className="btn primary" onClick={() => setCreating(true)}>Create the first project</button>}>
              A project groups mechanical models, tolerance specifications and experiments.</Empty>
          ) : (
            <div className="list">{list.map((p) => (
              <button key={p.id} className={`list-item ${p.id === projectId ? "selected" : ""}`} onClick={() => setProject(p.id)}>
                <span className="name"><b>{p.name}</b><br /><span className="faint small">{String(p.models)} {Number(p.models) === 1 ? "model" : "models"} · {String(p.experiments)} {Number(p.experiments) === 1 ? "experiment" : "experiments"} · {day(p.created)}</span></span>
              </button>))}</div>
          ); }}</Load>
        </Panel>
        <div className="col grow">
          {!projectId ? <Panel><Empty title="Select a project">Choose a project on the left or create a new one.</Empty></Panel> : (
            <Load state={detail}>{(p) => (
              <>
                <Panel title={p.name} actions={<>
                  <button className="btn" onClick={() => go("import")}>Import CAD</button>
                  <button className="btn" disabled={busy} onClick={addReference} title="Adds the synthetic NEMA 17 planetary-joint design generated by MotionProof">Add reference design</button>
                  <button className="btn" disabled={p.models.length === 0} onClick={() => go("builder")}>New experiment</button>
                  <button className="btn ghost danger" onClick={() => setToDelete(p.id)} aria-label="Delete project"><Trash2 /></button></>} flush>
                  {(() => {
                    const done = p.experiments.filter((e) => e.summary);
                    const scen = done.reduce((n, e) => n + e.summary!.scenarios.completed, 0);
                    const failed = done.reduce((n, e) => n + e.summary!.scenarios.failed, 0);
                    const synth = p.models.filter((m) => m.synthetic).length;
                    const step = nextStep(p);
                    return (<>
                      <p className="muted" style={{ padding: "8px 10px 0" }}>{p.description || "No description."} Created {date(p.created)}.</p>
                      <p className="proj-facts">
                        <button className="fact" disabled={!p.models.length} onClick={() => { setModel(p.models[0].id); go("workbench"); }} title="Open the assembly workbench">
                          <b>{p.models.length}</b> {p.models.length === 1 ? "model" : "models"}{synth ? ` (${synth} synthetic)` : ""}</button>
                        <span><b>{p.experiments.length}</b> {p.experiments.length === 1 ? "experiment" : "experiments"}, {done.length} with results</span>
                        <span><b>{scen.toLocaleString()}</b> scenarios simulated</span>
                        <button className="fact" disabled={!failed} title="Investigate the failed scenarios" onClick={() => {
                          const e = [...p.experiments].filter((x) => x.summary?.scenarios.failed).sort((x, y) => y.created.localeCompare(x.created))[0];
                          if (e) { setExperiment(e.id); setModel(e.model_id); go("robustness"); } }}>
                          <b className={failed ? "neg" : ""}>{failed.toLocaleString()}</b> failed{scen ? ` (${pct(failed / scen)})` : ""}</button>
                      </p>
                      <div className="next-step"><span className="grow">{step.text}</span>
                        <button className="btn primary small" disabled={step.route === "builder" && p.models.length === 0}
                          onClick={() => { if (step.exp) { setExperiment(step.exp.id); setModel(step.exp.model_id); } go(step.route); }}>{step.action}</button></div>
                    </>);
                  })()}
                </Panel>
                <ExperimentsTable p={p} open={(e) => { setExperiment(e.id); setModel(e.model_id); go(e.summary ? "robustness" : "monitor"); }}
                  go={(e, route) => { setExperiment(e.id); setModel(e.model_id); go(route); }} />
                <div className="grid2">
                  <Panel title="Mechanical models" flush>
                    {p.models.length === 0 ? <Empty title="No models">Import a STEP, STL, OBJ, URDF or MJCF file, or add the labelled reference design to explore the workflow.</Empty> : (
                      <table className="grid"><thead><tr><th>Model</th><th>Source</th><th>Created</th></tr></thead><tbody>
                        {p.models.map((m) => (
                          <tr key={m.id} className="click" onClick={() => { setModel(m.id); go("workbench"); }}>
                            <td>{m.name}<br /><span className="faint small">{m.id} · {p.experiments.filter((e) => e.model_id === m.id).length} experiments</span></td>
                            <td className="muted" title={m.synthetic ? "Generated reference geometry, not user hardware" : undefined}>{m.synthetic ? "synthetic" : m.kind}</td>
                            <td className="muted">{day(m.created)}</td></tr>))}
                      </tbody></table>)}
                  </Panel>
                  <Panel title="Recent failures" flush>
                  {(() => {
                    const rows = p.experiments.filter((e) => e.summary && Object.keys(e.summary.failure_categories).length > 0);
                    if (rows.length === 0) return <Empty title="No recorded failures">Failure categories of completed experiments appear here.</Empty>;
                    return (
                      <table className="grid"><thead><tr><th>Experiment</th><th>Failed scenarios by category</th></tr></thead><tbody>
                        {rows.map((e) => (
                          <tr key={e.id} className="click" onClick={() => { setExperiment(e.id); setModel(e.model_id); go("robustness"); }}>
                            <td>{e.name}</td>
                            <td>{Object.entries(e.summary!.failure_categories).map(([k, v]) =>
                              `${k.replace(/_/g, " ")}: ${v} (${pct(Number(v) / Math.max(e.summary!.scenarios.completed, 1))})`).join(", ")}</td></tr>))}
                      </tbody></table>);
                  })()}
                </Panel>
                </div>
              </>
            )}</Load>
          )}
        </div>
      </div>
      {creating && (
        <Modal title="New project" onClose={() => setCreating(false)} foot={<>
          <button className="btn" onClick={() => setCreating(false)}>Cancel</button>
          <button className="btn primary" disabled={busy || name.trim().length === 0} onClick={create}>Create</button></>}>
          <div className="col">
            <Field label="Name"><input className="input" autoFocus value={name} maxLength={120} onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && name.trim()) void create(); }} /></Field>
            <Field label="Description (optional)"><textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
          </div>
        </Modal>
      )}
      {toDelete && (
        <Modal title="Delete project" onClose={() => setToDelete(null)} foot={<>
          <button className="btn" onClick={() => setToDelete(null)}>Keep project</button>
          <button className="btn danger" onClick={remove}>Delete permanently</button></>}>
          <Alert kind="bad">This permanently deletes project {toDelete} with all of its models, original CAD copies, experiments and reports. This cannot be undone.</Alert>
        </Modal>
      )}
    </div>
  );
}

type SortKey = "created" | "name" | "scenarios" | "pass" | "failed";

/** Experiments of a project: sortable, each row expands to its scenario breakdown. */
function ExperimentsTable({ p, open, go }: { p: ProjectDetail; open: (e: ExperimentRow) => void;
  go: (e: ExperimentRow, route: "robustness" | "sensitivity" | "investigate" | "monitor" | "reports") => void }) {
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "created", desc: true });
  const [expanded, setExpanded] = useState<string | null>(null);
  const val = (e: ExperimentRow): number | string => {
    switch (sort.key) {
      case "name": return e.name.toLowerCase();
      case "scenarios": return e.summary?.scenarios.completed ?? -1;
      case "pass": return e.summary?.all_constraints.pass_fraction ?? -1;
      case "failed": return e.summary?.scenarios.failed ?? -1;
      default: return e.created;
    }
  };
  const rows = [...p.experiments].sort((a, b) => {
    const x = val(a), y = val(b);
    const c = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y));
    return sort.desc ? -c : c;
  });
  const th = (key: SortKey, label: string, num = false, title?: string) => (
    <th className={`${num ? "num " : ""}sortable`} title={title} aria-sort={sort.key === key ? (sort.desc ? "descending" : "ascending") : "none"}>
      <button onClick={() => setSort({ key, desc: sort.key === key ? !sort.desc : key !== "name" })}>
        {label}<span className="sort-mark" aria-hidden="true">{sort.key === key ? (sort.desc ? "\u25BE" : "\u25B4") : ""}</span></button></th>);
  return (
    <Panel title={`Experiments (${p.experiments.length})`} flush>
      {p.experiments.length === 0 ? <Empty title="No experiments">Build an experiment once a model has tolerances and a drive train.</Empty> : (
        <table className="grid exp-table"><thead><tr><th style={{ width: 28 }} />{th("name", "Experiment")}<th>Status</th>{th("scenarios", "Scenarios", true)}<th>Outcome</th>
          {th("pass", "Pass", true, "Share of valid scenarios passing every constraint, with its 95 % interval")}{th("failed", "Failed", true)}<th /></tr></thead>
          <tbody>{rows.map((e) => {
            const s = e.summary?.scenarios;
            const isOpen = expanded === e.id;
            return (<Fragment key={e.id}>
              <tr className={`click exp-row ${isOpen ? "open" : ""}`} tabIndex={0} onClick={() => open(e)}
                onKeyDown={(k) => { if (k.key === "Enter") open(e); if (k.key === " " || k.key === "ArrowRight" || k.key === "ArrowLeft") { k.preventDefault(); setExpanded(isOpen ? null : e.id); } }}>
                <td><button className="expander" aria-expanded={isOpen} aria-label={isOpen ? "Hide details" : "Show details"}
                  onClick={(k) => { k.stopPropagation(); setExpanded(isOpen ? null : e.id); }}>{isOpen ? "\u2212" : "+"}</button></td>
                <td>{e.name}<br /><span className="faint small">{e.id} · {day(e.created)}</span></td><td>{statusText(e.status)}</td>
                <td className="num">{s?.completed ?? "–"}</td><td><OutcomeBar e={e} /></td>
                <td className="num">{pct(e.summary?.all_constraints.pass_fraction)}
                  {e.summary?.all_constraints.interval && <><br /><span className="faint small" title={e.summary.all_constraints.interval_method}>
                    {pct(e.summary.all_constraints.interval[0])}–{pct(e.summary.all_constraints.interval[1])}</span></>}</td>
                <td className="num">{s ? <span className={s.failed ? "neg" : ""}>{s.failed}</span> : "–"}</td>
                <td className="open-hint">Open</td></tr>
              {isOpen && <tr className="exp-detail"><td /><td colSpan={7}>
                {!s ? <span className="muted">No results yet. The run is {e.status}.</span> : (
                  <div className="exp-detail-grid">
                    <dl className="kv">
                      <dt>Scenarios</dt><dd>{s.completed} of {s.total}</dd><dt>Passed</dt><dd>{s.passed}</dd>
                      <dt>Failed</dt><dd className={s.failed ? "neg" : ""}>{s.failed}</dd><dt>Invalid simulations</dt><dd>{s.invalid}</dd>
                      <dt>Out-of-spec dimensions</dt><dd>{s.out_of_spec}</dd>
                    </dl>
                    <div>
                      <div className="small muted" style={{ marginBottom: 4 }}>Failed scenarios by category</div>
                      {Object.keys(e.summary!.failure_categories).length === 0 ? <span className="small">None.</span> :
                        Object.entries(e.summary!.failure_categories).sort((x, y) => Number(y[1]) - Number(x[1])).map(([k, v]) => (
                          <div key={k} className="cat-row"><span>{k.replace(/_/g, " ")}</span>
                            <span className="cat-bar"><span style={{ width: `${(100 * Number(v)) / Math.max(s.failed, 1)}%` }} /></span>
                            <span className="mono">{String(v)}</span></div>))}
                    </div>
                    <div className="exp-actions">
                      <button className="btn small" onClick={() => go(e, "robustness")}>Robustness</button>
                      <button className="btn small" onClick={() => go(e, "sensitivity")}>Sensitivity</button>
                      <button className="btn small" disabled={!s.failed} onClick={() => go(e, "investigate")}>Investigate a failure</button>
                      <button className="btn small" onClick={() => go(e, "reports")}>Report</button>
                    </div>
                  </div>)}
              </td></tr>}
            </Fragment>);
          })}</tbody></table>)}
    </Panel>
  );
}
