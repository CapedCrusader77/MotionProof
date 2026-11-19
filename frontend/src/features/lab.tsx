import { useEffect, useMemo, useState } from "react";
import { Download, Play, Plus, ShieldAlert, Trash2 } from "lucide-react";
import { adv, type AnyJson } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import { useArtifactJob } from "../hooks/useArtifactJob";
import { useModel } from "../hooks/useModel";
import { useApp } from "../stores/app";
import { Alert, Badge, Empty, Field, Load, NeedSelection, Num, Panel, Spinner, Stat, Tabs, fmt, metricFmt, metricLabel, pct, signed } from "../components/ui";
import { Histogram, Lines, Points } from "../components/charts";
import { TASK_METRICS, TaskEditor, defaultTask } from "../components/TaskEditor";
import type { Task, Tolerance } from "../lib/types";

function History({ kind, modelId, onPick, current }: { kind: string; modelId: string; onPick: (id: string) => void; current: string | null }) {
  const list = useAsync(() => adv.artifacts(kind, undefined, modelId), [kind, modelId, current]);
  return (
    <Panel title="History" flush>
      <Load state={list}>{(rows) => rows.length === 0 ? <Empty title="None yet" /> : (
        <div className="list">{rows.map((r) => (
          <button key={r.id} className={`list-item ${r.id === current ? "selected" : ""}`} onClick={() => onPick(r.id)}>
            <span className="name">{r.name}<br /><span className="faint small">{r.id} · {new Date(r.created).toLocaleString()}</span></span><Badge>{r.status}</Badge></button>))}</div>)}</Load>
    </Panel>
  );
}
const needModel = (go: (r: "projects") => void) => <NeedSelection what="model" action={<button className="btn primary" onClick={() => go("projects")}>Open projects</button>} />;

// ================================================================ process batches

interface SourceRow { level: string; std: number; shared_group: string; enabled: boolean; basis: string }
interface FeatureRow { feature: string; process: string; target: number; lower: number; upper: number; unit: string; sources: SourceRow[]; drift: number }

export function ProcessScreen() {
  const { modelId, go } = useApp();
  const model = useModel();
  const [features, setFeatures] = useState<FeatureRow[]>([]);
  const [plan, setPlan] = useState({ batches: 4, setups_per_batch: 5, parts_per_setup: 20, tool_life_parts: 0, seed: 1 });
  const job = useArtifactJob("batch");
  const tols = model.data?.spec.tolerances ?? [];
  if (!modelId) return needModel(go);
  const add = (t: Tolerance) => setFeatures([...features, { feature: t.id, process: "", target: (t.nominal + t.lower + t.nominal + t.upper) / 2,
    lower: t.nominal + t.lower, upper: t.nominal + t.upper, unit: t.unit, drift: 0,
    sources: [{ level: "part", std: NaN, shared_group: "", enabled: true, basis: "assumed" }] }]);
  const upd = (i: number, p: Partial<FeatureRow>) => setFeatures(features.map((f, j) => (j === i ? { ...f, ...p } : f)));
  const valid = features.length > 0 && features.every((f) => f.process.trim() && f.sources.every((s) => Number.isFinite(s.std) && s.std >= 0));
  const run = () => job.start(() => adv.batch({ model_id: modelId, name: "virtual batch", plan: { ...plan, tool_life_parts: plan.tool_life_parts || null },
    process: { name: "process model", features: features.map((f) => ({ feature: f.feature, process: f.process, target: f.target, unit: f.unit,
      lower_limit: f.lower, upper_limit: f.upper, drift: f.drift ? { kind: "linear", rate: f.drift, basis: "assumed" } : { kind: "none" },
      sources: f.sources.map((s) => ({ level: s.level, std: s.std, enabled: s.enabled, basis: s.basis, shared_group: s.shared_group || null })) })) } }));
  const r = job.result;
  return (
    <div className="page">
      <div className="page-head"><h1>Process-aware manufacturing</h1><span className="sub">{model.data?.name}</span></div>
      <Alert kind="info">A statistical process model, not a machining simulation. Every variance source is entered by you and switched on or off explicitly; nothing is defaulted.
        Sources sharing a group name are drawn once per batch, setup or tool and move those features together.</Alert>
      <div className="split two" style={{ gridTemplateColumns: "minmax(0, 1fr) 300px" }}>
        <div className="col">
          <Panel title="Process model" actions={<select style={{ width: 230 }} value="" aria-label="Add feature" onChange={(e) => { const t = tols.find((x) => x.id === e.target.value); if (t) add(t); }}>
            <option value="">Add a toleranced feature…</option>{tols.filter((t) => !features.some((f) => f.feature === t.id)).map((t) => <option key={t.id}>{t.id}</option>)}</select>}>
            {features.length === 0 ? <Empty title="No features in the process model">Add the toleranced features this process produces.</Empty> : features.map((f, i) => (
              <div key={f.feature} style={{ borderBottom: "1px solid var(--border)", paddingBottom: 8, marginBottom: 8 }}>
                <div className="row center"><b className="grow">{f.feature}</b><button className="btn ghost small" onClick={() => setFeatures(features.filter((_, j) => j !== i))} aria-label="Remove feature"><Trash2 /></button></div>
                <div className="form three" style={{ gridTemplateColumns: "repeat(5, minmax(0, 1fr))" }}>
                  <Field label="Process"><input className="input" value={f.process} placeholder="e.g. CNC turning" onChange={(e) => upd(i, { process: e.target.value })} /></Field>
                  <Field label={`Target (${f.unit})`}><Num value={f.target} onChange={(v) => upd(i, { target: v })} /></Field>
                  <Field label="Lower limit"><Num value={f.lower} onChange={(v) => upd(i, { lower: v })} /></Field>
                  <Field label="Upper limit"><Num value={f.upper} onChange={(v) => upd(i, { upper: v })} /></Field>
                  <Field label="Drift per part"><Num value={f.drift} onChange={(v) => upd(i, { drift: v })} /></Field>
                </div>
                <table className="grid" style={{ marginTop: 6 }}><thead><tr><th>On</th><th>Level</th><th className="num">Std ({f.unit})</th><th>Shared group</th><th>Basis</th><th /></tr></thead><tbody>
                  {f.sources.map((s, k) => { const us = (p: Partial<SourceRow>) => upd(i, { sources: f.sources.map((x, m) => (m === k ? { ...x, ...p } : x)) }); return (
                    <tr key={k}><td><input type="checkbox" checked={s.enabled} onChange={(e) => us({ enabled: e.target.checked })} aria-label="Enabled" /></td>
                      <td><select value={s.level} onChange={(e) => us({ level: e.target.value })}>{["batch", "setup", "tool", "part", "measurement"].map((l) => <option key={l}>{l}</option>)}</select></td>
                      <td style={{ width: 110 }}><Num value={s.std} min={0} onChange={(v) => us({ std: v })} ariaLabel="Standard deviation" /></td>
                      <td><input className="input" value={s.shared_group} placeholder="independent" onChange={(e) => us({ shared_group: e.target.value })} /></td>
                      <td><select value={s.basis} onChange={(e) => us({ basis: e.target.value })}>{["measured", "specified", "assumed"].map((l) => <option key={l}>{l}</option>)}</select></td>
                      <td><button className="btn ghost small" onClick={() => upd(i, { sources: f.sources.filter((_, m) => m !== k) })} aria-label="Remove source"><Trash2 /></button></td></tr>); })}</tbody></table>
                <button className="btn small" style={{ marginTop: 4 }} onClick={() => upd(i, { sources: [...f.sources, { level: "setup", std: NaN, shared_group: "", enabled: true, basis: "assumed" }] })}><Plus />Source</button>
              </div>))}
          </Panel>
          {r && <BatchResult r={r} />}
        </div>
        <div className="col">
          <Panel title="Batch plan" actions={<button className="btn primary small" disabled={!valid || job.busy} onClick={run}><Play />Generate</button>}>
            <div className="form">
              <Field label="Batches"><Num value={plan.batches} min={1} step={1} onChange={(v) => setPlan({ ...plan, batches: v })} /></Field>
              <Field label="Setups per batch"><Num value={plan.setups_per_batch} min={1} step={1} onChange={(v) => setPlan({ ...plan, setups_per_batch: v })} /></Field>
              <Field label="Parts per setup"><Num value={plan.parts_per_setup} min={1} step={1} onChange={(v) => setPlan({ ...plan, parts_per_setup: v })} /></Field>
              <Field label="Tool life (parts, 0 = none)"><Num value={plan.tool_life_parts} min={0} step={1} onChange={(v) => setPlan({ ...plan, tool_life_parts: v })} /></Field>
              <Field label="Seed"><Num value={plan.seed} step={1} onChange={(v) => setPlan({ ...plan, seed: v })} /></Field>
            </div>
            {!valid && features.length > 0 && <p className="small faint" style={{ marginTop: 6 }}>Every feature needs a process name and every source a standard deviation.</p>}
            {job.busy && <Spinner label="Generating" />}
          </Panel>
          <History kind="batch" modelId={modelId} current={job.artifactId} onPick={job.load} />
        </div>
      </div>
    </div>
  );
}

