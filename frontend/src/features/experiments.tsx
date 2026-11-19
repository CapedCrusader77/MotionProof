import { useEffect, useState } from "react";
import { Play, Plus, Square, Trash2 } from "lucide-react";
import { api } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import { useExperiment, useModel } from "../hooks/useModel";
import { useApp } from "../stores/app";
import type { Constraint, Distribution, ExperimentConfig, Progress, Task } from "../lib/types";
import { Alert, Badge, Empty, Field, Load, NeedSelection, Num, Panel, Stat, fmt, metricLabel, metricUnit, pct } from "../components/ui";
import { TASK_LABEL, TASK_METRICS, TaskEditor, defaultTask } from "../components/TaskEditor";
import { statusBadge } from "./projects";

const STEPS = ["Model", "Manufacturing", "Operating", "Sampling", "Task", "Constraints", "Review", "Launch"];
const SAMPLING: Record<string, string> = {
  monte_carlo: "Monte Carlo — independent random draws; binomial (Wilson) confidence intervals apply.",
  latin_hypercube: "Latin hypercube — stratified; better coverage, rows are not independent. Use replicates for an interval.",
  sobol: "Scrambled Sobol sequence — low-discrepancy; use replicates for an interval.",
  boundary: "Boundary values — nominal plus each variable at its bounds. A deterministic probe, not a probability sample.",
  corners: "Worst-case corners — combinations of bounds. A deterministic probe, not a probability sample.",
};

// ---------------------------------------------------------------- builder

