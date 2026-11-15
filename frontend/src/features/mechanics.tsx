import { useEffect, useState } from "react";
import { Play, Save } from "lucide-react";
import { api } from "../lib/api";
import { useModel } from "../hooks/useModel";
import { useApp } from "../stores/app";
import type { Drive, SimResult, Task } from "../lib/types";
import { Alert, Badge, Empty, Field, Load, NeedSelection, Num, Panel, Stat, fmt, metricFmt, metricLabel } from "../components/ui";
import { Lines, traceRows } from "../components/charts";
import { TaskEditor, defaultTask } from "../components/TaskEditor";

const FIDELITY: Record<string, string> = {
  F1_geometry_kinematics: "Fidelity 1 — geometry and kinematics: transforms, dimensional variation, clearance, interference.",
  F2_reduced_order_dynamics: "Fidelity 2 — reduced-order dynamics: rigid bodies, motor limits, effective gearbox with backlash, stiffness and friction. No tooth contact, no structural or thermal effects.",
};

export function TraceCharts({ r }: { r: SimResult }) {
  if (!r.trace.t || r.trace.t.length === 0) return <Empty title="No trace recorded" />;
  const DEG = 180 / Math.PI;
  return (
    <div className="grid2">
      <div><div className="chart-title">Joint angle (deg)</div>
        <Lines data={traceRows(r.trace, { q_cmd: DEG, q_motor: DEG, q_out: DEG })} x="t" xLabel="time s"
          series={[{ key: "q_cmd", name: "command", dashed: true, color: "var(--faint)" }, { key: "q_motor", name: "motor (÷ ratio)" }, { key: "q_out", name: "output", color: "var(--bad)" }]} /></div>
      <div><div className="chart-title">Output tracking error (mrad)</div>
        <Lines data={traceRows(r.trace, { tracking_error: 1e3 })} x="t" xLabel="time s" series={[{ key: "tracking_error", name: "command − output" }]} /></div>
      <div><div className="chart-title">Motor torque vs. available (N·m at the shaft)</div>
        <Lines data={traceRows(r.trace, { tau_motor: 1, tau_available: 1 })} x="t" xLabel="time s"
          series={[{ key: "tau_motor", name: "demand" }, { key: "tau_available", name: "available", dashed: true, color: "var(--bad)" }]} /></div>
      <div><div className="chart-title">End-effector position error (mm)</div>
        <Lines data={traceRows(r.trace, { ee_error: 1e3 })} x="t" xLabel="time s" series={[{ key: "ee_error", name: "|actual − nominal|" }]} /></div>
    </div>
  );
}