function BatchResult({ r }: { r: AnyJson }) {
  const feats = Object.keys(r.summary);
  const [f, setF] = useState(feats[0]);
  const s = r.summary[f], vc = r.variance_components[f], ch = r.control_charts[f];
  const hist = useMemo(() => { const v: number[] = r.samples[f] ?? []; const lo = Math.min(...v), hi = Math.max(...v), n = 30, w = (hi - lo) / n || 1e-12;
    const c = new Array(n).fill(0); v.forEach((x) => { c[Math.min(n - 1, Math.floor((x - lo) / w))] += 1; }); return { x: c.map((_, i) => lo + (i + 0.5) * w), count: c }; }, [r, f]);
  return (<>
    <Panel title={`Virtual batch ${r.id}: ${r.parts} parts`} actions={<Tabs tabs={feats.map((x) => [x, x] as [string, string])} value={f} onChange={setF} />}>
      <Alert kind="warn">{r.label}</Alert>
      <div className="grid4" style={{ marginTop: 8 }}>
        <Stat label="Mean" value={fmt(s.mean, 7)} sub={s.unit} /><Stat label="Std" value={fmt(s.std, 3)} />
        <Stat label="Cp / Cpk (overall)" value={`${fmt(s.cp, 3)} / ${fmt(s.cpk, 3)}`} sub={s.note} /><Stat label="Out of specification" value={pct(s.out_of_spec_fraction, 2)} tone={s.out_of_spec ? "neg" : undefined} />
      </div>
      <div className="grid2" style={{ marginTop: 8 }}>
        <div><div className="chart-title">Distribution ({s.unit})</div><Histogram hist={hist} unit={s.unit} height={170} /></div>
        <div><div className="chart-title">Subgroup means (control chart, measured values)</div>
          {ch.error ? <Alert kind="info">{ch.error}</Alert> : <><Lines data={ch.xbar.map((v: number, i: number) => ({ i, mean: v, ucl: ch.ucl, lcl: ch.lcl, centre: ch.centre }))} x="i" xLabel="subgroup"
            series={[{ key: "mean", name: "subgroup mean" }, { key: "ucl", name: "UCL", dashed: true, color: "var(--bad)" }, { key: "lcl", name: "LCL", dashed: true, color: "var(--bad)" }, { key: "centre", name: "centre", dashed: true, color: "var(--faint)" }]} height={170} />
            <p className="small muted">{ch.statement}{ch.signals.length ? `: ${ch.signals.join("; ")}` : ""}</p></>}</div>
      </div>
    </Panel>
    <div className="grid2">
      <Panel title="Variance components (recovered)">{vc.error ? <Alert kind="info">{vc.error}</Alert> : (<>
        <dl className="kv"><dt>Batch std</dt><dd>{fmt(vc.batch_std, 3)}</dd><dt>Setup std</dt><dd>{fmt(vc.setup_std, 3)}</dd><dt>Part std</dt><dd>{fmt(vc.part_std, 3)}</dd><dt>Method</dt><dd>{vc.method}</dd></dl>
        {vc.notes.map((n: string, i: number) => <div key={i} className="small muted">• {n}</div>)}</>)}</Panel>
      <Panel title="Assembly impact" flush>
        <table className="grid"><thead><tr><th>Fit</th><th className="num">Mean clearance</th><th className="num">Std</th><th className="num">Interference</th></tr></thead><tbody>
          {Object.entries(r.assemblies.fits as Record<string, AnyJson>).map(([k, v]) => <tr key={k}><td>{k}</td><td className="num">{fmt(v.mean * 1000, 4)} µm</td><td className="num">{fmt(v.std * 1000, 3)} µm</td><td className="num">{pct(v.interference_fraction)}</td></tr>)}</tbody></table>
        <div style={{ padding: 8 }} className="small muted">{r.assemblies.evaluated} assemblies evaluated. Violations: {Object.entries(r.assemblies.violations).map(([k, v]) => `${k} ${v}`).join(", ") || "none"}.
          Correlation between features: {r.correlation.features.length > 1 ? r.correlation.matrix[0].slice(1).map((v: number) => fmt(v, 2)).join(", ") : "-"}.</div>
      </Panel>
    </div>
  </>);
}