export function BuilderScreen() {
  const { modelId, projectId, go, notify, setExperiment } = useApp();
  const model = useModel();
  const tols = useAsync(modelId ? () => api.tolerances(modelId) : null, [modelId]);
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [task, setTask] = useState<Task | null>(null);
  const [method, setMethod] = useState("monte_carlo");
  const [samples, setSamples] = useState(200);
  const [seed, setSeed] = useState(42);
  const [replicates, setReplicates] = useState(1);
  const [payloadVar, setPayloadVar] = useState(false);
  const [payload, setPayload] = useState<[number, number]>([0, 0.5]);
  const [speedVar, setSpeedVar] = useState(false);
  const [speed, setSpeed] = useState<[number, number]>([0.8, 1.2]);
  const [constraints, setConstraints] = useState<Constraint[]>([]);
  const [probe, setProbe] = useState<{ metrics: Record<string, number>; seconds: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const driven = Object.keys(model.data?.spec.drives ?? {});
  useEffect(() => { if (driven.length && !task) setTask(defaultTask("reversal", driven[0])); }, [driven, task]);
  // one nominal run supplies the available metrics, their nominal values and a time estimate
  useEffect(() => {
    if (!modelId || !task) return;
    let live = true;
    const t0 = performance.now();
    api.runTask(modelId, task).then((r) => { if (live && r.valid) setProbe({ metrics: r.metrics, seconds: (performance.now() - t0) / 1000 }); },
      () => { if (live) setProbe(null); });
    return () => { live = false; };
  }, [modelId, JSON.stringify(task)]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!projectId) return <NeedSelection what="project" action={<button className="btn primary" onClick={() => go("projects")}>Open projects</button>} />;
  if (!modelId) return <NeedSelection what="model" action={<button className="btn primary" onClick={() => go("projects")}>Open projects</button>} />;

  const operating: Record<string, Distribution> = {};
  if (payloadVar) operating.payload_mass = { type: "uniform", low: payload[0], high: payload[1] };
  if (speedVar) operating.speed_scale = { type: "uniform", low: speed[0], high: speed[1] };
  const nTol = tols.data?.tolerances.length ?? 0;
  const dims = nTol + Object.keys(operating).length;
  const scenarios = method === "boundary" ? 2 * dims + 1 : samples * (["latin_hypercube", "sobol"].includes(method) ? replicates : 1);
  const metrics = probe ? Object.keys(probe.metrics).sort() : [];
  const problems: string[] = [];
  if (!name.trim()) problems.push("Give the experiment a name.");
  if (driven.length === 0) problems.push("The model has no driven joint: configure the mechanical model first.");
  if (nTol === 0) problems.push("The model has no tolerances: define them in Manufacturing.");
  if (!(samples >= 1 && samples <= 100000)) problems.push("Samples must be between 1 and 100,000.");
  if (payloadVar && !(payload[1] > payload[0] && payload[0] >= 0)) problems.push("Payload range must satisfy 0 ≤ low < high.");
  if (speedVar && !(speed[1] > speed[0] && speed[0] > 0)) problems.push("Speed range must satisfy 0 < low < high.");
  if (constraints.some((c) => !c.name.trim() || !Number.isFinite(c.limit))) problems.push("Every constraint needs a name and a numeric limit.");
  if (new Set(constraints.map((c) => c.name)).size !== constraints.length) problems.push("Constraint names must be unique.");
  if (constraints.length === 0) problems.push("Add at least one performance constraint.");

  const config: ExperimentConfig | null = task ? {
    name: name.trim(), task, sampling: { method, samples, seed, replicates: ["latin_hypercube", "sobol"].includes(method) ? replicates : 1 },
    operating, constraints } : null;
  const launch = async () => {
    if (!config) return;
    setBusy(true);
    try {
      const exp = await api.createExperiment(modelId, config);
      await api.runExperiment(exp.id);
      setExperiment(exp.id);
      notify("ok", `Experiment ${exp.id} started`);
      go("monitor");
    } catch (e) { notify("error", (e as Error).message); } finally { setBusy(false); }
  };
  const addConstraint = (metric: string) => {
    const [k] = metricUnit(metric);
    const base = probe?.metrics[metric] ?? 0;
    const lower = metric.startsWith("min_");
    // the limit starts at the nominal result so the engineer consciously sets the requirement
    setConstraints([...constraints, { name: metric, metric, op: lower ? ">=" : "<=", limit: Number((base).toPrecision(4)) }]);
    void k;
  };

  return (
    <div className="page">
      <div className="page-head"><h1>Experiment builder</h1><span className="sub">{model.data?.name}</span></div>
      <div className="steps" role="tablist">{STEPS.map((s, i) => (
        <button key={s} role="tab" aria-selected={step === i} className={`step ${step === i ? "active" : i < step ? "done" : ""}`} onClick={() => setStep(i)}><i>{i + 1}</i>{s}</button>))}</div>
      <div className="split two" style={{ gridTemplateColumns: "minmax(0, 1fr) 330px" }}>
        <Panel title={`Step ${step + 1} of ${STEPS.length} — ${STEPS[step]}`} foot={
          <div className="row center"><button className="btn" disabled={step === 0} onClick={() => setStep(step - 1)}>Back</button><span className="grow" />
            {step < 7 ? <button className="btn primary" onClick={() => setStep(step + 1)}>Next</button>
              : <button className="btn primary" disabled={busy || problems.length > 0} onClick={launch}><Play />Launch experiment</button>}</div>}>
          <Load state={model}>{(m) => (<>
            {step === 0 && <div className="col">
              <Field label="Experiment name"><input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Reversal robustness, baseline tolerances" /></Field>
              <dl className="kv"><dt>Model</dt><dd>{m.name}</dd><dt>Model fingerprint</dt><dd>{m.fingerprint}</dd><dt>Fidelity</dt><dd>{m.spec.fidelity}</dd>
                <dt>Driven joints</dt><dd>{driven.join(", ") || "none"}</dd><dt>Geometry</dt><dd>{m.spec.synthetic ? "synthetic reference design" : m.source_file ?? m.kind}</dd></dl>
              <Alert kind="info">The experiment stores a frozen snapshot of this model and its tolerances. Later edits do not change it.</Alert></div>}
            {step === 1 && <Load state={tols}>{(t) => t.tolerances.length === 0 ? <Empty title="No tolerances defined" action={<button className="btn" onClick={() => go("tolerances")}>Open Manufacturing</button>} /> : (
              <div className="table-wrap" style={{ maxHeight: 420 }}><table className="grid"><thead><tr><th>Tolerance</th><th className="num">Lower limit</th><th className="num">Upper limit</th><th>Unit</th><th>Distribution</th><th className="num">Mean</th><th className="num">Std</th><th>Confidence</th></tr></thead><tbody>
                {t.tolerances.map((x, i) => <tr key={x.id}><td>{x.id}</td><td className="num">{fmt(x.nominal + x.lower, 6)}</td><td className="num">{fmt(x.nominal + x.upper, 6)}</td><td>{x.unit}</td>
                  <td>{x.distribution.type.replace("_", " ")}</td><td className="num">{fmt(t.review[i]?.mean, 6)}</td><td className="num">{fmt(t.review[i]?.std, 3)}</td>
                  <td><Badge kind={x.confidence === "assumed" ? "warn" : "ok"}>{x.confidence}</Badge></td></tr>)}</tbody></table></div>)}</Load>}
            {step === 2 && <div className="col">
              <p className="muted">Operating conditions varied alongside the manufacturing tolerances. Unchecked conditions stay at the task's fixed value.</p>
              <label className="check"><input type="checkbox" checked={payloadVar} onChange={(e) => setPayloadVar(e.target.checked)} />Vary payload mass (uniform)</label>
              {payloadVar && <div className="form"><Field label="Low (kg)"><Num value={payload[0]} min={0} onChange={(v) => setPayload([v, payload[1]])} /></Field>
                <Field label="High (kg)"><Num value={payload[1]} min={0} onChange={(v) => setPayload([payload[0], v])} /></Field></div>}
              <label className="check"><input type="checkbox" checked={speedVar} onChange={(e) => setSpeedVar(e.target.checked)} />Vary motion speed scale (uniform, 1 = as defined)</label>
              {speedVar && <div className="form"><Field label="Low"><Num value={speed[0]} min={0.01} onChange={(v) => setSpeed([v, speed[1]])} /></Field>
                <Field label="High"><Num value={speed[1]} min={0.01} onChange={(v) => setSpeed([speed[0], v])} /></Field></div>}</div>}
            {step === 3 && <div className="col"><div className="form three">
              <Field label="Method"><select value={method} onChange={(e) => setMethod(e.target.value)}>{Object.keys(SAMPLING).map((k) => <option key={k} value={k}>{k.replace(/_/g, " ")}</option>)}</select></Field>
              <Field label="Samples" hint={method === "boundary" ? "Fixed by the design: 2 × variables + 1" : undefined}><Num value={samples} min={1} max={100000} step={1} disabled={method === "boundary"} onChange={setSamples} /></Field>
              <Field label="Random seed"><Num value={seed} step={1} onChange={setSeed} /></Field>
              {["latin_hypercube", "sobol"].includes(method) && <Field label="Randomised replicates" hint="≥ 2 gives a confidence interval"><Num value={replicates} min={1} max={64} step={1} onChange={setReplicates} /></Field>}
            </div><Alert kind="info">{SAMPLING[method]}</Alert></div>}
            {step === 4 && task && <div className="col"><TaskEditor task={task} joints={driven} onChange={(t) => { setTask(t); setConstraints([]); }} />
              <p className="small muted">Changing the task clears the constraints, because the available metrics differ per task.</p></div>}
            {step === 5 && <div className="col">
              <div className="row center wrap"><span className="muted">Add a constraint on:</span>
                {(task ? TASK_METRICS[task.type] : []).filter((k) => metrics.includes(k)).map((k) => <button key={k} className="btn small" onClick={() => addConstraint(k)}><Plus />{metricLabel(k)}</button>)}
                <select style={{ width: 210 }} value="" onChange={(e) => { if (e.target.value) addConstraint(e.target.value); }} aria-label="Other metric">
                  <option value="">Other metric…</option>{metrics.map((k) => <option key={k} value={k}>{metricLabel(k)}</option>)}</select></div>
              {constraints.length === 0 ? <Empty title="No constraints">A constraint turns a measured quantity into a pass/fail requirement. Each new limit starts at the nominal result; set it to your actual requirement.</Empty> : (
                <table className="grid"><thead><tr><th>Name</th><th>Metric</th><th /><th className="num">Limit (SI)</th><th className="num">Displayed as</th><th className="num">Nominal result</th><th /></tr></thead><tbody>
                  {constraints.map((c, i) => { const [k, u] = metricUnit(c.metric); const upd = (p: Partial<Constraint>) => setConstraints(constraints.map((x, j) => (j === i ? { ...x, ...p } : x)));
                    return (<tr key={i}><td><input className="input" value={c.name} onChange={(e) => upd({ name: e.target.value })} aria-label="Constraint name" /></td><td>{metricLabel(c.metric)}</td>
                      <td><select value={c.op} onChange={(e) => upd({ op: e.target.value as Constraint["op"] })} aria-label="Operator" style={{ width: 60 }}><option>{"<="}</option><option>{">="}</option></select></td>
                      <td style={{ width: 130 }}><Num value={c.limit} onChange={(v) => upd({ limit: v })} ariaLabel="Limit" /></td><td className="num">{fmt(c.limit * k)} {u}</td>
                      <td className="num">{fmt((probe?.metrics[c.metric] ?? NaN) * k)} {u}</td>
                      <td><button className="btn ghost small" onClick={() => setConstraints(constraints.filter((_, j) => j !== i))} aria-label="Remove constraint"><Trash2 /></button></td></tr>); })}
                </tbody></table>)}</div>}
            {step >= 6 && config && <div className="col">
              {problems.length > 0 ? problems.map((p, i) => <Alert key={i} kind="warn">{p}</Alert>) : <Alert kind="ok">The configuration is complete.</Alert>}
              <div className="grid2">
                <div><h3>Experiment</h3><dl className="kv"><dt>Name</dt><dd>{config.name || "–"}</dd><dt>Model</dt><dd>{m.name}</dd><dt>Fingerprint</dt><dd>{m.fingerprint}</dd><dt>Fidelity</dt><dd>{m.spec.fidelity}</dd>
                  <dt>Task</dt><dd>{TASK_LABEL[config.task.type]}</dd><dt>Payload</dt><dd>{payloadVar ? `${payload[0]}–${payload[1]} kg (varied)` : `${config.task.payload_mass ?? 0} kg`}</dd></dl></div>
                <div><h3>Sampling</h3><dl className="kv"><dt>Method</dt><dd>{method.replace(/_/g, " ")}</dd><dt>Seed</dt><dd>{seed}</dd><dt>Variables</dt><dd>{nTol} tolerances + {Object.keys(operating).length} operating</dd>
                  <dt>Scenarios</dt><dd>{scenarios}</dd><dt>Estimated time</dt><dd>{probe ? `~${fmt(scenarios * probe.seconds, 2)} s (from one measured nominal run)` : "not available"}</dd></dl></div>
              </div>
              <h3>Constraints</h3>
              <table className="grid"><tbody>{config.constraints.map((c) => { const [k, u] = metricUnit(c.metric); return <tr key={c.name}><td>{c.name}</td><td>{metricLabel(c.metric)} {c.op} {fmt(c.limit * k)} {u}</td></tr>; })}</tbody></table>
              {m.spec.tolerances.some((t) => t.confidence === "assumed") && <Alert kind="warn">Some tolerances are assumed values. Results are conditional on those assumptions.</Alert>}
            </div>}
          </>)}</Load>
        </Panel>
        <Panel title="Configuration summary">
          <div className="grid2"><Stat label="Scenarios" value={Number.isFinite(scenarios) ? scenarios : "–"} /><Stat label="Variables" value={dims} />
            <Stat label="Seed" value={seed} /><Stat label="Constraints" value={constraints.length} /></div>
          <dl className="kv" style={{ marginTop: 8 }}><dt>Sampling</dt><dd>{method.replace(/_/g, " ")}</dd><dt>Task</dt><dd>{task ? TASK_LABEL[task.type] : "–"}</dd>
            <dt>Time per scenario</dt><dd>{probe ? `${fmt(probe.seconds, 2)} s (measured)` : "–"}</dd></dl>
          {problems.length > 0 && <div className="col" style={{ marginTop: 10, gap: 5 }}><h3>To complete</h3>{problems.map((p, i) => <div key={i} className="small muted">• {p}</div>)}</div>}
        </Panel>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- monitor

export function MonitorScreen() {
  const { experimentId, go, notify, projectId, setExperiment, setModel } = useApp();
  const exp = useExperiment();
  const list = useAsync(projectId ? () => api.experiments(projectId) : null, [projectId, experimentId]);
  const [p, setP] = useState<Progress | null>(null);
  const [kick, setKick] = useState(0);
  useEffect(() => {
    if (!experimentId) { setP(null); return; }
    let live = true; let timer = 0;
    const poll = () => api.progress(experimentId).then((r) => {
      if (!live) return;
      setP(r);
      if (r.status === "running" || r.status === "queued") timer = window.setTimeout(poll, 600);
    }, () => { if (live) timer = window.setTimeout(poll, 2000); });
    poll();
    return () => { live = false; window.clearTimeout(timer); };
  }, [experimentId, kick]);
  const start = async () => { if (!experimentId) return; try { await api.runExperiment(experimentId); setKick((k) => k + 1); exp.reload(); } catch (e) { notify("error", (e as Error).message); } };
  const cancel = async () => { if (!experimentId) return; try { await api.cancelExperiment(experimentId); notify("info", "Cancellation requested; the current scenario finishes first"); } catch (e) { notify("error", (e as Error).message); } };
  const running = p?.status === "running" || p?.status === "queued";
  const pr = p?.progress ?? {};
  const done = p?.done ?? 0, total = p?.total ?? 0;
  const elapsed = p?.job?.elapsed ?? 0;
  const rate = running && elapsed > 0 && typeof pr.done === "number" ? (pr.done as number) / elapsed : null;

  return (
    <div className="page">
      <div className="page-head"><h1>Experiment monitor</h1><span className="sub">{exp.data?.name}</span><span className="spacer" />
        <button className="btn" onClick={() => go("builder")}><Plus />New experiment</button></div>
      <div className="split two" style={{ gridTemplateColumns: "320px minmax(0, 1fr)" }}>
        <Panel title="Experiments in this project" flush>
          <Load state={list}>{(rows) => rows.length === 0 ? <Empty title="No experiments" action={<button className="btn primary" onClick={() => go("builder")}>Build an experiment</button>} /> : (
            <div className="list">{rows.map((e) => (
              <button key={e.id} className={`list-item ${e.id === experimentId ? "selected" : ""}`} onClick={() => { setExperiment(e.id); setModel(e.model_id); }}>
                <span className="name">{e.name}<br /><span className="faint small">{e.id}</span></span>{statusBadge(e.id === experimentId && p ? p.status : e.status)}</button>))}</div>)}</Load>
        </Panel>
        {!experimentId ? <Panel><Empty title="No experiment selected">Select an experiment or build a new one.</Empty></Panel> : (
          <div className="col">
            <Panel title="Execution" actions={<>
              {running ? <button className="btn danger small" onClick={cancel}><Square />Cancel</button>
                : done < total ? <button className="btn primary small" onClick={start}><Play />{done > 0 ? "Resume" : "Run"}</button> : null}
              {done > 0 && !running && <button className="btn small" onClick={() => go("robustness")}>Open analysis</button>}</>}>
              <div className="row center" style={{ marginBottom: 8 }}>{p ? statusBadge(p.status) : null}
                <span className="mono">{done} / {total} scenarios</span><span className="grow" />
                {running && typeof pr.current === "string" && <span className="muted">current {pr.current}</span>}</div>
              <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={done}><div style={{ width: total ? `${(100 * done) / total}%` : "0%" }} /></div>
              <div className="grid4" style={{ marginTop: 8 }}>
                <Stat label="Passed" value={typeof pr.passed === "number" ? pr.passed : exp.data?.summary?.scenarios.passed ?? "–"} tone="pos" />
                <Stat label="Failed" value={typeof pr.failed === "number" ? pr.failed : exp.data?.summary?.scenarios.failed ?? "–"} tone="neg" />
                <Stat label="Invalid simulations" value={typeof pr.invalid === "number" ? pr.invalid : exp.data?.summary?.scenarios.invalid ?? "–"} />
                <Stat label="Elapsed" value={elapsed ? `${fmt(elapsed, 3)} s` : "–"} sub={rate ? `${fmt(rate, 3)} scenarios/s · ~${fmt((total - done) / rate, 2)} s left` : undefined} />
              </div>
              {p?.job?.error && <Alert kind="bad">The run failed: {p.job.error}</Alert>}
              {p?.status === "cancelled" && <Alert kind="info">Cancelled after {done} scenarios. Completed scenarios are stored; Resume continues from scenario {done + 1}.</Alert>}
              <p className="small faint" style={{ marginTop: 8 }}>Progress is read from the backend job and the stored results file. One worker runs at a time.</p>
            </Panel>
            <Load state={exp}>{(e) => (
              <Panel title="Configuration snapshot (immutable)">
                <div className="grid2">
                  <dl className="kv"><dt>Model</dt><dd>{e.manifest.model.name}</dd><dt>Fingerprint</dt><dd>{e.manifest.model.fingerprint}</dd><dt>Fidelity</dt><dd>{e.manifest.model.fidelity}</dd>
                    <dt>Created</dt><dd>{new Date(e.manifest.created).toLocaleString()}</dd><dt>MuJoCo</dt><dd>{e.manifest.versions.mujoco}</dd></dl>
                  <dl className="kv"><dt>Sampling</dt><dd>{e.manifest.config.sampling.method}</dd><dt>Seed</dt><dd>{e.manifest.config.sampling.seed}</dd><dt>Replicates</dt><dd>{e.manifest.config.sampling.replicates}</dd>
                    <dt>Variables</dt><dd>{e.manifest.design.names.length}</dd><dt>Task</dt><dd>{TASK_LABEL[e.manifest.config.task.type]}</dd></dl>
                </div>
                {e.manifest.model.synthetic && <Alert kind="warn">Synthetic reference design — results describe the generated model, not physical hardware.</Alert>}
                {e.summary && <p className="small muted" style={{ marginTop: 8 }}>Last result: {pct(e.summary.all_constraints.pass_fraction)} of valid scenarios satisfy all constraints.</p>}
              </Panel>)}</Load>
          </div>)}
      </div>
    </div>
  );
}
