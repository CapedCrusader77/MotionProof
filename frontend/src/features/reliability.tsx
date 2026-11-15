import { useEffect, useMemo, useState } from "react";
import { Play, Search } from "lucide-react";
import { CartesianGrid, Cell, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";
import { adv, api, type AnyJson } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import { useArtifactJob } from "../hooks/useArtifactJob";
import { useExperiment, useModel } from "../hooks/useModel";
import { useApp } from "../stores/app";
import { Alert, Badge, Empty, Field, Load, NeedSelection, Num, Panel, Spinner, Stat, Tabs, fmt, metricFmt, metricLabel, metricUnit, pct, signed } from "../components/ui";
import { Lines, Points } from "../components/charts";
import { TASK_METRICS, TaskEditor, defaultTask } from "../components/TaskEditor";
import { TraceCharts } from "./mechanics";
import type { Task } from "../lib/types";

function History({ kind, modelId, onPick, current }: { kind: string; modelId: string; onPick: (id: string) => void; current: string | null }) {
  const list = useAsync(() => adv.artifacts(kind, undefined, modelId), [kind, modelId, current]);
  return (
    <Panel title="History" flush>
      <Load state={list}>{(rows) => rows.length === 0 ? <Empty title="None yet" /> : (
        <div className="list">{rows.map((r) => <button key={r.id} className={`list-item ${r.id === current ? "selected" : ""}`} onClick={() => onPick(r.id)}>
          <span className="name">{r.name}<br /><span className="faint small">{r.id} · {new Date(r.created).toLocaleString()}</span></span><Badge>{r.status}</Badge></button>)}</div>)}</Load>
    </Panel>
  );
}
const needModel = (go: (r: "projects") => void) => <NeedSelection what="model" action={<button className="btn primary" onClick={() => go("projects")}>Open projects</button>} />;

// ================================================================ adaptive

export function AdaptiveScreen() {
  const { modelId, go } = useApp();
  const model = useModel();
  const driven = Object.keys(model.data?.spec.drives ?? {});
  const [task, setTask] = useState<Task | null>(null);
  const [metric, setMetric] = useState("");
  const [op, setOp] = useState<"<=" | ">=">("<=");
  const [limit, setLimit] = useState(NaN);
  const [cfg, setCfg] = useState({ initial: 30, budget: 120, population: 5000, seed: 0 });
  const [payload, setPayload] = useState<[number, number] | null>(null);
  const job = useArtifactJob("adaptive");
  useEffect(() => { if (driven.length && !task) setTask(defaultTask("reversal", driven[0])); }, [driven, task]);
  useEffect(() => { if (task) setMetric(TASK_METRICS[task.type][0]); }, [task?.type]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!modelId) return needModel(go);
  const run = () => task && job.start(() => adv.adaptive({ model_id: modelId, ...cfg, config: {
    name: `adaptive ${metric}`, task, constraints: [{ name: metric, metric, op, limit }],
    operating: payload ? { payload_mass: { type: "uniform", low: payload[0], high: payload[1] } } : {} } }));
  const r = job.result;
  const live = job.job?.progress as AnyJson | undefined;
  return (
    <div className="page">
      <div className="page-head"><h1>Adaptive experiment</h1><span className="sub">simulations spent near the pass/fail boundary</span></div>
      <Alert kind="info">A Gaussian-process surrogate chooses which scenario to simulate next. It never replaces the simulation: simulated results and surrogate predictions are reported separately.</Alert>
      <div className="split two" style={{ gridTemplateColumns: "360px minmax(0, 1fr)" }}>
        <div className="col">
          <Panel title="Configuration" actions={<button className="btn primary small" disabled={!task || !Number.isFinite(limit) || job.busy} onClick={run}><Play />Run</button>}>
            {task && <TaskEditor task={task} joints={driven} onChange={setTask} />}
            <div className="form" style={{ marginTop: 8 }}>
              <Field label="Limit-state metric" wide><select value={metric} onChange={(e) => setMetric(e.target.value)}>{(task ? TASK_METRICS[task.type] : []).concat("min_mesh_backlash_mm").map((m) => <option key={m} value={m}>{metricLabel(m)}</option>)}</select></Field>
              <Field label="Operator"><select value={op} onChange={(e) => setOp(e.target.value as "<=" | ">=")}><option>{"<="}</option><option>{">="}</option></select></Field>
              <Field label="Limit (SI)"><Num value={limit} onChange={setLimit} /></Field>
              <Field label="Initial simulations"><Num value={cfg.initial} min={4} step={1} onChange={(v) => setCfg({ ...cfg, initial: v })} /></Field>
              <Field label="Simulation budget"><Num value={cfg.budget} min={4} step={1} onChange={(v) => setCfg({ ...cfg, budget: v })} /></Field>
              <Field label="Population"><Num value={cfg.population} min={100} step={1} onChange={(v) => setCfg({ ...cfg, population: v })} /></Field>
              <Field label="Seed"><Num value={cfg.seed} step={1} onChange={(v) => setCfg({ ...cfg, seed: v })} /></Field>
            </div>
            <label className="check" style={{ marginTop: 6 }}><input type="checkbox" checked={!!payload} onChange={(e) => setPayload(e.target.checked ? [0, 0.5] : null)} />Vary payload 0–0.5 kg</label>
          </Panel>
          <History kind="adaptive" modelId={modelId} current={job.artifactId} onPick={job.load} />
        </div>
        <div className="col">
          {job.busy && <Panel title="Running"><div className="grid4">
            <Stat label="True simulations" value={`${live?.done ?? 0} / ${live?.total ?? cfg.budget}`} />
            <Stat label="Simulated failures" value={live?.simulated_failures ?? "-"} />
            <Stat label="Surrogate PREDICTION of failure fraction" value={live?.predicted_failure_fraction == null ? "-" : fmt(live.predicted_failure_fraction, 3)} />
            <Stat label="Surrogate Q²" value={live?.leave_one_out_q2 == null ? "-" : fmt(live.leave_one_out_q2, 2)} sub={`${live?.uncertain_population_points ?? "-"} uncertain points`} /></div></Panel>}
          {!r ? (!job.busy && <Panel><Empty title="No adaptive run">Set a limit state and run.</Empty></Panel>) : (<>
            <Panel title={`Result ${r.id}`}>
              <div className="grid4">
                <Stat label="True simulations" value={r.simulations.total} sub={`${r.simulations.initial} initial · ${r.simulations.adaptive} adaptive`} />
                <Stat label="Simulated failures (confirmed)" value={r.simulations.failures_simulated} tone={r.simulations.failures_simulated ? "neg" : undefined} />
                <Stat label="Surrogate PREDICTION" value={fmt(r.surrogate.predicted_failure_fraction, 3)} sub={`failure fraction over ${r.surrogate.population} population points`} />
                <Stat label="Surrogate Q²" value={fmt(r.surrogate.leave_one_out_q2, 2)} tone={r.surrogate.leave_one_out_q2 < 0.5 ? "neg" : "pos"} sub={`${r.surrogate_inputs.length} of ${r.dimensions} inputs`} />
              </div>
              <p className="small muted" style={{ marginTop: 6 }}>Stopped: {r.stopping_reason}. {r.statement}</p>
              {r.warnings.map((w: string, i: number) => <Alert key={i} kind="warn">{w}</Alert>)}
            </Panel>
            <div className="grid2">
              <Panel title="Convergence"><Lines data={r.history.map((h: AnyJson) => ({ n: h.simulations, pf: h.predicted_failure_fraction, q2: Math.max(h.leave_one_out_q2 ?? 0, -1) }))}
                x="n" xLabel="true simulations" series={[{ key: "pf", name: "predicted failure fraction" }, { key: "q2", name: "surrogate Q²", dashed: true, color: "var(--faint)" }]} height={220} /></Panel>
              <Panel title="Simulated scenarios (observed)">
                <Points points={r.simulated.map((s: AnyJson, i: number) => ({ x: s.values[r.variables[r.surrogate_inputs[0]]], y: s.margin, ok: s.passed, mark: r.points.kind[i] === "adaptive" }))}
                  xLabel={r.variables[r.surrogate_inputs[0]]} yLabel="normalised margin" yLimit={0} height={220} />
                <p className="small faint">Diamonds: adaptively chosen. Dashed: the limit (margin 0).</p></Panel>
            </div>
          </>)}
        </div>
      </div>
    </div>
  );
}

// ================================================================ workspace

export function WorkspaceScreen() {
  const { modelId, go } = useApp();
  const model = useModel();
  const joints = useMemo(() => [...Object.keys(model.data?.spec.drives ?? {}), ...Object.keys(model.data?.spec.held_joints ?? {})], [model.data]);
  const [grid, setGrid] = useState<Record<string, string>>({});
  const [source, setSource] = useState("virtual");
  const [samples, setSamples] = useState(30);
  const [tol, setTol] = useState(0.0025);
  const [payload, setPayload] = useState(0);
  const [verify, setVerify] = useState(2);
  const [metricKey, setMetricKey] = useState("error_rms");
  const [cell, setCell] = useState<AnyJson | null>(null);
  const job = useArtifactJob("workspace");
  useEffect(() => { if (joints.length && !Object.keys(grid).length) setGrid(Object.fromEntries(joints.map((j, i) => [j, i === 0 ? "-1.2, -0.6, 0, 0.6, 1.2" : "0, 0.8, 1.6"]))); }, [joints, grid]);
  if (!modelId) return needModel(go);
  const parsed: Record<string, number[]> = {};
  for (const [k, v] of Object.entries(grid)) {
    const nums = v.split(/[,\s]+/).filter(Boolean).map(Number).filter(Number.isFinite);
    if (nums.length) parsed[k] = nums;
  }
  const size = Object.values(parsed).reduce((a, v) => a * v.length, 1);
  const run = () => job.start(() => adv.workspace({ model_id: modelId, grid: parsed, source, samples, seed: 0, position_tolerance: tol, payload_mass: payload, verify_poses: verify }));
  const r = job.result;
  const cells = (r?.cells ?? []) as AnyJson[];
  const reach = cells.filter((c) => c.reachable);
  const vals = reach.map((c) => (c[metricKey] ?? 0) as number);
  const hi = vals.length ? Math.max(...vals) : 1, lo = vals.length ? Math.min(...vals) : 0;
  const shade = (v: number) => { const t = (v - lo) / (hi - lo || 1); return metricKey === "within_tolerance" ? `hsl(${120 * t}, 55%, 45%)` : `hsl(${120 * (1 - t)}, 55%, 45%)`; };
  return (
    <div className="page">
      <div className="page-head"><h1>Workspace reliability</h1><span className="sub">{model.data?.name}</span></div>
      <div className="split two" style={{ gridTemplateColumns: "330px minmax(0, 1fr)" }}>
        <div className="col">
          <Panel title="Map" actions={<button className="btn primary small" disabled={job.busy || size === 0 || size > 400} onClick={run}><Play />Compute</button>}>
            <div className="form">
              {joints.map((j) => <Field key={j} label={`${j} angles (rad)`} wide><input className="input mono" value={grid[j] ?? ""} onChange={(e) => setGrid({ ...grid, [j]: e.target.value })} /></Field>)}
              <Field label="Configuration"><select value={source} onChange={(e) => setSource(e.target.value)}><option value="nominal">nominal design</option><option value="virtual">virtual manufactured</option><option value="as_built">measured as-built</option></select></Field>
              <Field label="Variants"><Num value={samples} min={1} max={2000} step={1} onChange={setSamples} /></Field>
              <Field label="Position tolerance (m)"><Num value={tol} min={0} onChange={setTol} /></Field>
              <Field label="Payload (kg)"><Num value={payload} min={0} onChange={setPayload} /></Field>
              <Field label="Poses checked at Level 2" wide><Num value={verify} min={0} max={20} step={1} onChange={setVerify} /></Field>
            </div>
            <p className="small faint" style={{ marginTop: 6 }}>{size} poses × {source === "virtual" ? samples : 1} variants. Level 1 quasi-static per pose; the worst poses are re-simulated at Level 2.</p>
            {job.busy && <Spinner label="Computing" />}
          </Panel>
          <History kind="workspace" modelId={modelId} current={job.artifactId} onPick={(id) => { job.load(id); setCell(null); }} />
        </div>
        {!r ? <Panel><Empty title="No map">Choose a joint grid and compute.</Empty></Panel> : (
          <div className="col">
            <Panel title={`Map ${r.id}: ${r.source}, ${r.samples} variants (${r.level})`} actions={<Tabs tabs={[["error_rms", "RMS error"], ["error_max", "Max error"], ["within_tolerance", "P(within tolerance)"], ["manipulability", "Manipulability"]]} value={metricKey} onChange={setMetricKey} />}>
              <ResponsiveContainer width="100%" height={380}>
                <ScatterChart margin={{ top: 10, right: 16, bottom: 18, left: 8 }}>
                  <CartesianGrid /><XAxis type="number" dataKey="x" name="x" unit=" m" domain={["auto", "auto"]} label={{ value: "end-effector x (m)", position: "insideBottom", offset: -8 }} />
                  <YAxis type="number" dataKey="z" name="z" unit=" m" domain={["auto", "auto"]} width={60} label={{ value: "z (m)", angle: -90, position: "insideLeft" }} /><ZAxis range={[160, 160]} />
                  <Tooltip formatter={(v) => fmt(Number(v))} />
                  <Scatter data={cells.map((c) => ({ x: c.position[0], z: c.position[2], c }))} onClick={(p: { payload?: { c: AnyJson } }) => p.payload && setCell(p.payload.c)}>
                    {cells.map((c, i) => <Cell key={i} fill={c.reachable ? shade((c[metricKey] ?? 0) as number) : "var(--border-strong)"} stroke={c.near_singular ? "var(--text)" : "none"} />)}
                  </Scatter>
                </ScatterChart>
              </ResponsiveContainer>
              <p className="small muted">Colour: {metricKey === "within_tolerance" ? "green = more likely within tolerance" : "green = smaller"} ({fmt(lo * (metricKey.startsWith("error") ? 1000 : 1), 3)} to {fmt(hi * (metricKey.startsWith("error") ? 1000 : 1), 3)}{metricKey.startsWith("error") ? " mm" : ""}).
                Grey: outside the joint range. Black outline: near singular. {r.collision}. Click a pose.</p>
            </Panel>
            <div className="grid2">
              <Panel title="Selected pose">{!cell ? <Empty title="Click a pose on the map" /> : (
                <dl className="kv">{Object.entries(cell.pose as Record<string, number>).map(([k, v]) => <><dt key={k}>{k}</dt><dd key={`${k}v`}>{fmt(v)} rad</dd></>)}
                  <dt>Reachable</dt><dd>{String(cell.reachable)}</dd>{cell.reachable && <><dt>Samples</dt><dd>{cell.samples}</dd><dt>Mean error</dt><dd>{fmt(cell.error_mean * 1000)} mm</dd>
                  <dt>RMS / max</dt><dd>{fmt(cell.error_rms * 1000)} / {fmt(cell.error_max * 1000)} mm</dd>
                  {cell.within_tolerance !== undefined && <><dt>Within tolerance</dt><dd>{pct(cell.within_tolerance)}{cell.interval ? ` (${pct(cell.interval[0])}–${pct(cell.interval[1])})` : " (no interval)"}</dd></>}
                  <dt>Manipulability</dt><dd>{fmt(cell.manipulability, 3)}</dd></>}</dl>)}</Panel>
              <Panel title="Level 2 check of the worst poses" flush>{r.verification.length === 0 ? <Empty title="No poses verified">{r.verification_note}</Empty> : (
                <table className="grid"><thead><tr><th>Pose</th><th className="num">Map RMS</th><th className="num">Level 2 RMS</th></tr></thead><tbody>
                  {r.verification.map((v: AnyJson, i: number) => <tr key={i}><td className="mono small">{Object.entries(v.pose).map(([k, x]) => `${k} ${fmt(x as number, 3)}`).join(", ")}</td>
                    <td className="num">{v.skipped ? "-" : `${fmt(v.map_error_rms * 1000)} mm`}</td><td className="num">{v.skipped ? v.skipped : `${fmt(v.error_rms * 1000)} mm`}</td></tr>)}</tbody></table>)}
                <p className="small faint" style={{ padding: 8 }}>{r.interval_method}</p></Panel>
            </div>
          </div>)}
      </div>
    </div>
  );
}

// ================================================================ degradation

export function DegradationScreen() {
  const { modelId, go } = useApp();
  const model = useModel();
  const driven = Object.keys(model.data?.spec.drives ?? {});
  const [mechs, setMechs] = useState<AnyJson[]>([]);
  const [cycles, setCycles] = useState("0, 100000, 250000, 500000, 750000, 1000000");
  const [pose, setPose] = useState(0);
  const [payload, setPayload] = useState(0);
  const [cons, setCons] = useState({ metric: "ee_error_final", limit: NaN });
  const [inspect, setInspect] = useState(100000);
  const job = useArtifactJob("degradation");
  if (!modelId) return needModel(go);
  const joint = driven[0];
  const cyc = cycles.split(/[,\s]+/).filter(Boolean).map(Number);
  const ok = joint && mechs.length > 0 && mechs.every((m) => Number.isFinite(m.rate)) && Number.isFinite(cons.limit) && cyc.length >= 2;
  const run = () => job.start(() => adv.degradation({ model_id: modelId, mechanisms: mechs.map((m) => ({ ...m, joint, rate_std: Number.isFinite(m.rate_std) ? m.rate_std : null })),
    cycles: cyc, constraints: [{ name: cons.metric, metric: cons.metric, op: "<=", limit: cons.limit }], pose: { [joint]: pose }, payload_mass: payload, inspect_every: inspect || null }));
  const r = job.result;
  const series = (r?.series ?? []).filter((s: AnyJson) => s.valid);
  const keys = series.length ? Object.keys(series[0].state) : [];
  return (
    <div className="page">
      <div className="page-head"><h1>Lifetime degradation</h1><span className="sub">{model.data?.name}</span></div>
      <Alert kind="warn">Model-based projections from progressions you define. MotionProof has no wear physics, lubrication, material or temperature model; this is not a service-life prediction.</Alert>
      <div className="split two" style={{ gridTemplateColumns: "380px minmax(0, 1fr)" }}>
        <div className="col">
          <Panel title="Mechanisms" actions={<select style={{ width: 170 }} value="" aria-label="Add mechanism" onChange={(e) => e.target.value && setMechs([...mechs, { parameter: e.target.value, kind: "linear", rate: NaN, rate_std: NaN, basis: "assumed", assumptions: "" }])}>
            <option value="">add…</option>{["backlash", "friction", "stiffness", "radial_play", "efficiency", "damping"].map((p) => <option key={p}>{p}</option>)}</select>}>
            {mechs.length === 0 ? <Empty title="No mechanisms">Add a parameter progression. Rates come from your data or are labelled assumed.</Empty> : mechs.map((m, i) => {
              const upd = (p: AnyJson) => setMechs(mechs.map((x, j) => (j === i ? { ...x, ...p } : x)));
              return <div key={i} className="form" style={{ borderBottom: "1px solid var(--border)", paddingBottom: 8, marginBottom: 8 }}>
                <Field label={`${joint}.${m.parameter}`}><select value={m.kind} onChange={(e) => upd({ kind: e.target.value })}><option value="linear">linear</option><option value="exponential">exponential</option></select></Field>
                <Field label="Basis"><select value={m.basis} onChange={(e) => upd({ basis: e.target.value })}>{["measured", "fitted", "specified", "assumed"].map((b) => <option key={b}>{b}</option>)}</select></Field>
                <Field label="Rate per cycle"><Num value={m.rate} onChange={(v) => upd({ rate: v })} /></Field>
                <Field label="Rate std (band)"><Num value={m.rate_std} min={0} onChange={(v) => upd({ rate_std: v })} /></Field>
                <button className="btn small" onClick={() => setMechs(mechs.filter((_, j) => j !== i))}>Remove</button></div>; })}
          </Panel>
          <Panel title="Projection" actions={<button className="btn primary small" disabled={!ok || job.busy} onClick={run}><Play />Project</button>}>
            <div className="form">
              <Field label="Cycles" wide><input className="input mono" value={cycles} onChange={(e) => setCycles(e.target.value)} /></Field>
              <Field label={`${joint ?? "joint"} pose (rad)`}><Num value={pose} onChange={setPose} /></Field>
              <Field label="Payload (kg)"><Num value={payload} min={0} onChange={setPayload} /></Field>
              <Field label="Requirement"><select value={cons.metric} onChange={(e) => setCons({ ...cons, metric: e.target.value })}>{["ee_error_final", "angle_error_final", "torque_utilisation_peak"].map((m) => <option key={m} value={m}>{metricLabel(m)}</option>)}</select></Field>
              <Field label="≤ limit (SI)"><Num value={cons.limit} onChange={(v) => setCons({ ...cons, limit: v })} /></Field>
              <Field label="Inspect every (cycles)" wide><Num value={inspect} min={0} onChange={setInspect} /></Field>
            </div>{job.busy && <Spinner label="Projecting" />}
          </Panel>
          <History kind="degradation" modelId={modelId} current={job.artifactId} onPick={job.load} />
        </div>
        {!r ? <Panel><Empty title="No projection" /></Panel> : (
          <div className="col">
            <Panel title={`${r.label} (${r.level})`}>
              {Object.entries(r.threshold_crossings as Record<string, AnyJson>).map(([n, c]) => <Alert key={n} kind={c.cycles == null ? "ok" : "bad"}>{n}: {c.cycles == null ? c.note : `projected crossing at ${fmt(c.cycles, 5)} cycles (${c.note})`}</Alert>)}
              {r.maintenance && Object.values(r.maintenance as Record<string, AnyJson>).map((m, i) => <p key={i} className="small muted">{m.statement}</p>)}
              <div className="grid2" style={{ marginTop: 8 }}>
                {(() => { const c = r.constraints[0]; const [ck, cu] = metricUnit(c.metric); return (
                  <div><div className="chart-title">{metricLabel(c.metric)} ({cu || "-"}) with band and limit</div>
                    <Lines data={series.map((s: AnyJson) => ({ n: s.cycles, value: s.metrics[c.metric] * ck, limit: c.limit * ck,
                      lo: s.band ? s.band[c.metric][0] * ck : NaN, hi: s.band ? s.band[c.metric][1] * ck : NaN }))}
                      x="n" xLabel="cycles" series={[{ key: "value", name: "projection" }, { key: "limit", name: "limit", dashed: true, color: "var(--bad)" },
                        { key: "lo", name: "band low", dashed: true, color: "var(--faint)" }, { key: "hi", name: "band high", dashed: true, color: "var(--faint)" }]} height={230} /></div>); })()}
                {keys.map((key) => <div key={key}><div className="chart-title">{key} versus cycles</div>
                  <Lines data={series.map((s: AnyJson) => ({ n: s.cycles, v: s.state[key] }))} x="n" xLabel="cycles" series={[{ key: "v", name: key }]} height={230} /></div>)}
              </div>
            </Panel>
            <Panel title="Assumptions">{r.assumptions.map((a: string, i: number) => <div key={i} className="small muted">• {a}</div>)}</Panel>
          </div>)}
      </div>
    </div>
  );
}

// ================================================================ fidelity

export function FidelityScreen() {
  const { modelId, go } = useApp();
  const model = useModel();
  const driven = Object.keys(model.data?.spec.drives ?? {});
  const [pose, setPose] = useState(0);
  const [samples, setSamples] = useState(10);
  const job = useArtifactJob("fidelity");
  if (!modelId) return needModel(go);
  const r = job.result;
  return (
    <div className="page">
      <div className="page-head"><h1>Multi-fidelity comparison</h1><span className="sub">{model.data?.name}</span><span className="spacer" />
        <Field label={`${driven[0] ?? "joint"} pose (rad)`}><div style={{ width: 100 }}><Num value={pose} onChange={setPose} /></div></Field>
        <Field label="Variants"><div style={{ width: 90 }}><Num value={samples} min={1} max={500} step={1} onChange={setSamples} /></div></Field>
        <button className="btn primary" disabled={!driven.length || job.busy} onClick={() => job.start(() => adv.fidelity({ model_id: modelId, pose: { [driven[0]]: pose }, samples }))}><Play />Compare L1 and L2</button></div>
      <div className="grid4">
        {[["L1 quasi-static", "implemented", "static equilibrium: kinematics, gravity, backlash, windup"], ["L2 reduced-order dynamics", "implemented", "MuJoCo + drive train: inertia, friction, motor limits"],
          ["L3 contact / structural", "not implemented", "no validated contact or FEA solver integrated"], ["L4 physical", "via hardware sessions", "measurements, calibration, holdout"]].map(([t, s, d]) => (
          <Panel key={t}><Stat label={t} value={s} sub={d} tone={s === "not implemented" ? "neg" : undefined} /></Panel>))}
      </div>
      {job.busy && <Spinner label="Running both levels" />}
      {!r ? <Panel><Empty title="No comparison">The measured L1–L2 difference sets the band within which an L1 verdict is refused and L2 is required.</Empty></Panel> : (
        <Panel title={`L1 versus L2 on ${r.variants} variants`} flush>
          <table className="grid"><thead><tr><th>Metric</th><th className="num">Mean difference</th><th className="num">95 % |difference|</th><th className="num">Max |difference|</th><th className="num">95 % relative</th></tr></thead><tbody>
            {Object.entries(r.metrics as Record<string, AnyJson>).map(([k, v]) => <tr key={k}><td>{metricLabel(k)}</td><td className="num">{metricFmt(k, v.mean_difference)}</td>
              <td className="num">{metricFmt(k, v.p95_abs_difference)}</td><td className="num">{metricFmt(k, v.max_abs_difference)}</td><td className="num">{pct(v.p95_abs_relative)}</td></tr>)}</tbody></table>
          <p className="small faint" style={{ padding: 8 }}>{r.note}</p>
        </Panel>)}
    </div>
  );
}

// ================================================================ failure investigation

export function InvestigationScreen() {
  const { experimentId, go } = useApp();
  const exp = useExperiment();
  const failed = useAsync(experimentId ? () => api.results(experimentId, "failed", undefined, 200) : null, [experimentId]);
  const [scenario, setScenario] = useState<string | null>(null);
  const job = useArtifactJob("rootcause");
  useEffect(() => { if (!scenario && failed.data?.results.length) setScenario(failed.data.results[0].id); }, [failed.data, scenario]);
  if (!experimentId) return <NeedSelection what="experiment" action={<button className="btn primary" onClick={() => go("monitor")}>Open experiments</button>} />;
  const r = job.result && job.result.scenario === scenario ? job.result : null;
  const stored = failed.data?.results.find((x) => x.id === scenario);
  return (
    <div className="page">
      <div className="page-head"><h1>Failure investigation</h1><span className="sub">{exp.data?.name}</span><span className="spacer" />
        <button className="btn primary" disabled={!scenario || job.busy} onClick={() => scenario && job.start(() => adv.rootcause(experimentId, scenario))}><Search />Investigate {scenario}</button></div>
      <div className="split two" style={{ gridTemplateColumns: "260px minmax(0, 1fr)" }}>
        <Panel title="Failed scenarios" flush>
          <Load state={failed}>{(d) => d.results.length === 0 ? <Empty title="No failures in this experiment" /> : (
            <div className="list">{d.results.map((s) => <button key={s.id} className={`list-item ${s.id === scenario ? "selected" : ""}`} onClick={() => setScenario(s.id)}>
              <span className="name">{s.id}<br /><span className="faint small">{s.failures.map((f) => f.category).join(", ")}</span></span></button>)}</div>)}</Load>
        </Panel>
        <div className="col">
          {stored && <Panel title={`Scenario ${stored.id}`}>
            <div className="row wrap">{stored.failures.map((f, i) => <Badge key={i} kind="bad">{f.category}: {f.constraint}</Badge>)}</div>
            <div className="row wrap" style={{ marginTop: 6 }}>{Object.entries(stored.operating).map(([k, v]) => <Badge key={k}>{k} {fmt(v)}</Badge>)}</div></Panel>}
          {job.busy && <Spinner label="Running sensitivity and counterfactual simulations" />}
          {!r ? (!job.busy && <Panel><Empty title="Not investigated">Investigate re-simulates the failure, measures local sensitivity and reruns it with each leading parameter at nominal.</Empty></Panel>) : (<>
            <Panel title="Explanation (assembled from the numbers below)"><p>{r.explanation}</p><p className="small faint" style={{ marginTop: 6 }}>{r.evidence_note} {r.simulations_run} simulations.</p></Panel>
            <Panel title="Contribution ranking" flush>
              <table className="grid"><thead><tr><th>Parameter</th><th className="num">Value</th><th className="num">Reference</th><th className="num">Local effect</th><th className="num">Rerun at reference</th><th>Fixes?</th><th className="num">Association (KS p)</th></tr></thead><tbody>
                {r.contributions.map((c: AnyJson) => <tr key={c.parameter}><td>{c.parameter}</td><td className="num">{fmt(c.value, 6)}</td><td className="num">{fmt(c.reference, 6)}</td>
                  <td className="num">{signed(c.local_first_order_effect, 3)}</td>
                  <td className="num">{c.counterfactual ? `${metricFmt(r.metric, c.counterfactual.metric_after)} (${pct(c.counterfactual.relative_improvement, 0)} better)` : "invalid"}</td>
                  <td>{c.counterfactual?.fixes_failure ? <Badge kind="ok">yes</Badge> : <Badge>no</Badge>}</td>
                  <td className="num">{c.association ? fmt(c.association.p_value, 2) : "-"}</td></tr>)}</tbody></table>
              <p className="small faint" style={{ padding: 8 }}>Local effect: first-order change of {metricLabel(r.metric)} from this parameter's deviation (positive = makes the failure worse). Reruns are causal evidence within the model; association is not.</p>
            </Panel>
            {r.trace && <Panel title="Replay of the failure"><TraceCharts r={{ valid: true, metrics: r.metrics, message: "", trace: r.trace, measurements: [] }} /></Panel>}
          </>)}
        </div>
      </div>
    </div>
  );
}