// ================================================================ hardware

export function HardwareScreen() {
  const { modelId, go } = useApp();
  const model = useModel();
  const devices = useAsync(() => adv.devices(), []);
  const driven = Object.keys(model.data?.spec.drives ?? {});
  const [device, setDevice] = useState("simulated");
  const [test, setTest] = useState({ joint: "", kind: "reversal", centre: 1.5708, excursion: 0.15, move_time: 1.0, settle: 0.5, cycles: 1, load_mass: 0 });
  const [limits, setLimits] = useState({ travel_min: 1.2, travel_max: 1.95, max_speed: 0.8, max_duration: 20, watchdog_ms: 200, max_lost_packets: 20 });
  const [truth, setTruth] = useState(0.009);
  const [confirm, setConfirm] = useState(false);
  const job = useArtifactJob("session");
  useEffect(() => { if (driven.length && !test.joint) setTest((t) => ({ ...t, joint: driven[0] })); }, [driven, test.joint]);
  if (!modelId) return needModel(go);
  const simulated = device === "simulated";
  const peak = 1.875 * test.excursion / test.move_time;
  const lo = test.centre - (test.kind === "reversal" ? test.excursion : 0), hi = test.centre + test.excursion;
  const checks = [["travel within limits", lo >= limits.travel_min && hi <= limits.travel_max, `${fmt(lo)} … ${fmt(hi)} rad`],
    ["peak speed within limit", peak <= limits.max_speed, `${fmt(peak)} rad/s`]] as [string, boolean, string][];
  const run = () => { job.start(() => adv.hardware({ model_id: modelId, device, test, limits, confirm_actuation: confirm,
    simulated_truth: simulated ? { backlash: truth } : {} })); setConfirm(false); };
  const r = job.result;
  return (
    <div className="page">
      <div className="page-head"><h1>Hardware testing</h1><span className="sub">{model.data?.name}</span><span className="spacer" />
        {simulated ? <Badge kind="warn">SIMULATED DEVICE mode</Badge> : <Badge kind="bad">physical device</Badge>}</div>
      <Alert kind="warn"><b>Software limits are not a safety system.</b> They do not replace a wired emergency-stop circuit, mechanical travel stops or an electrical assessment of the rig.
        Nothing moves until you tick the confirmation for that one run.</Alert>
      <div className="split two" style={{ gridTemplateColumns: "360px minmax(0, 1fr)" }}>
        <div className="col">
          <Panel title="Device"><Load state={devices}>{(list) => (
            <div className="col" style={{ gap: 6 }}>
              <select value={device} onChange={(e) => setDevice(e.target.value)} aria-label="Device">{list.map((d) => <option key={d.id} value={d.id} disabled={!d.available}>{d.id} — {d.description}</option>)}</select>
              <dl className="kv"><dt>Connection</dt><dd>{simulated ? "in-process simulation" : "USB serial, JSON lines"}</dd><dt>Emergency stop</dt><dd>{simulated ? "simulated flag" : "device flag bit 0 (hardware circuit required)"}</dd></dl>
            </div>)}</Load></Panel>
          <Panel title="Test">
            <div className="form">
              <Field label="Joint"><select value={test.joint} onChange={(e) => setTest({ ...test, joint: e.target.value })}>{driven.map((j) => <option key={j}>{j}</option>)}</select></Field>
              <Field label="Kind"><select value={test.kind} onChange={(e) => setTest({ ...test, kind: e.target.value })}><option value="reversal">reversal</option><option value="cycles">cycles</option></select></Field>
              <Field label="Centre (rad)"><Num value={test.centre} onChange={(v) => setTest({ ...test, centre: v })} /></Field>
              <Field label="Excursion (rad)"><Num value={test.excursion} min={0.001} onChange={(v) => setTest({ ...test, excursion: v })} /></Field>
              <Field label="Move time (s)"><Num value={test.move_time} min={0.05} onChange={(v) => setTest({ ...test, move_time: v })} /></Field>
              <Field label="Settle (s)"><Num value={test.settle} min={0.05} onChange={(v) => setTest({ ...test, settle: v })} /></Field>
              {test.kind === "cycles" && <Field label="Cycles"><Num value={test.cycles} min={1} max={100} step={1} onChange={(v) => setTest({ ...test, cycles: v })} /></Field>}
              <Field label="Load (kg)"><Num value={test.load_mass} min={0} onChange={(v) => setTest({ ...test, load_mass: v })} /></Field>
              {simulated && <Field label="Simulated rig backlash (rad)" wide hint="The 'true' rig value the simulated device uses; calibration should find it."><Num value={truth} min={0} onChange={setTruth} /></Field>}
            </div>
          </Panel>
          <Panel title="Safety limits">
            <div className="form">
              <Field label="Travel min (rad)"><Num value={limits.travel_min} onChange={(v) => setLimits({ ...limits, travel_min: v })} /></Field>
              <Field label="Travel max (rad)"><Num value={limits.travel_max} onChange={(v) => setLimits({ ...limits, travel_max: v })} /></Field>
              <Field label="Max speed (rad/s)"><Num value={limits.max_speed} min={0.001} onChange={(v) => setLimits({ ...limits, max_speed: v })} /></Field>
              <Field label="Max duration (s)"><Num value={limits.max_duration} min={1} onChange={(v) => setLimits({ ...limits, max_duration: v })} /></Field>
              <Field label="Watchdog (ms)"><Num value={limits.watchdog_ms} min={1} onChange={(v) => setLimits({ ...limits, watchdog_ms: v })} /></Field>
              <Field label="Max lost packets"><Num value={limits.max_lost_packets} min={0} step={1} onChange={(v) => setLimits({ ...limits, max_lost_packets: v })} /></Field>
            </div>
            <h3 style={{ margin: "8px 0 4px" }}>Preflight</h3>
            {checks.map(([n, ok, d]) => <div key={n} className="row center small" style={{ gap: 6 }}><Badge kind={ok ? "ok" : "bad"}>{ok ? "ok" : "fail"}</Badge>{n} <span className="faint">{d}</span></div>)}
            <label className="check" style={{ marginTop: 10 }}><input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />
              I have checked the rig, its stops and emergency stop; start this one run.</label>
            <button className="btn primary" style={{ marginTop: 8 }} disabled={!confirm || job.busy || !test.joint || checks.some((c) => !c[1])} onClick={run}><ShieldAlert />Start test</button>
            {job.busy && <Spinner label="Running" />}
          </Panel>
          <History kind="hardware" modelId={modelId} current={job.artifactId} onPick={job.load} />
        </div>
        {!r ? <Panel><Empty title="No session">Configure a test, confirm, and start it. Results are stored with the device identity and firmware.</Empty></Panel> : (
          <div className="col">
            <Panel title={`Session ${r.id}`} actions={<a className="btn small" href={adv.hardwareCsv(r.id)} download><Download />CSV</a>}>
              <div className="grid4"><Stat label="Source" value={r.source} /><Stat label="Status" value={r.status} tone={r.status === "completed" ? "pos" : "neg"} sub={r.abort_reason ?? undefined} />
                <Stat label="Samples" value={r.samples} sub={`${r.lost_packets} lost · ${r.malformed_messages} malformed`} /><Stat label="Device" value={r.device?.device ?? "-"} sub={`firmware ${r.device?.firmware ?? "-"}`} /></div>
              {r.source === "SIMULATED DEVICE" && <Alert kind="warn">Simulated device: this checks the software path, not the physics.</Alert>}
            </Panel>
            {r.comparison && (<>
              <Panel title="Measured versus predicted (output angle)">
                <Lines data={r.comparison.signals.output_angle.series.t.map((t: number, i: number) => ({ t, measured: r.comparison.signals.output_angle.series.measured[i], predicted: r.comparison.signals.output_angle.series.predicted[i] }))}
                  x="t" xLabel="time s" yLabel="rad" series={[{ key: "measured", name: "measured", color: "var(--faint)" }, { key: "predicted", name: "model" }]} />
                <Lines data={r.comparison.signals.output_angle.series.t.map((t: number, i: number) => ({ t, residual: r.comparison.signals.output_angle.series.residual[i] * 1000 }))}
                  x="t" xLabel="time s" yLabel="mrad" series={[{ key: "residual", name: "measured − model", color: "var(--bad)" }]} height={140} />
              </Panel>
              <Panel title="Discrepancy"><table className="grid"><thead><tr><th>Signal</th><th className="num">RMSE</th><th className="num">MAE</th><th className="num">Max</th></tr></thead><tbody>
                {Object.entries(r.comparison.signals as Record<string, AnyJson>).map(([k, v]) => <tr key={k}><td>{k}</td><td className="num">{fmt(v.rmse * 1000)} mrad</td><td className="num">{fmt(v.mae * 1000)} mrad</td><td className="num">{fmt(v.max_abs * 1000)} mrad</td></tr>)}
                {r.comparison.measured_lost_motion !== undefined && <tr><td>lost motion</td><td colSpan={3} className="num">measured {fmt(r.comparison.measured_lost_motion * 1000)} mrad · model {fmt((r.comparison.predicted_lost_motion ?? NaN) * 1000)} mrad</td></tr>}
              </tbody></table>
                <p className="small muted" style={{ marginTop: 6 }}>To fit model parameters, download the CSV and use Calibration with a second session as the independent holdout.</p></Panel>
            </>)}
          </div>)}
      </div>
    </div>
  );
}

