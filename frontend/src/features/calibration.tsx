import { useEffect, useRef, useState } from "react";
import { Play, Upload } from "lucide-react";
import { api } from "../lib/api";
import { isActive, useAsync, useJob } from "../hooks/useAsync";
import { useModel } from "../hooks/useModel";
import { useApp } from "../stores/app";
import type { Series, Task } from "../lib/types";
import { Alert, Badge, Empty, Field, Load, NeedSelection, Num, Panel, Spinner, fmt } from "../components/ui";
import { Lines } from "../components/charts";
import { TaskEditor, defaultTask } from "../components/TaskEditor";

const SIGNALS: Record<string, { label: string; units: string[] }> = {
  output_angle: { label: "Output angle", units: ["rad", "deg"] },
  motor_angle: { label: "Motor angle (referred to output)", units: ["rad", "deg"] },
  motor_torque: { label: "Motor torque", units: ["N*m", "mN*m"] },
  output_velocity: { label: "Output velocity", units: ["rad/s", "deg/s"] },
};
const PARAMS: Record<string, [number, number, string]> = {
  backlash: [0, 0.03, "rad"], stiffness: [100, 20000, "N·m/rad"], friction: [0, 1, "N·m"], efficiency: [0.4, 1, "–"],
  damping: [0, 1, "N·m·s/rad"], zero_offset: [-0.05, 0.05, "rad"],
};
interface Param { name: string; lower: number; upper: number }

