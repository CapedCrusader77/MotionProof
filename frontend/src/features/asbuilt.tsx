import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Crosshair, Play, Upload, X } from "lucide-react";
import { adv, api, type AnyJson } from "../lib/api";
import { isActive, useAsync, useJob } from "../hooks/useAsync";
import { useModel } from "../hooks/useModel";
import { useApp } from "../stores/app";
import { Alert, Badge, Empty, Field, Load, NeedSelection, Num, Panel, Spinner, fmt, pct, signed } from "../components/ui";
import { CameraLink, DeviationLegend, ScanView } from "../components/ScanViewer";
import { Histogram } from "../components/charts";

const DOF = ["rx", "ry", "rz", "tx", "ty", "tz"];

export function AsBuiltScreen() {
  const { modelId, go, notify } = useApp();
  const model = useModel();
  const scans = useAsync(modelId ? () => adv.artifacts("scan", undefined, modelId) : null, [modelId]);
  const built = useAsync(modelId ? () => adv.asBuilt(modelId) : null, [modelId]);
  const [scanId, setScanId] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const scan = useAsync(scanId ? () => adv.scan(scanId) : null, [scanId, tick]);
  const file = useRef<HTMLInputElement>(null);
  const [units, setUnits] = useState("");
  const [scanner, setScanner] = useState("");
  const [component, setComponent] = useState("");
  const [lock, setLock] = useState<string[]>([]);
  const [acceptRms, setAcceptRms] = useState(0.05);
  const [limit, setLimit] = useState(0.02);
  const [feature, setFeature] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useJob(jobId, (j) => {
    if (j.status !== "completed") notify("error", j.error ?? "job failed");
    setTick((t) => t + 1); scans.reload(); built.reload();
  });
  const link = useMemo(() => new CameraLink(), [scanId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (!scanId && scans.data?.length) setScanId(scans.data[0].id); }, [scans.data, scanId]);
  useEffect(() => { const c = scan.data?.registration?.component; if (c) setComponent(c); }, [scan.data]);
  if (!modelId) return <NeedSelection what="model" action={<button className="btn primary" onClick={() => go("projects")}>Open projects</button>} />;

  const upload = async (f: File | undefined) => {
    if (!f) return;
    try {
      const r = await adv.importScan(modelId, f, units, scanner, "");
      notify(r.units ? "ok" : "info", r.units ? `Scan ${r.id} imported` : `Scan ${r.id} imported without a unit: state the unit and re-import before alignment`);
      setScanId(r.id); scans.reload();
    } catch (e) { notify("error", (e as Error).message); }
  };
  const register = async () => {
    if (!scanId) return;
    try { setJobId((await adv.registerScan(scanId, { component: component || null, lock, accept_rms: acceptRms })).id); }
    catch (e) { notify("error", (e as Error).message); }
  };
  const feats = (model.data?.spec.features ?? []).filter((f) => f.geometry.kind === "cylinder" && (!component || f.component === component));
  const analyse = async () => {
    if (!scanId) return;
    const f = model.data?.spec.features.find((x) => x.id === feature);
    const cylinders = f && f.geometry.point && f.geometry.direction && f.geometry.radius ? [{
      feature: f.id, tolerance: model.data?.spec.tolerances.find((t) => t.feature === f.id)?.id ?? null,
      axis_point: f.geometry.point, axis_direction: f.geometry.direction, radius: f.geometry.radius,
      band: Math.max(0.2, f.geometry.radius * 0.05), start: f.geometry.length ? 1 : null,
      length: f.geometry.length ? Math.max(f.geometry.length - 2, 1) : null }] : [];
    try { setJobId((await adv.analyseScan(scanId, { limit, cylinders })).id); }
    catch (e) { notify("error", (e as Error).message); }
  };
  const decide = async (mid: string, status: "approved" | "rejected") => {
    if (!scanId) return;
    try { await adv.decide(scanId, mid, status); notify("ok", `Measurement ${status}`); setTick((t) => t + 1); built.reload(); }
    catch (e) { notify("error", (e as Error).message); }
  };
  const busy = isActive(job);
  const d = scan.data;
  const reg = d?.registration?.registration as AnyJson | undefined;
  const ana = d?.analysis as AnyJson | null | undefined;
  const usedLimit: number = ana?.deviation?.specification?.limit_mm ?? limit;
  const meshUrl = component && model.data ? api.meshUrl(model.data.id, component, model.data.geometry_fingerprint) : null;
  const devHist = useMemo(() => {
    const v: number[] = ana?.deviation?.heatmap?.deviation ?? [];
    if (!v.length) return null;
    const lo = Math.min(...v), hi = Math.max(...v), n = 30, w = (hi - lo) / n || 1e-9;
    const count = new Array(n).fill(0);
    v.forEach((x) => { count[Math.min(n - 1, Math.floor((x - lo) / w))] += 1; });
    return { x: count.map((_, i) => lo + (i + 0.5) * w), count };
  }, [ana]);

  return (
    <div className="page">
      <div className="page-head"><h1>As-built inspection</h1><span className="sub">{model.data?.name}</span><span className="spacer" />
        <Field label="Scan unit"><select style={{ width: 110 }} value={units} onChange={(e) => setUnits(e.target.value)}>
          <option value="">Not stated</option><option>mm</option><option>cm</option><option>m</option><option value="in">inch</option></select></Field>
        <Field label="Scanner (optional)"><input className="input" style={{ width: 150 }} value={scanner} onChange={(e) => setScanner(e.target.value)} /></Field>
        <button className="btn primary" onClick={() => file.current?.click()}><Upload />Import point cloud</button>
        <input ref={file} type="file" hidden accept=".ply,.pcd,.xyz,.txt,.csv,.stl,.obj" onChange={(e) => void upload(e.target.files?.[0])} />
      </div>
      <Alert kind="info">Scans are aligned to the nominal component mesh and measured by fitted geometry. This is not a standards-conformant GD&T inspection.
        Approved measurements replace sampled dimensions in an as-built variant (reduced-order: the CAD mesh itself is not changed).</Alert>
      <div className="split" style={{ gridTemplateColumns: "280px minmax(0, 1fr) 340px" }}>
        <div className="col">
          <Panel title="Scans" flush>
            <Load state={scans}>{(list) => list.length === 0 ? <Empty title="No scans">Import a PLY, PCD, XYZ, CSV, STL or OBJ point cloud. State its unit: nothing is assumed.</Empty> : (
              <div className="list">{list.map((s) => (
                <button key={s.id} className={`list-item ${s.id === scanId ? "selected" : ""}`} onClick={() => setScanId(s.id)}>
                  <span className="name">{s.name}<br /><span className="faint small">{s.id}{s.summary?.points ? ` · ${s.summary.points} points` : ""}</span></span>
                  {s.summary?.synthetic && <Badge kind="warn">synthetic</Badge>}<Badge>{s.status}</Badge></button>))}</div>)}</Load>
          </Panel>
          {scanId && <Panel title="1 · Align to nominal" actions={<button className="btn primary small" disabled={busy || !d?.scan?.units} onClick={register}><Crosshair />Align</button>}>
            <div className="col" style={{ gap: 8 }}>
              {d && !d.scan?.units && <Alert kind="bad">This scan has no unit and cannot be compared with CAD.</Alert>}
              <Field label="Nominal component"><select value={component} onChange={(e) => setComponent(e.target.value)}>
                <option value="">Whole assembly</option>{model.data?.components.filter((c) => c.mesh).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
              <Field label="Locked degrees of freedom (datum constraints)">
                <div className="row wrap" style={{ gap: 6 }}>{DOF.map((x) => (
                  <label key={x} className="check"><input type="checkbox" checked={lock.includes(x)} onChange={(e) => setLock(e.target.checked ? [...lock, x] : lock.filter((y) => y !== x))} />{x}</label>))}</div></Field>
              <Field label="Acceptance RMS (mm)"><Num value={acceptRms} min={0.0001} onChange={setAcceptRms} /></Field>
              {!lock.length && <p className="small faint">No datum constraint: an unconstrained best fit spreads form error over the part.</p>}
            </div>
          </Panel>}
          {reg && <Panel title="2 · Measure" actions={<button className="btn primary small" disabled={busy || !reg} onClick={analyse}><Play />Analyse</button>}>
            <div className="col" style={{ gap: 8 }}>
              <Field label="Deviation limit (± mm)"><Num value={limit} min={0.0001} onChange={setLimit} /></Field>
              <Field label="Cylindrical feature to measure"><select value={feature} onChange={(e) => setFeature(e.target.value)}>
                <option value="">Deviation only</option>{feats.map((f) => <option key={f.id} value={f.id}>{f.id} ({f.type})</option>)}</select></Field>
              {feats.length === 0 && <p className="small faint">No registered cylindrical feature on this component. Register one under Features and datums.</p>}
            </div>
          </Panel>}
          {busy && <Spinner label="Processing on the backend" />}
        </div>
        <div className="col">
          {!scanId ? <Panel><Empty title="No scan selected" /></Panel> : (<>
            <div className="grid2" style={{ gridTemplateColumns: "1fr 1fr" }}>
              <ScanView id="nominal" link={link} meshUrl={meshUrl} caption="Nominal CAD" height={330} empty="Select the nominal component." />
              <ScanView id="asbuilt" link={link} meshUrl={meshUrl} meshOpacity={0.18} points={ana?.deviation?.heatmap?.points}
                values={ana?.deviation?.heatmap?.deviation} limit={usedLimit} missing={ana?.deviation?.missing} height={330}
                caption="As-built: scan deviation" empty={reg ? "Run Analyse to compute deviations." : "Align the scan first."} />
            </div>
            {ana && <DeviationLegend limit={usedLimit} />}
            <VirtualState modelId={modelId} component={component} />
            {devHist && <Panel title="Deviation distribution (signed, mm)"><Histogram hist={devHist} unit="mm" limit={usedLimit} failAbove height={150} /></Panel>}
          </>)}
        </div>
        <div className="col">
          <Panel title="Alignment quality">{!reg ? <Empty title="Not aligned" /> : (
            <div className="col" style={{ gap: 6 }}>
              <Alert kind={reg.valid_for_inspection ? "ok" : "bad"}>{reg.valid_for_inspection ? "Accepted for inspection." : "NOT valid for inspection: dimensions from this alignment must not be used."}</Alert>
              <dl className="kv"><dt>Method</dt><dd>{reg.method}</dd><dt>RMS residual</dt><dd>{fmt(reg.rms)} mm</dd><dt>Max residual</dt><dd>{fmt(reg.max_residual)} mm</dd>
                <dt>Points used</dt><dd>{reg.inliers} / {reg.points}</dd><dt>Outliers</dt><dd>{reg.outliers}</dd><dt>Iterations</dt><dd>{reg.iterations}</dd>
                <dt>Locked DOF</dt><dd>{reg.locked.join(", ") || "none"}</dd></dl>
              {reg.diagnostics.map((x: string, i: number) => <div key={i} className="small muted">• {x}</div>)}
              <div className="small faint">{(d?.registration?.processing ?? []).join(" · ")}</div>
            </div>)}</Panel>
          {ana && <Panel title="Deviation statistics">
            <dl className="kv"><dt>Mean</dt><dd>{signed(ana.deviation.mean)} mm</dd><dt>Std</dt><dd>{fmt(ana.deviation.std)} mm</dd><dt>RMS</dt><dd>{fmt(ana.deviation.rms)} mm</dd>
              <dt>Min / max</dt><dd>{signed(ana.deviation.min)} / {signed(ana.deviation.max)} mm</dd><dt>5 % / 95 %</dt><dd>{signed(ana.deviation.percentiles.p05)} / {signed(ana.deviation.percentiles.p95)}</dd>
              {ana.deviation.specification && <><dt>Within ±{fmt(ana.deviation.specification.limit_mm)} mm</dt><dd>{pct(ana.deviation.specification.fraction_within)}</dd></>}
              <dt>Surface coverage</dt><dd>{pct(ana.deviation.coverage.fraction_of_nominal_surface)}</dd></dl>
            <p className="small faint" style={{ marginTop: 6 }}>{ana.deviation.coverage.note}</p></Panel>}
          {ana && <Panel title="Measured features (review before use)" flush>
            {ana.measured.length === 0 ? <Empty title="No feature measured" /> : ana.measured.map((m: AnyJson) => (
              <div key={m.id} style={{ padding: "8px 10px", borderBottom: "1px solid var(--border)" }}>
                <div className="row center"><b className="grow">{m.feature ?? m.id}</b><Badge kind={m.status === "approved" ? "ok" : m.status === "rejected" ? "bad" : "warn"}>{m.status}</Badge></div>
                {m.value !== undefined && <dl className="kv"><dt>Diameter</dt><dd>{fmt(m.value, 7)} mm</dd><dt>Std error</dt><dd>{fmt(m.uncertainty, 2)} mm</dd>
                  <dt>Points</dt><dd>{m.points}</dd><dt>Arc covered</dt><dd>{fmt(m.fit?.arc_coverage_deg, 3)}°</dd><dt>Replaces</dt><dd>{m.tolerance ?? "-"}</dd></dl>}
                {(m.notes ?? []).map((n: string, i: number) => <div key={i} className="small muted">• {n}</div>)}
                {m.status === "pending" && <div className="row" style={{ marginTop: 6 }}>
                  <button className="btn small" onClick={() => decide(m.id, "approved")}><Check />Approve</button>
                  <button className="btn small danger" onClick={() => decide(m.id, "rejected")}><X />Reject</button></div>}
              </div>))}
          </Panel>}
          <Panel title="As-built model">
            <Load state={built}>{(b) => b.used.length === 0 ? <Empty title="No approved measurements">Approved scan measurements build the as-built variant.</Empty> : (
              <div className="col" style={{ gap: 6 }}>
                <table className="grid"><tbody>{b.used.map((u: AnyJson) => <tr key={u.id}><td>{u.tolerance}</td><td className="num">{fmt(u.value, 7)} {u.unit}</td>
                  <td>{u.in_spec ? <Badge kind="ok">in spec</Badge> : <Badge kind="bad">out of spec</Badge>}</td></tr>)}</tbody></table>
                {(b.variant?.violations ?? []).map((v: AnyJson, i: number) => <Alert key={i} kind="bad">{v.subject}: {v.message}</Alert>)}
                <p className="small faint">{b.representation}</p></div>)}</Load>
          </Panel>
        </div>
      </div>
    </div>
  );
}

function VirtualState({ modelId, component }: { modelId: string; component: string }) {
  const tol = useAsync(() => api.tolerances(modelId), [modelId]);
  const rows = (tol.data?.tolerances ?? []).filter((t) => !component || t.component === component);
  return (
    <Panel title="Virtual as-manufactured state (third view)">
      {rows.length === 0 ? <Empty title="No tolerances on this component">The virtual state exists only where tolerances are defined; no geometry is invented.</Empty> : (
        <div className="col" style={{ gap: 6 }}>
          <p className="small muted">Virtual variants change these dimensions inside the model (Level C relations, or Level A regeneration for the reference design under Virtual assemblies). No modified mesh is drawn here.</p>
          <table className="grid"><thead><tr><th>Tolerance</th><th className="num">Lower limit</th><th className="num">Upper limit</th><th>Unit</th><th>Distribution</th></tr></thead><tbody>
            {rows.map((t) => <tr key={t.id}><td>{t.id}</td><td className="num">{fmt(t.nominal + t.lower, 7)}</td><td className="num">{fmt(t.nominal + t.upper, 7)}</td><td>{t.unit}</td><td>{t.distribution.type}</td></tr>)}</tbody></table>
        </div>)}
    </Panel>
  );
}