// ================================================================ challenge

const STEPS = ["Model", "Requirements", "Variables", "Cost", "Reliability", "Review", "Results"];

export function ChallengeScreen() {
  const { modelId, go } = useApp();
  const model = useModel();
  const driven = Object.keys(model.data?.spec.drives ?? {});
  const [step, setStep] = useState(0);
  const [task, setTask] = useState<Task | null>(null);
  const [cons, setCons] = useState<{ name: string; metric: string; op: "<=" | ">="; limit: number }[]>([]);
  const [vars, setVars] = useState<{ tolerance: string; kind: "scale" | "shift"; lower: number; upper: number }[]>([]);
  const [costs, setCosts] = useState<Record<string, number>>({});
  const [costSource, setCostSource] = useState("");
  const [rel, setRel] = useState({ target: 0.9, confidence: 0.9 });
  const [search, setSearch] = useState({ samples: 60, verify_samples: 200, screen: 8, refine_generations: 2, seed: 0 });
  const [payload, setPayload] = useState<[number, number] | null>(null);
  const job = useArtifactJob("challenge");
  const comp = useAsync(job.artifactId ? () => adv.artifact(job.artifactId as string, "comparison") : null, [job.artifactId]);
  useEffect(() => { if (driven.length && !task) setTask(defaultTask("reversal", driven[0])); }, [driven, task]);
  if (!modelId) return needModel(go);
  const tols = (model.data?.spec.tolerances ?? []).filter((t) => ["uniform", "normal", "truncated_normal"].includes(t.distribution.type));
  const priced = vars.some((v) => v.kind === "scale" && Number.isFinite(costs[v.tolerance]));
  const problems = [!task && "choose a task", cons.length === 0 && "add at least one requirement", vars.length === 0 && "add at least one decision variable",
    vars.some((v) => !(v.upper > v.lower) || (v.kind === "scale" && v.lower <= 0)) && "every variable needs lower < upper (scale > 0)",
    cons.some((c) => !Number.isFinite(c.limit)) && "every requirement needs a limit"].filter(Boolean) as string[];
  const config = task && {
    name: `challenge on ${model.data?.name}`, search_fidelity: "L2", ...search, reliability: rel, cost_source: priced ? costSource || "user cost model" : null,
    costs: Object.fromEntries(vars.filter((v) => v.kind === "scale" && Number.isFinite(costs[v.tolerance])).map((v) => [v.tolerance, { coefficient: costs[v.tolerance] }])),
    variables: vars, experiment: { name: "challenge task", task, constraints: cons, operating: payload ? { payload_mass: { type: "uniform", low: payload[0], high: payload[1] } } : {} } };
  const run = () => { if (config) { job.start(() => adv.challenge(modelId, config)); setStep(6); } };
  const r = job.result;
  const metrics = task ? TASK_METRICS[task.type].concat(["min_mesh_backlash_mm", "torque_utilisation_peak"]) : [];
  return (
    <div className="page">
      <div className="page-head"><h1>MotionProof Engineering Challenge</h1><span className="sub">least expensive tolerance specification that meets the requirements</span></div>
      <div className="steps" role="tablist">{STEPS.map((s, i) => <button key={s} role="tab" aria-selected={step === i} className={`step ${step === i ? "active" : i < step ? "done" : ""}`} onClick={() => setStep(i)}><i>{i + 1}</i>{s}</button>)}</div>
      <Panel title={STEPS[step]} foot={step < 6 ? <div className="row center"><button className="btn" disabled={step === 0} onClick={() => setStep(step - 1)}>Back</button><span className="grow" />
        {step < 5 ? <button className="btn primary" onClick={() => setStep(step + 1)}>Next</button> : <button className="btn primary" disabled={problems.length > 0 || job.busy} onClick={run}><Play />Run optimisation</button>}</div> : undefined}>
        {step === 0 && <div className="col"><dl className="kv"><dt>Model</dt><dd>{model.data?.name}</dd><dt>Fingerprint</dt><dd>{model.data?.fingerprint}</dd><dt>Driven joints</dt><dd>{driven.join(", ") || "none"}</dd>
          <dt>Tolerances that can vary</dt><dd>{tols.length}</dd></dl>{model.data?.spec.synthetic && <Alert kind="warn">Synthetic reference design: requirements and results are illustrative.</Alert>}
          {task && <TaskEditor task={task} joints={driven} onChange={setTask} />}
          <label className="check"><input type="checkbox" checked={!!payload} onChange={(e) => setPayload(e.target.checked ? [0, 0.5] : null)} />Vary payload (uniform)</label>
          {payload && <div className="form"><Field label="Low (kg)"><Num value={payload[0]} min={0} onChange={(v) => setPayload([v, payload[1]])} /></Field><Field label="High (kg)"><Num value={payload[1]} min={0} onChange={(v) => setPayload([payload[0], v])} /></Field></div>}</div>}
        {step === 1 && <div className="col"><p className="muted">Requirements are your values; none is suggested. A scenario passes only if it meets all of them.</p>
          <select style={{ width: 260 }} value="" onChange={(e) => e.target.value && setCons([...cons, { name: e.target.value, metric: e.target.value, op: e.target.value.startsWith("min_") ? ">=" : "<=", limit: NaN }])} aria-label="Add requirement">
            <option value="">Add requirement…</option>{metrics.filter((m) => !cons.some((c) => c.metric === m)).map((m) => <option key={m} value={m}>{metricLabel(m)}</option>)}</select>
          <table className="grid"><tbody>{cons.map((c, i) => <tr key={c.metric}><td>{metricLabel(c.metric)}</td><td style={{ width: 70 }}>{c.op}</td>
            <td style={{ width: 160 }}><Num value={c.limit} onChange={(v) => setCons(cons.map((x, j) => (j === i ? { ...x, limit: v } : x)))} ariaLabel="Limit (SI)" /></td><td className="muted">SI units</td>
            <td><button className="btn ghost small" onClick={() => setCons(cons.filter((_, j) => j !== i))} aria-label="Remove"><Trash2 /></button></td></tr>)}</tbody></table></div>}
        {step === 2 && <div className="col"><p className="muted">Scale multiplies a tolerance's width and spread (below 1 tightens). Shift moves its centre, for example a backlash target.</p>
          <select style={{ width: 260 }} value="" onChange={(e) => e.target.value && setVars([...vars, { tolerance: e.target.value, kind: "scale", lower: 0.5, upper: 1.5 }])} aria-label="Add variable">
            <option value="">Add decision variable…</option>{tols.map((t) => <option key={t.id}>{t.id}</option>)}</select>
          <table className="grid"><thead><tr><th>Tolerance</th><th>Kind</th><th className="num">Lower</th><th className="num">Upper</th><th /></tr></thead><tbody>
            {vars.map((v, i) => { const u = (p: Partial<typeof v>) => setVars(vars.map((x, j) => (j === i ? { ...x, ...p } : x))); return <tr key={i}><td>{v.tolerance}</td>
              <td><select value={v.kind} onChange={(e) => u({ kind: e.target.value as "scale" | "shift", lower: e.target.value === "scale" ? 0.5 : 0, upper: e.target.value === "scale" ? 1.5 : 0 })}><option>scale</option><option>shift</option></select></td>
              <td style={{ width: 120 }}><Num value={v.lower} onChange={(x) => u({ lower: x })} /></td><td style={{ width: 120 }}><Num value={v.upper} onChange={(x) => u({ upper: x })} /></td>
              <td><button className="btn ghost small" onClick={() => setVars(vars.filter((_, j) => j !== i))} aria-label="Remove"><Trash2 /></button></td></tr>; })}</tbody></table></div>}
        {step === 3 && <div className="col"><p className="muted">Cost of a scaled tolerance = coefficient ÷ scale. Enter coefficients from your own cost data; leave empty if you have none.</p>
          <table className="grid"><tbody>{vars.filter((v) => v.kind === "scale").map((v) => <tr key={v.tolerance}><td>{v.tolerance}</td><td style={{ width: 160 }}><Num value={costs[v.tolerance] ?? NaN} min={0} onChange={(x) => setCosts({ ...costs, [v.tolerance]: x })} ariaLabel="Cost coefficient" /></td></tr>)}</tbody></table>
          {priced && <Field label="Source of the cost data"><input className="input" value={costSource} onChange={(e) => setCostSource(e.target.value)} /></Field>}
          <Alert kind={priced ? "info" : "warn"}>{priced ? "Costs use your coefficients and are reported as estimates." : "No cost data: a unit coefficient is used and results are a relative cost index, not a price. No savings will be claimed."}</Alert></div>}
        {step === 4 && <div className="col"><div className="form three">
          <Field label="Required pass fraction"><Num value={rel.target} min={0.01} max={0.9999} onChange={(v) => setRel({ ...rel, target: v })} /></Field>
          <Field label="Confidence"><Num value={rel.confidence} min={0.51} max={0.999} onChange={(v) => setRel({ ...rel, confidence: v })} /></Field>
          <Field label="Search scenarios per candidate"><Num value={search.samples} min={10} step={1} onChange={(v) => setSearch({ ...search, samples: v })} /></Field>
          <Field label="Verification scenarios"><Num value={search.verify_samples} min={20} step={1} onChange={(v) => setSearch({ ...search, verify_samples: v })} /></Field>
          <Field label="Screen candidates"><Num value={search.screen} min={2} step={1} onChange={(v) => setSearch({ ...search, screen: v })} /></Field>
          <Field label="Refinement generations"><Num value={search.refine_generations} min={0} step={1} onChange={(v) => setSearch({ ...search, refine_generations: v })} /></Field>
          <Field label="Seed"><Num value={search.seed} step={1} onChange={(v) => setSearch({ ...search, seed: v })} /></Field></div>
          <Alert kind="info">Feasible means the one-sided exact (Clopper-Pearson) lower bound of the all-requirements pass fraction is at least {pct(rel.target)} at {pct(rel.confidence, 0)} confidence.
            With zero failures that needs at least {Math.ceil(Math.log(1 - rel.confidence) / Math.log(rel.target))} scenarios.</Alert></div>}
        {step === 5 && <div className="col">{problems.length ? problems.map((p) => <Alert key={p} kind="warn">{p}</Alert>) : <Alert kind="ok">Configuration complete.</Alert>}
          <pre className="mono small" style={{ maxHeight: 360, overflow: "auto", background: "var(--surface-2)", padding: 8, border: "1px solid var(--border)" }}>{JSON.stringify(config, null, 2)}</pre></div>}
        {step === 6 && (!r ? (job.busy ? <Spinner label={`Searching: ${job.job?.progress?.done ?? 0} candidates evaluated`} /> : <Empty title="Not run yet" />) : <ChallengeResult r={r} comparison={comp.data} />)}
      </Panel>
      <History kind="challenge" modelId={modelId} current={job.artifactId} onPick={(id) => { job.load(id); setStep(6); }} />
    </div>
  );
}