export function CalibrationScreen() {
  const { projectId, modelId, go, notify } = useApp();
  const model = useModel();
  const files = useAsync(projectId ? () => api.measurements(projectId) : null, [projectId]);
  const stored = useAsync(modelId ? () => api.calibration(modelId) : null, [modelId]);
  const input = useRef<HTMLInputElement>(null);
  const [calFile, setCalFile] = useState("");
  const [holdFile, setHoldFile] = useState("");
  const [timeColumn, setTimeColumn] = useState("");
  const [timeUnit, setTimeUnit] = useState("s");
  const [mapping, setMapping] = useState<Record<string, { column: string; unit: string }>>({});
  const [params, setParams] = useState<Param[]>([{ name: "backlash", lower: 0, upper: 0.03 }]);
  const [task, setTask] = useState<Task | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useJob(jobId, (j) => { if (j.status === "failed") notify("error", j.error ?? "Calibration failed"); stored.reload(); });
  const driven = Object.keys(model.data?.spec.drives ?? {});
  useEffect(() => { if (driven.length && !task) setTask(defaultTask("reversal", driven[0])); }, [driven, task]);
  const preview = files.data?.find((f) => f.file === calFile) ?? null;
  useEffect(() => { if (preview && !preview.columns.includes(timeColumn)) setTimeColumn(preview.columns[0] ?? ""); }, [preview, timeColumn]);
  if (!projectId || !modelId) return <NeedSelection what="model" action={<button className="btn primary" onClick={() => go("projects")}>Open projects</button>} />;

  const upload = async (list: FileList | null) => {
    if (!list) return;
    try { for (const f of Array.from(list)) await api.importMeasurement(projectId, f); notify("ok", "Measurement file imported"); files.reload(); }
    catch (e) { notify("error", (e as Error).message); }
  };
  const ready = calFile && timeColumn && Object.keys(mapping).length > 0 && params.length > 0 && task && driven.length > 0
    && params.every((p) => p.upper > p.lower) && holdFile !== calFile;
  const run = async () => {
    if (!task) return;
    try {
      const j = await api.calibrate({ model_id: modelId, calibration_file: calFile, holdout_file: holdFile || null,
        config: { task, time_column: timeColumn, time_unit: timeUnit, signals: mapping, parameters: params.map((p) => ({ joint: driven[0], ...p })) } });
      setJobId(j.id);
    } catch (e) { notify("error", (e as Error).message); }
  };
  const r = stored.data?.result ?? null;

  return (
    <div className="page">
      <div className="page-head"><h1>Calibration and physical measurements</h1><span className="sub">{model.data?.name}</span><span className="spacer" />
        <button className="btn" onClick={() => input.current?.click()}><Upload />Import measurement CSV</button>
        <input ref={input} type="file" accept=".csv" multiple hidden onChange={(e) => void upload(e.target.files)} /></div>
      <Alert kind="info">Calibration fits model parameters to a recording of a real joint executing the task defined below. MotionProof ships no measurement data and generates none:
        results appear only for files you import. A model is never called validated on its calibration data.</Alert>
      <div className="split two" style={{ gridTemplateColumns: "430px minmax(0, 1fr)" }}>
        <div className="col">
          <Panel title="1 · Datasets">
            <Load state={files}>{(list) => list.length === 0 ? <Empty title="No measurement files" action={<button className="btn primary" onClick={() => input.current?.click()}>Import a CSV</button>}>
              One row per sample: a time column and one or more signal columns.</Empty> : (
              <div className="form">
                <Field label="Calibration set (used for fitting)" wide><select value={calFile} onChange={(e) => { setCalFile(e.target.value); setMapping({}); }}>
                  <option value="">select a file…</option>{list.map((f) => <option key={f.file} value={f.file}>{f.file} ({f.row_count} rows)</option>)}</select></Field>
                <Field label="Holdout set (independent validation)" wide hint={holdFile ? "A separate recording: independent evidence." : "None selected: the last 30% of the calibration recording is held out, which is weaker evidence."}>
                  <select value={holdFile} onChange={(e) => setHoldFile(e.target.value)}><option value="">tail of the calibration recording</option>
                    {list.filter((f) => f.file !== calFile).map((f) => <option key={f.file} value={f.file}>{f.file} ({f.row_count} rows)</option>)}</select></Field>
              </div>)}</Load>
          </Panel>
          {preview && <Panel title="2 · Column mapping and units">
            <div className="table-wrap" style={{ maxHeight: 130, marginBottom: 8 }}><table className="grid"><thead><tr>{preview.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
              <tbody>{preview.rows.slice(0, 4).map((row, i) => <tr key={i}>{row.map((v, j) => <td key={j} className="num">{v}</td>)}</tr>)}</tbody></table></div>
            <div className="form">
              <Field label="Time column"><select value={timeColumn} onChange={(e) => setTimeColumn(e.target.value)}>{preview.columns.map((c) => <option key={c}>{c}</option>)}</select></Field>
              <Field label="Time unit"><select value={timeUnit} onChange={(e) => setTimeUnit(e.target.value)}><option>s</option><option>ms</option></select></Field>
            </div>
            <table className="grid" style={{ marginTop: 6 }}><thead><tr><th>Signal</th><th>Column</th><th>Unit</th></tr></thead><tbody>
              {Object.entries(SIGNALS).map(([key, s]) => { const m = mapping[key]; return (<tr key={key}><td>{s.label}</td>
                <td><select value={m?.column ?? ""} aria-label={`${s.label} column`} onChange={(e) => { const next = { ...mapping }; if (e.target.value) next[key] = { column: e.target.value, unit: m?.unit ?? s.units[0] }; else delete next[key]; setMapping(next); }}>
                  <option value="">not recorded</option>{preview.columns.filter((c) => c !== timeColumn).map((c) => <option key={c}>{c}</option>)}</select></td>
                <td><select value={m?.unit ?? s.units[0]} disabled={!m} aria-label={`${s.label} unit`} onChange={(e) => m && setMapping({ ...mapping, [key]: { ...m, unit: e.target.value } })}>{s.units.map((x) => <option key={x}>{x}</option>)}</select></td></tr>); })}
            </tbody></table>
          </Panel>}
          <Panel title="3 · Recorded task">{task && driven.length > 0 ? <TaskEditor task={task} joints={driven} onChange={setTask} /> : <Empty title="No driven joint">Configure the mechanical model first.</Empty>}
            <p className="small muted" style={{ marginTop: 6 }}>The simulated task must be the motion that was recorded, with the same timing.</p></Panel>
          <Panel title="4 · Parameters to estimate" actions={<>{isActive(job) && <Spinner label="Fitting" />}
            <button className="btn primary small" disabled={!ready || isActive(job)} onClick={run}><Play />Calibrate</button></>}>
            <table className="grid"><thead><tr><th>Parameter</th><th className="num">Lower bound</th><th className="num">Upper bound</th><th>Unit</th><th /></tr></thead><tbody>
              {params.map((p, i) => { const upd = (x: Partial<Param>) => setParams(params.map((q, j) => (j === i ? { ...q, ...x } : q))); return (<tr key={i}>
                <td><select value={p.name} aria-label="Parameter" onChange={(e) => upd({ name: e.target.value, lower: PARAMS[e.target.value][0], upper: PARAMS[e.target.value][1] })}>{Object.keys(PARAMS).map((k) => <option key={k} value={k}>{k.replace(/_/g, " ")}</option>)}</select></td>
                <td><Num value={p.lower} onChange={(v) => upd({ lower: v })} ariaLabel="Lower bound" /></td><td><Num value={p.upper} onChange={(v) => upd({ upper: v })} ariaLabel="Upper bound" /></td>
                <td className="muted">{PARAMS[p.name][2]}</td><td><button className="btn ghost small" disabled={params.length === 1} onClick={() => setParams(params.filter((_, j) => j !== i))}>Remove</button></td></tr>); })}
            </tbody></table>
            <button className="btn small" style={{ marginTop: 6 }} disabled={params.length >= Object.keys(PARAMS).length}
              onClick={() => { const free = Object.keys(PARAMS).find((k) => !params.some((p) => p.name === k)); if (free) setParams([...params, { name: free, lower: PARAMS[free][0], upper: PARAMS[free][1] }]); }}>Add parameter</button>
            {holdFile === calFile && calFile && <Alert kind="bad">The holdout set must differ from the calibration set.</Alert>}
          </Panel>
        </div>
        <div className="col">
          {!r ? <Panel><Empty title="No calibration result">Import measurements, map the columns and run the calibration. Predicted-versus-measured plots, residuals and the holdout assessment appear here.</Empty></Panel> : (<>
            <Panel title="Model quality" actions={<Badge kind={r.assessment === "holdout_consistent" ? "ok" : "bad"}>{r.assessment.replace(/_/g, " ")}</Badge>}>
              <p className="muted small" style={{ marginBottom: 8 }}>{r.statement}</p>
              <table className="grid"><thead><tr><th>Signal</th><th className="num">Calibration RMSE</th><th className="num">Holdout RMSE</th><th className="num">Holdout MAE</th><th className="num">Holdout max deviation</th><th className="num">RMSE ratio</th></tr></thead><tbody>
                {Object.keys(r.holdout.errors).map((s) => <tr key={s}><td>{SIGNALS[s]?.label ?? s}</td><td className="num">{fmt(r.calibration.errors[s].rmse)}</td><td className="num">{fmt(r.holdout.errors[s].rmse)}</td>
                  <td className="num">{fmt(r.holdout.errors[s].mae)}</td><td className="num">{fmt(r.holdout.errors[s].max_abs)}</td><td className={`num ${r.holdout.rmse_ratio[s] > 2 ? "neg" : ""}`}>{fmt(r.holdout.rmse_ratio[s], 3)}</td></tr>)}
              </tbody></table>
              <p className="small faint" style={{ marginTop: 6 }}>Calibration set: {r.calibration.name} ({r.calibration.samples} samples). Holdout set: {r.holdout.name} ({r.holdout.samples} samples, {r.holdout.split.replace(/_/g, " ")}). SI units.</p>
            </Panel>
            <div className="grid2">
              <Panel title="Parameter estimates" flush foot={`${r.solver.method}; ${r.solver.evaluations} simulations; condition number ${fmt(r.condition_number, 3)}`}>
                <table className="grid"><thead><tr><th>Parameter</th><th className="num">Estimate</th><th className="num">Std error</th><th className="num">Bounds</th></tr></thead><tbody>
                  {r.parameters.map((p) => <tr key={p.name}><td>{p.joint}.{p.name} {p.at_bound && <Badge kind="warn">at bound</Badge>}</td><td className="num">{fmt(p.estimate, 5)}</td><td className="num">{p.std_error == null ? "undefined" : fmt(p.std_error, 3)}</td><td className="num">{p.lower} … {p.upper}</td></tr>)}
                </tbody></table>
              </Panel>
              <Panel title="Identifiability and warnings">{r.warnings.length === 0 ? <Alert kind="ok">No identifiability warnings.</Alert> : <div className="col" style={{ gap: 6 }}>{r.warnings.map((w, i) => <Alert key={i} kind="warn">{w}</Alert>)}</div>}</Panel>
            </div>
            {Object.keys(r.holdout.signals).map((s) => { const row = (set: Series) => set.time.map((t, i) => ({ t, measured: set.signals[s].measured[i], predicted: set.signals[s].predicted[i], residual: set.signals[s].residual[i] })); return (
              <Panel key={s} title={`${SIGNALS[s]?.label ?? s} — predicted versus measured`}>
                <div className="grid2">
                  <div><div className="chart-title">Calibration set (fitted)</div><Lines data={row(r.calibration)} x="t" xLabel="time s" series={[{ key: "measured", name: "measured", color: "var(--faint)" }, { key: "predicted", name: "predicted" }]} /></div>
                  <div><div className="chart-title">Holdout set (not used for fitting)</div><Lines data={row(r.holdout)} x="t" xLabel="time s" series={[{ key: "measured", name: "measured", color: "var(--faint)" }, { key: "predicted", name: "predicted", color: "var(--bad)" }]} /></div>
                  <div><div className="chart-title">Calibration residual</div><Lines data={row(r.calibration)} x="t" xLabel="time s" series={[{ key: "residual", name: "predicted − measured" }]} height={140} /></div>
                  <div><div className="chart-title">Holdout residual</div><Lines data={row(r.holdout)} x="t" xLabel="time s" series={[{ key: "residual", name: "predicted − measured", color: "var(--bad)" }]} height={140} /></div>
                </div>
              </Panel>); })}
          </>)}
        </div>
      </div>
    </div>
  );
}