export function MechanicsScreen() {
  const { modelId, go, notify } = useApp();
  const model = useModel();
  const [joint, setJoint] = useState<string | null>(null);
  const [drive, setDrive] = useState<Drive | null>(null);
  const [task, setTask] = useState<Task | null>(null);
  const [result, setResult] = useState<SimResult | null>(null);
  const [running, setRunning] = useState(false);
  const spec = model.data?.spec;
  const driven = Object.keys(spec?.drives ?? {});
  const active = joint ?? driven[0] ?? null;
  useEffect(() => {
    if (spec && active && spec.drives[active]) setDrive(structuredClone(spec.drives[active]));
    else setDrive(null);
  }, [spec, active]);
  useEffect(() => { if (driven.length && !task) setTask(defaultTask("reversal", driven[0])); }, [driven, task]);
  if (!modelId) return <NeedSelection what="model" action={<button className="btn primary" onClick={() => go("projects")}>Open projects</button>} />;

  const save = async () => {
    if (!spec || !active || !drive) return;
    try {
      await api.configureMechanics({ model_id: modelId, drives: { ...spec.drives, [active]: drive } });
      notify("ok", "Drive-train parameters saved"); model.reload();
    } catch (e) { notify("error", (e as Error).message); }
  };
  const addDrive = async (j: string) => {
    if (!spec) return;
    // a new drive starts with clearly labelled placeholder values that the engineer must replace
    const d: Drive = {
      motor: { model: null, continuous_torque: 1, peak_torque: 1, max_speed: 100, torque_speed: [], rotor_inertia: 1e-5, friction_torque: 0, source: "placeholder - replace with datasheet values", confidence: "assumed" },
      gearbox: { ratio: 1, efficiency: 1, backlash: 0, stiffness: 1000, damping_ratio: 0.1, source: "placeholder - replace with gearbox data", confidence: "assumed" },
      controller: { bandwidth: 40 }, friction: 0, damping: 0 };
    const body: Record<string, unknown> = { model_id: modelId, drives: { ...spec.drives, [j]: d } };
    if (!spec.end_effector) {
      const b = model.data?.components.find((c) => c.body !== "world")?.body ?? model.data?.components[0]?.body;
      if (b) body.end_effector = { body: b, offset: [0, 0, 0] };
    }
    try { await api.configureMechanics({ model_id: modelId, ...body } as { model_id: string }); notify("info", `Drive added to ${j} with placeholder values marked as assumed`); setJoint(j); model.reload(); }
    catch (e) { notify("error", (e as Error).message); }
  };
  const run = async () => {
    if (!task) return;
    setRunning(true);
    try { setResult(await api.runTask(modelId, task)); } catch (e) { notify("error", (e as Error).message); setResult(null); } finally { setRunning(false); }
  };
  const g = (p: Partial<Drive["gearbox"]>) => drive && setDrive({ ...drive, gearbox: { ...drive.gearbox, ...p } });
  const m = (p: Partial<Drive["motor"]>) => drive && setDrive({ ...drive, motor: { ...drive.motor, ...p } });

  return (
    <div className="page">
      <Load state={model}>{(md) => {
        const undriven = md.joints.filter((j) => !driven.includes(j) && !(j in md.spec.held_joints));
        const stages = md.spec.gear_stages.filter((s) => s.joint === active).sort((a, b) => a.order - b.order);
        return (<>
          <div className="page-head"><h1>Mechanical model</h1><span className="sub">{md.name}</span><Badge kind="info">{md.spec.fidelity.replace(/_/g, " ")}</Badge><span className="spacer" />
            {driven.length > 1 && <select style={{ width: 160 }} value={active ?? ""} onChange={(e) => setJoint(e.target.value)} aria-label="Driven joint">{driven.map((j) => <option key={j}>{j}</option>)}</select>}
            <button className="btn primary" disabled={!drive} onClick={save}><Save />Save parameters</button></div>
          <Alert kind="info">{FIDELITY[md.spec.fidelity] ?? md.spec.fidelity}</Alert>
          {!md.has_dynamics ? <Panel><Empty title="Geometry-only model">This model has no dynamics description. Import a URDF or MJCF model (or use the reference design) to configure motors and gearboxes.</Empty></Panel>
            : !drive ? <Panel title="No drive configured"><Empty title="No driven joint" action={<div className="row">{undriven.map((j) => <button key={j} className="btn" onClick={() => addDrive(j)}>Add drive to {j}</button>)}</div>}>
              Add a motor and gearbox to a joint. New drives start with placeholder values marked as assumed.</Empty></Panel> : (
              <div className="grid3">
                <Panel title={`Motor — ${active}`} foot={<>Source: {drive.motor.source} <Badge kind={drive.motor.confidence === "assumed" ? "warn" : "ok"}>{drive.motor.confidence}</Badge></>}>
                  <div className="form">
                    <Field label="Model" wide><input className="input" value={drive.motor.model ?? ""} onChange={(e) => m({ model: e.target.value || null })} /></Field>
                    <Field label="Continuous torque (N·m)"><Num value={drive.motor.continuous_torque} min={1e-6} onChange={(v) => m({ continuous_torque: v })} /></Field>
                    <Field label="Peak torque (N·m)"><Num value={drive.motor.peak_torque} min={1e-6} onChange={(v) => m({ peak_torque: v })} /></Field>
                    <Field label="Maximum speed (rad/s)"><Num value={drive.motor.max_speed} min={1e-6} onChange={(v) => m({ max_speed: v })} /></Field>
                    <Field label="Rotor inertia (kg·m²)"><Num value={drive.motor.rotor_inertia} min={1e-12} onChange={(v) => m({ rotor_inertia: v })} /></Field>
                    <Field label="Friction torque (N·m)"><Num value={drive.motor.friction_torque} min={0} onChange={(v) => m({ friction_torque: v })} /></Field>
                    <Field label="Data confidence"><select value={drive.motor.confidence} onChange={(e) => m({ confidence: e.target.value })}>{["specified", "measured", "estimated", "assumed"].map((c) => <option key={c}>{c}</option>)}</select></Field>
                    <Field label="Torque–speed curve" wide hint="speed rad/s : torque N·m pairs, comma-separated. Empty = peak torque up to maximum speed.">
                      <input className="input mono" key={active} defaultValue={drive.motor.torque_speed.map((p) => `${p[0]}:${p[1]}`).join(", ")}
                        onBlur={(e) => m({ torque_speed: e.target.value.split(",").map((s) => s.trim().split(":").map(Number)).filter((p) => p.length === 2 && p.every(Number.isFinite)) as [number, number][] })} /></Field>
                    <Field label="Source" wide><input className="input" value={drive.motor.source} onChange={(e) => m({ source: e.target.value })} /></Field>
                  </div>
                </Panel>
                <Panel title="Gearbox" foot={<>Source: {drive.gearbox.source} <Badge kind={drive.gearbox.confidence === "assumed" ? "warn" : "ok"}>{drive.gearbox.confidence}</Badge></>}>
                  <div className="form">
                    <Field label="Ratio"><Num value={drive.gearbox.ratio} min={1e-6} onChange={(v) => g({ ratio: v })} /></Field>
                    <Field label="Efficiency (0–1)"><Num value={drive.gearbox.efficiency} min={0.01} max={1} onChange={(v) => g({ efficiency: v })} /></Field>
                    <Field label="Additional backlash (rad)" hint="Added to the backlash derived from the gear stages"><Num value={drive.gearbox.backlash} min={0} onChange={(v) => g({ backlash: v })} /></Field>
                    <Field label="Torsional stiffness (N·m/rad)"><Num value={drive.gearbox.stiffness} min={1e-6} onChange={(v) => g({ stiffness: v })} /></Field>
                    <Field label="Damping ratio"><Num value={drive.gearbox.damping_ratio} min={0} onChange={(v) => g({ damping_ratio: v })} /></Field>
                    <Field label="Data confidence"><select value={drive.gearbox.confidence} onChange={(e) => g({ confidence: e.target.value })}>{["specified", "measured", "estimated", "assumed"].map((c) => <option key={c}>{c}</option>)}</select></Field>
                    <Field label="Output Coulomb friction (N·m)"><Num value={drive.friction} min={0} onChange={(v) => setDrive({ ...drive, friction: v })} /></Field>
                    <Field label="Output viscous damping (N·m·s/rad)"><Num value={drive.damping} min={0} onChange={(v) => setDrive({ ...drive, damping: v })} /></Field>
                    <Field label="Source" wide><input className="input" value={drive.gearbox.source} onChange={(e) => g({ source: e.target.value })} /></Field>
                  </div>
                </Panel>
                <Panel title="Mechanism overview" flush>
                  <div className="tree-group">Gear stages</div>
                  {stages.length === 0 ? <div className="list-item dim"><span className="name">No gear geometry mapped: backlash comes from the gearbox value and direct effects only.</span></div> : (
                    <table className="grid"><thead><tr><th>Stage</th><th className="num">Sun/Planet/Ring</th><th className="num">Ratio</th><th className="num">Module</th></tr></thead><tbody>
                      {stages.map((s) => <tr key={s.id}><td>{s.id}</td><td className="num">{s.sun_teeth}/{s.planet_teeth}/{s.ring_teeth}</td><td className="num">{fmt(1 + s.ring_teeth / s.sun_teeth)}</td><td className="num">{s.module} mm</td></tr>)}
                      <tr><td><b>Total</b></td><td /><td className="num"><b>{fmt(stages.reduce((a, s) => a * (1 + s.ring_teeth / s.sun_teeth), 1))}</b></td><td /></tr>
                    </tbody></table>)}
                  <div className="tree-group">Tolerance bindings (reduced order)</div>
                  <table className="grid"><tbody>
                    {md.spec.effects.filter((e) => e.joint === active).map((e, i) => <tr key={i}><td>{e.tolerance}</td><td className="muted">→ {e.target.replace(/_/g, " ")}</td><td>{e.mode}</td></tr>)}
                    {md.spec.radial_supports.filter((r) => r.joint === active).map((r, i) => <tr key={`r${i}`}><td>bearing fits and clearance</td><td className="muted">→ radial play, tilt</td><td>span {fmt(r.bearing_span * 1000)} mm</td></tr>)}
                  </tbody></table>
                  <div className="tree-group">Held joints (ideal servo)</div>
                  {Object.keys(md.spec.held_joints).length === 0 ? <div className="list-item dim"><span className="name">none</span></div>
                    : Object.entries(md.spec.held_joints).map(([j, v]) => <div key={j} className="list-item"><span className="name">{j}</span><span className="mono">{fmt((v * 180) / Math.PI)}°</span></div>)}
                  <div className="tree-group">Assumptions</div>
                  <ul className="small muted" style={{ margin: "0 0 8px", paddingLeft: 26 }}>{md.spec.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul>
                </Panel>
              </div>)}
          {drive && task && (
            <Panel title="Task simulation on the nominal assembly" actions={<button className="btn primary small" disabled={running} onClick={run}><Play />{running ? "Simulating…" : "Run task"}</button>}>
              <div className="row">
                <div style={{ width: 330, flex: "none" }}><TaskEditor task={task} joints={driven} onChange={setTask} /></div>
                <div className="grow">
                  {!result ? <Empty title="Not simulated yet">Run the task to see joint motion, torque demand and positioning error of the nominal design.</Empty>
                    : !result.valid ? <Alert kind="bad">The simulation is invalid: {result.message}</Alert> : (<>
                      <div className="grid4" style={{ marginBottom: 8 }}>
                        {["backlash", "ee_error_max", "lost_motion", "torque_utilisation_peak"].filter((k) => k in result.metrics).map((k) => (
                          <Stat key={k} label={metricLabel(k)} value={metricFmt(k, result.metrics[k])} />))}
                      </div>
                      <TraceCharts r={result} /></>)}
                </div>
              </div>
            </Panel>)}
        </>);
      }}</Load>
    </div>
  );
}