function ChallengeResult({ r, comparison }: { r: AnyJson; comparison: AnyJson | null }) {
  const [pick, setPick] = useState<string | null>(r.chosen);
  const sel = r.candidates.find((c: AnyJson) => c.id === pick) ?? r.candidates[0];
  return (
    <div className="col">
      <Alert kind={r.chosen ? "ok" : "warn"}>{r.chosen ? `Chosen ${r.chosen}: feasible in the search and confirmed on ${r.verification.find((v: AnyJson) => v.candidate === r.chosen)?.samples} fresh Level 2 scenarios.` : "No verified feasible candidate within the given ranges."}</Alert>
      {r.notes.map((n: string, i: number) => <Alert key={i} kind="warn">{n}</Alert>)}
      <p className="small muted">{r.objective}. {r.search.method}; {r.search.candidates} candidates, {r.search.scenario_evaluations} scenario evaluations. Cost axis: {r.cost_label}.</p>
      <div className="grid2">
        <div><div className="chart-title">Cost versus demonstrated reliability (lower confidence bound)</div>
          <Points points={r.candidates.map((c: AnyJson) => ({ x: c.cost, y: c.lower_bound, ok: c.feasible, label: c.id, mark: r.pareto.includes(c.id) }))} xLabel="cost" yLabel="lower bound" yLimit={r.reliability.target} onPick={setPick} height={260} />
          <p className="small faint">Diamonds: non-dominated. Red: infeasible. Dashed line: target. Click a point.</p></div>
        <div className="table-wrap" style={{ maxHeight: 300 }}><table className="grid"><thead><tr><th>Candidate</th><th className="num">Cost</th><th className="num">Pass</th><th className="num">Lower bound</th><th /></tr></thead><tbody>
          {[...r.candidates].sort((a: AnyJson, b: AnyJson) => a.cost - b.cost).map((c: AnyJson) => <tr key={c.id} className={`click ${pick === c.id ? "selected" : ""}`} onClick={() => setPick(c.id)}>
            <td>{c.id}{c.id === r.chosen && <> <Badge kind="ok">chosen</Badge></>}{c.id === "baseline" && <> <Badge>original</Badge></>}</td><td className="num">{fmt(c.cost)}</td><td className="num">{pct(c.pass_fraction)}</td><td className="num">{fmt(c.lower_bound, 3)}</td>
            <td>{c.feasible ? <Badge kind="ok">feasible</Badge> : c.physically_invalid ? <Badge kind="warn" title={c.physically_invalid.join("; ")}>impossible spec</Badge> : <Badge kind="bad">no</Badge>}</td></tr>)}</tbody></table></div>
      </div>
      {sel?.physically_invalid && <Alert kind="warn">Candidate {sel.id} was rejected without simulation: {sel.physically_invalid.join("; ")}.</Alert>}
      {sel && <Panel title={`Candidate ${sel.id} (${sel.level}, ${sel.valid} scenarios, seed ${sel.seed})`}>
        <div className="grid2"><table className="grid"><tbody>{Object.entries(sel.decision as Record<string, number>).map(([k, v]) => <tr key={k}><td>{k}</td><td className="num">{fmt(v, 4)}</td></tr>)}</tbody></table>
          <table className="grid"><tbody>{Object.entries(sel.constraint_pass_fraction as Record<string, number>).map(([k, v]) => <tr key={k}><td>{k}</td><td className="num">{pct(v)}</td></tr>)}
            {Object.entries(sel.metrics as Record<string, AnyJson>).map(([k, v]) => <tr key={k}><td>{metricLabel(k)} p95</td><td className="num">{metricFmt(k, v.p95)}</td></tr>)}</tbody></table></div></Panel>}
      {comparison?.available && <Panel title="Original versus optimised specification">
        <table className="grid"><thead><tr><th>Tolerance</th><th>Original limits</th><th>Proposed limits</th><th className="num">Width scale</th><th className="num">Target shift</th><th>Unit</th></tr></thead><tbody>
          {comparison.tolerances.map((t: AnyJson) => <tr key={t.tolerance}><td>{t.tolerance}</td><td className="mono">{t.original_limits.map((x: number) => fmt(x, 6)).join(" … ")}</td>
            <td className="mono">{t.proposed_limits.map((x: number) => fmt(x, 6)).join(" … ")}</td><td className="num">×{fmt(t.scale, 3)}</td><td className="num">{signed(t.shift, 3)}</td><td>{t.unit}</td></tr>)}</tbody></table>
        <div className="grid3" style={{ marginTop: 8 }}>
          <Stat label="Cost" value={`${fmt(comparison.cost.original)} → ${fmt(comparison.cost.proposed)}`} sub={comparison.cost.savings_claim} />
          <Stat label="Verified pass fraction" value={`${pct(comparison.verified.original.pass_fraction)} → ${pct(comparison.verified.proposed.pass_fraction)}`} sub="fresh Level 2 scenarios" />
          <Stat label="Lower bound" value={`${fmt(comparison.verified.original.lower_bound, 3)} → ${fmt(comparison.verified.proposed.lower_bound, 3)}`} sub={`target ${r.reliability.target}`} />
        </div>
        <table className="grid" style={{ marginTop: 8 }}><thead><tr><th>Metric (p95)</th><th className="num">Original</th><th className="num">Proposed</th></tr></thead><tbody>
          {Object.keys(comparison.verified.proposed.metrics).map((k) => <tr key={k}><td>{metricLabel(k)}</td><td className="num">{metricFmt(k, comparison.verified.original.metrics[k]?.p95)}</td><td className="num">{metricFmt(k, comparison.verified.proposed.metrics[k]?.p95)}</td></tr>)}</tbody></table>
      </Panel>}
    </div>
  );
}

// ================================================================ trust panel

export function TrustScreen() {
  const { modelId, go } = useApp();
  const trust = useAsync(modelId ? () => adv.trust(modelId) : null, [modelId]);
  const [group, setGroup] = useState("all");
  if (!modelId) return needModel(go);
  const tone = (s: string) => (s.includes("validated") || s.includes("measured physically") || s.includes("manufacturer") || s.includes("scan") ? "ok"
    : s.includes("assumed") || s.includes("simulated") ? "warn" : s.includes("estimated") || s.includes("calibrated") ? "info" : "plain") as "ok" | "warn" | "info" | "plain";
  return (
    <div className="page">
      <div className="page-head"><h1>Engineering model trust</h1><span className="sub">evidence behind every parameter</span></div>
      <Load state={trust}>{(t) => (<>
        <Alert kind="info">{t.note}</Alert>
        <div className="row wrap">{Object.entries(t.counts as Record<string, number>).map(([k, v]) => <Badge key={k} kind={tone(k)}>{k}: {v}</Badge>)}</div>
        <Panel title="Parameters" flush actions={<Tabs tabs={[["all", "All"], ["geometry", "Geometry"], ["tolerance", "Tolerances"], ["mechanics", "Mechanics"], ["calibration", "Calibration"], ["measurement", "Measurements"]]} value={group} onChange={setGroup} />}>
          <div className="table-wrap" style={{ maxHeight: 620 }}><table className="grid"><thead><tr><th>Group</th><th>Parameter</th><th>Evidence</th><th className="num">Value</th><th>Source</th></tr></thead><tbody>
            {t.parameters.filter((p: AnyJson) => group === "all" || p.group === group).map((p: AnyJson, i: number) => (
              <tr key={i}><td className="muted">{p.group}</td><td>{p.parameter}</td><td><Badge kind={tone(p.status)}>{p.status}</Badge></td>
                <td className="num">{p.value == null ? "-" : `${fmt(p.value, 6)} ${p.unit}`}</td><td className="wrap small">{p.source}</td></tr>))}</tbody></table></div>
        </Panel></>)}</Load>
    </div>
  );
}

// ================================================================ benchmarks

export function BenchmarksScreen() {
  const list = useAsync(() => adv.benchmarks(), []);
  const job = useArtifactJob<AnyJson[]>("benchmarks", () => list.reload());
  const results: AnyJson[] | null = job.result ?? list.data?.latest ?? null;
  const [open, setOpen] = useState<string | null>(null);
  return (
    <div className="page">
      <div className="page-head"><h1>Benchmark suite</h1><span className="sub">reference problems with independent expected values</span><span className="spacer" />
        <button className="btn primary" disabled={job.busy} onClick={() => job.start(() => adv.runBenchmarks())}><Play />Run all</button></div>
      {job.busy && <Spinner label="Running benchmarks on the backend" />}
      <Alert kind="info">Every number comes from a run. Synthetic benchmarks use generated data with known ground truth; none of them is physical validation. Benchmark J has no hardware data.</Alert>
      {!results ? <Panel><Empty title="No benchmark run stored">Run the suite to produce results.</Empty></Panel> : (
        <Panel title="Results" flush>
          <table className="grid"><thead><tr><th>ID</th><th>Benchmark</th><th>Status</th><th className="num">Checks</th><th>Synthetic</th><th className="num">Time</th><th /></tr></thead><tbody>
            {results.map((r) => <tr key={r.id} className="click" onClick={() => setOpen(open === r.id ? null : r.id)}>
              <td>{r.id}</td><td>{r.title}</td><td><Badge kind={r.status === "PASS" ? "ok" : r.status === "NOT RUN" ? "warn" : "bad"}>{r.status}</Badge></td>
              <td className="num">{r.checks.filter((c: AnyJson) => c.passed).length}/{r.checks.length}</td><td>{r.synthetic ? "yes" : "no"}</td><td className="num">{r.seconds} s</td>
              <td><button className="btn ghost small" onClick={(e) => { e.stopPropagation(); job.start(() => adv.runBenchmarks([r.id])); }}>Rerun</button></td></tr>)}</tbody></table>
          {open && (() => { const r = results.find((x) => x.id === open)!; return (
            <div style={{ padding: 10 }}><h2>{r.id}. {r.title}</h2><p className="small muted">{r.purpose} · {r.formulation} · {r.fidelity}</p>
              <table className="grid"><thead><tr><th>Quantity</th><th className="num">Expected</th><th className="num">Actual</th><th className="num">Error</th><th>Criterion</th><th>Result</th></tr></thead><tbody>
                {r.checks.map((c: AnyJson, i: number) => <tr key={i}><td className="wrap">{c.quantity}</td><td className="num">{c.expected == null ? "-" : fmt(c.expected, 6)}</td>
                  <td className="num wrap">{typeof c.actual === "number" ? fmt(c.actual, 6) : String(c.actual)}</td><td className="num">{c.error == null ? "-" : fmt(c.error, 3)}</td><td className="small">{c.criterion}</td>
                  <td><Badge kind={c.passed ? "ok" : "bad"}>{c.passed ? "pass" : "fail"}</Badge></td></tr>)}</tbody></table>
              {(r.notes ?? []).map((n: string, i: number) => <p key={i} className="small muted">• {n}</p>)}</div>); })()}
        </Panel>)}
    </div>
  );
}
