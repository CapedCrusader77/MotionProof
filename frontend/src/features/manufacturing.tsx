import { useEffect, useMemo, useState } from "react";
import { Plus, RefreshCw, Trash2 } from "lucide-react";
import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import { useModel, usePose } from "../hooks/useModel";
import { useApp } from "../stores/app";
import type { Distribution, Tolerance, ToleranceReviewRow, Variant } from "../lib/types";
import { Alert, Badge, Empty, Field, Load, NeedSelection, Num, Panel, fmt, pct, signed } from "../components/ui";
import { Viewer, type Marker } from "../components/Viewer";

const CHARACTERISTICS = ["length", "diameter", "thickness", "centre_distance", "gear_dimension", "position_x", "position_y",
  "radial_position", "runout", "concentricity", "phase", "parallelism", "perpendicularity", "angularity", "flatness",
  "circularity", "offset", "angular_misalignment", "radial_clearance", "axial_clearance", "backlash", "efficiency",
  "friction", "stiffness", "torque_scale", "other"];
const confKind = { specified: "ok", measured: "ok", estimated: "info", assumed: "warn" } as const;

function defaultDistribution(type: Distribution["type"], t: Tolerance): Distribution {
  const lo = t.nominal + t.lower, hi = t.nominal + t.upper, mid = (lo + hi) / 2, sd = Math.max((hi - lo) / 6, 1e-9);
  switch (type) {
    case "uniform": return { type, low: lo, high: hi };
    case "normal": return { type, mean: mid, std: sd };
    case "truncated_normal": return { type, mean: mid, std: sd, low: lo, high: hi };
    case "lognormal": return { type, mu: Math.log(Math.max(mid, 1e-9)), sigma: 0.05 };
    case "discrete": return { type, values: [lo, mid, hi], probabilities: null };
    case "empirical": return { type, samples: [lo, mid, hi] };
  }
}

function DistributionEditor({ d, onChange }: { d: Distribution; onChange: (d: Distribution) => void }) {
  const num = (label: string, key: string) => (
    <Field label={label} key={key}><Num value={(d as unknown as Record<string, number>)[key]} onChange={(v) => onChange({ ...d, [key]: v } as Distribution)} /></Field>);
  const list = (label: string, key: "values" | "samples") => (
    <Field label={label} wide hint="Comma-separated numbers"><input className="input mono" defaultValue={((d as unknown as Record<string, number[]>)[key] ?? []).join(", ")}
      onBlur={(e) => onChange({ ...d, [key]: e.target.value.split(/[,\s]+/).filter(Boolean).map(Number).filter(Number.isFinite) } as Distribution)} /></Field>);
  switch (d.type) {
    case "uniform": return <>{num("Low", "low")}{num("High", "high")}</>;
    case "normal": return <>{num("Mean", "mean")}{num("Standard deviation", "std")}</>;
    case "truncated_normal": return <>{num("Mean", "mean")}{num("Standard deviation", "std")}{num("Lower truncation", "low")}{num("Upper truncation", "high")}</>;
    case "lognormal": return <>{num("mu (of ln x)", "mu")}{num("sigma (of ln x)", "sigma")}</>;
    case "discrete": return list("Values", "values");
    case "empirical": return list("Measured samples", "samples");
  }
}

function DensityChart({ row, t }: { row: ToleranceReviewRow; t: Tolerance }) {
  const data = row.curve.x.map((x, i) => ({ x, density: row.curve.density[i] }));
  return (
    <ResponsiveContainer width="100%" height={150}>
      <AreaChart data={data} margin={{ top: 14, right: 12, bottom: 12, left: 0 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="x" type="number" domain={["dataMin", "dataMax"]} tickFormatter={(v: number) => fmt(v, 6)} label={{ value: t.unit, position: "insideBottom", offset: -6 }} />
        <YAxis width={10} tick={false} />
        <Tooltip formatter={(v) => fmt(Number(v))} labelFormatter={(v) => `${fmt(Number(v), 7)} ${t.unit}`} contentStyle={{ background: "var(--surface)", border: "1px solid var(--border-strong)", fontSize: 12 }} />
        <Area dataKey="density" stroke="var(--mp-data)" fill="color-mix(in srgb, var(--mp-data) 18%, transparent)" isAnimationActive={false} />
        <ReferenceLine x={row.lower_limit} stroke="var(--bad)" strokeDasharray="4 3" label={{ value: "LSL", fontSize: 10, fill: "var(--bad)", position: "top" }} />
        <ReferenceLine x={row.upper_limit} stroke="var(--bad)" strokeDasharray="4 3" label={{ value: "USL", fontSize: 10, fill: "var(--bad)", position: "top" }} />
        <ReferenceLine x={row.design_value} stroke="var(--ok)" label={{ value: "design", fontSize: 10, fill: "var(--ok)", position: "top" }} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

// ---------------------------------------------------------------- tolerances

export function TolerancesScreen() {
  const { modelId, go, notify } = useApp();
  const model = useModel();
  const list = useAsync(modelId ? () => api.tolerances(modelId) : null, [modelId]);
  const pose = usePose(modelId, {});
  const [selected, setSelected] = useState<string | null>(null);
  const [draft, setDraft] = useState<Tolerance | null>(null);
  const [isNew, setIsNew] = useState(false);
  const [filter, setFilter] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (isNew) return;
    const t = list.data?.tolerances.find((x) => x.id === selected);
    setDraft(t ? structuredClone(t) : null);
  }, [selected, list.data, isNew]);
  const markers = useMemo<Marker[]>(() => {
    const f = model.data?.spec.features.find((x) => x.id === draft?.feature);
    return f && f.geometry.kind !== "none" ? [{ component: f.component, geometry: f.geometry }] : [];
  }, [model.data, draft?.feature]);
  if (!modelId) return <NeedSelection what="model" action={<button className="btn primary" onClick={() => go("projects")}>Open projects</button>} />;

  const save = async () => {
    if (!draft) return;
    setBusy(true);
    try {
      if (isNew) await api.createTolerance(modelId, draft); else await api.updateTolerance(modelId, draft);
      notify("ok", `Tolerance ${draft.id} saved. Existing experiments keep their own snapshot.`);
      setIsNew(false); setSelected(draft.id); list.reload(); model.reload();
    } catch (e) { notify("error", (e as Error).message); } finally { setBusy(false); }
  };
  const remove = async () => {
    if (!draft) return;
    try { await api.deleteTolerance(modelId, draft.id); notify("ok", `Tolerance ${draft.id} deleted`); setSelected(null); list.reload(); model.reload(); }
    catch (e) { notify("error", (e as Error).message); }
  };
  const create = () => {
    const comp = model.data?.components[0]?.id ?? "";
    setIsNew(true); setSelected(null);
    // a blank entry: every value must be supplied by the engineer, nothing is pre-filled as if specified
    setDraft({ id: "", component: comp, feature: null, parameter: "", characteristic: "diameter", category: "dimensional", nominal: NaN, upper: NaN, lower: NaN,
      unit: "mm", datum: null, zone_group: null, distribution: { type: "uniform", low: NaN, high: NaN }, correlation_group: null, source: "", confidence: "estimated",
      verification: "unverified", process: null, note: null });
  };
  const patch = (p: Partial<Tolerance>) => draft && setDraft({ ...draft, ...p });
  const draftValid = draft !== null && draft.id.trim() !== "" && draft.parameter.trim() !== "" && draft.source.trim() !== ""
    && [draft.nominal, draft.upper, draft.lower].every(Number.isFinite) && draft.upper >= draft.lower;

  return (
    <div className="page">
      <div className="page-head"><h1>Manufacturing tolerances</h1><span className="sub">{model.data?.name}</span><span className="spacer" />
        <input className="input" style={{ width: 200 }} placeholder="Filter by id or component" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter tolerances" />
        <button className="btn primary" onClick={create}><Plus />Add tolerance</button></div>
      <Load state={list}>{(data) => {
        const rows = data.tolerances.filter((t) => `${t.id} ${t.component} ${t.parameter}`.toLowerCase().includes(filter.toLowerCase()));
        const review = Object.fromEntries(data.review.map((r) => [r.id, r]));
        const rev = draft ? review[draft.id] : undefined;
        const mine = data.findings.filter((f) => f.tolerance === draft?.id);
        return (
          <div className="split two" style={{ gridTemplateColumns: "minmax(0, 1fr) 400px" }}>
            <div className="col">
              <Panel title={`Tolerance table (${rows.length} of ${data.tolerances.length})`} flush style={{ maxHeight: 430 }}>
                {data.tolerances.length === 0 ? <Empty title="No tolerances defined" action={<button className="btn primary" onClick={create}>Add the first tolerance</button>}>
                  MotionProof never invents tolerances: enter them from your drawings or process data.</Empty> : (
                  <div className="table-wrap"><table className="grid"><thead><tr><th>Id</th><th>Component</th><th>Parameter</th><th className="num">Nominal</th><th className="num">Lower</th><th className="num">Upper</th><th>Unit</th><th>Datum</th><th>Distribution</th><th className="num">Out of spec</th><th>Confidence</th></tr></thead><tbody>
                    {rows.map((t) => (
                      <tr key={t.id} className={`click ${selected === t.id ? "selected" : ""}`} onClick={() => { setIsNew(false); setSelected(t.id); }}>
                        <td>{t.id}</td><td className="muted">{t.component}</td><td>{t.parameter}</td><td className="num">{fmt(t.nominal, 6)}</td>
                        <td className="num">{signed(t.lower)}</td><td className="num">{signed(t.upper)}</td><td>{t.unit}</td><td>{t.datum ?? "–"}</td>
                        <td>{t.distribution.type.replace("_", " ")}</td><td className="num">{pct(review[t.id]?.fraction_out_of_spec, 2)}</td>
                        <td><Badge kind={confKind[t.confidence]}>{t.confidence}</Badge></td></tr>))}
                  </tbody></table></div>)}
              </Panel>
              <div className="grid2">
                <Panel title="Validation" flush style={{ maxHeight: 260 }}>
                  {data.findings.length === 0 ? <Empty title="No findings" /> : (
                    <table className="grid"><tbody>{data.findings.map((f, i) => (
                      <tr key={i} className={f.tolerance ? "click" : ""} onClick={() => { if (f.tolerance) { setIsNew(false); setSelected(f.tolerance); } }}>
                        <td><Badge kind={f.severity === "error" ? "bad" : f.severity === "warning" ? "warn" : "info"}>{f.severity}</Badge></td>
                        <td className="mono">{f.tolerance ?? "model"}</td><td className="wrap">{f.message}</td></tr>))}</tbody></table>)}
                </Panel>
                <Panel title="Fits and correlations" flush style={{ maxHeight: 260 }}>
                  <table className="grid"><thead><tr><th>Fit</th><th>Class</th><th className="num">Min clearance</th><th className="num">Max clearance</th></tr></thead><tbody>
                    {data.fits.length === 0 && <tr><td colSpan={4} className="muted">No fits defined.</td></tr>}
                    {data.fits.map((f) => <tr key={f.fit}><td>{f.fit}</td><td><Badge kind={f.class === "clearance" ? "ok" : f.class === "transition" ? "warn" : "info"}>{f.class}</Badge></td>
                      <td className="num">{signed(f.min_clearance * 1000)} µm</td><td className="num">{signed(f.max_clearance * 1000)} µm</td></tr>)}
                  </tbody></table>
                  <table className="grid"><thead><tr><th>Correlated pair</th><th className="num">Coefficient</th><th>Basis</th></tr></thead><tbody>
                    {data.correlations.length === 0 && <tr><td colSpan={3} className="muted">No correlations: variables are sampled independently.</td></tr>}
                    {data.correlations.map((c, i) => <tr key={i}><td>{c.parameters.join(" ~ ")}</td><td className="num">{c.coefficient}</td><td><Badge kind={c.basis === "measured" ? "ok" : "warn"}>{c.basis}</Badge></td></tr>)}
                  </tbody></table>
                </Panel>
              </div>
            </div>
            <div className="col">
              <Panel title={isNew ? "New tolerance" : draft ? draft.id : "Tolerance editor"} actions={draft && <>
                {!isNew && <button className="btn small danger" onClick={remove} aria-label="Delete tolerance"><Trash2 /></button>}
                <button className="btn primary small" disabled={!draftValid || busy} onClick={save}>Save</button></>}>
                {!draft ? <Empty title="No tolerance selected">Select a row to edit its specification and distribution.</Empty> : (
                  <div className="col">
                    <div className="form">
                      <Field label="Id"><input className="input" value={draft.id} disabled={!isNew} onChange={(e) => patch({ id: e.target.value })} /></Field>
                      <Field label="Parameter"><input className="input" value={draft.parameter} onChange={(e) => patch({ parameter: e.target.value })} /></Field>
                      <Field label="Component"><select value={draft.component} onChange={(e) => patch({ component: e.target.value })}>
                        {[...new Set([draft.component, ...(model.data?.components.map((c) => c.id) ?? [])])].filter(Boolean).map((c) => <option key={c}>{c}</option>)}</select></Field>
                      <Field label="Feature"><select value={draft.feature ?? ""} onChange={(e) => patch({ feature: e.target.value || null })}><option value="">none</option>
                        {model.data?.spec.features.map((f) => <option key={f.id}>{f.id}</option>)}</select></Field>
                      <Field label="Category"><select value={draft.category} onChange={(e) => patch({ category: e.target.value as Tolerance["category"] })}>
                        {["dimensional", "geometric", "assembly", "mechanical"].map((c) => <option key={c}>{c}</option>)}</select></Field>
                      <Field label="Characteristic"><select value={draft.characteristic} onChange={(e) => patch({ characteristic: e.target.value })}>
                        {CHARACTERISTICS.map((c) => <option key={c} value={c}>{c.replace(/_/g, " ")}</option>)}</select></Field>
                    </div>
                    <div className="form three">
                      <Field label="Nominal"><Num value={draft.nominal} onChange={(v) => patch({ nominal: v })} /></Field>
                      <Field label="Lower deviation"><Num value={draft.lower} onChange={(v) => patch({ lower: v })} /></Field>
                      <Field label="Upper deviation"><Num value={draft.upper} onChange={(v) => patch({ upper: v })} /></Field>
                      <Field label="Unit"><input className="input" value={draft.unit} onChange={(e) => patch({ unit: e.target.value })} /></Field>
                      <Field label="Datum"><select value={draft.datum ?? ""} onChange={(e) => patch({ datum: e.target.value || null })}><option value="">none</option>
                        {model.data?.spec.datums.map((d) => <option key={d.id}>{d.id}</option>)}</select></Field>
                      <Field label="Zone group"><input className="input" value={draft.zone_group ?? ""} onChange={(e) => patch({ zone_group: e.target.value || null })} /></Field>
                    </div>
                    {Number.isFinite(draft.nominal) && <p className="small muted">Limits: {fmt(draft.nominal + draft.lower, 7)} … {fmt(draft.nominal + draft.upper, 7)} {draft.unit}</p>}
                    <h3>Distribution</h3>
                    <div className="form">
                      <Field label="Type" wide><select value={draft.distribution.type} onChange={(e) => patch({ distribution: defaultDistribution(e.target.value as Distribution["type"], draft) })}>
                        {["uniform", "normal", "truncated_normal", "lognormal", "discrete", "empirical"].map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}</select></Field>
                      <DistributionEditor d={draft.distribution} onChange={(d) => patch({ distribution: d })} />
                    </div>
                    {rev && !isNew && <><DensityChart row={rev} t={draft} />
                      <dl className="kv"><dt>Mean</dt><dd>{fmt(rev.mean, 7)}</dd><dt>Standard deviation</dt><dd>{fmt(rev.std)}</dd>
                        <dt>Outside limits</dt><dd>{pct(rev.fraction_out_of_spec, 3)}</dd>
                        {rev.capability && <><dt>Cp / Cpk ({rev.capability.basis})</dt><dd>{fmt(rev.capability.cp, 3)} / {fmt(rev.capability.cpk, 3)}</dd></>}</dl>
                      <p className="small faint">Chart reflects the saved definition; save to refresh.</p></>}
                    <h3>Provenance</h3>
                    <div className="form">
                      <Field label="Source" wide><input className="input" value={draft.source} placeholder="Drawing number, standard, measurement report…" onChange={(e) => patch({ source: e.target.value })} /></Field>
                      <Field label="Confidence"><select value={draft.confidence} onChange={(e) => patch({ confidence: e.target.value as Tolerance["confidence"] })}>
                        {["specified", "measured", "estimated", "assumed"].map((c) => <option key={c}>{c}</option>)}</select></Field>
                      <Field label="Verification"><select value={draft.verification} onChange={(e) => patch({ verification: e.target.value as Tolerance["verification"] })}>
                        {["unverified", "measured", "inspected"].map((c) => <option key={c}>{c}</option>)}</select></Field>
                      <Field label="Correlation group" wide><input className="input" value={draft.correlation_group ?? ""} onChange={(e) => patch({ correlation_group: e.target.value || null })} /></Field>
                    </div>
                    {mine.map((f, i) => <Alert key={i} kind={f.severity === "error" ? "bad" : f.severity === "warning" ? "warn" : "info"}>{f.message}</Alert>)}
                  </div>)}
              </Panel>
              {model.data && markers.length > 0 && <Viewer modelId={model.data.id} stamp={model.data.geometry_fingerprint} components={model.data.components}
                pose={pose} markers={markers} selected={markers[0].component} height={230} legend="Mapped feature" />}
            </div>
          </div>);
      }}</Load>
    </div>
  );
}

// ---------------------------------------------------------------- virtual assembly

export function VirtualAssemblyScreen() {
  const { modelId, go, notify } = useApp();
  const model = useModel();
  const [method, setMethod] = useState("monte_carlo");
  const [samples, setSamples] = useState(20);
  const [seed, setSeed] = useState(1);
  const [request, setRequest] = useState(0);
  const set = useAsync(modelId && request > 0 ? () => api.generateVariants(modelId, method, samples, seed) : null, [modelId, request]);
  const [picked, setPicked] = useState<Variant | null>(null);
  const detail = useAsync(modelId && picked ? () => api.variantDetail(modelId, picked.values) : null, [modelId, picked?.id]);
  const [mode, setMode] = useState<"overlay" | "nominal" | "variant">("overlay");
  const [magnify, setMagnify] = useState(200);
  const nominalPose = usePose(modelId, {});
  const variantPose = usePose(picked ? modelId : null, {}, picked?.values);
  useEffect(() => { if (set.error) notify("error", set.error); }, [set.error, notify]);
  if (!modelId) return <NeedSelection what="model" action={<button className="btn primary" onClick={() => go("projects")}>Open projects</button>} />;
  const hasTol = (model.data?.spec.tolerances.length ?? 0) > 0;
  const joint = (v: Variant) => Object.values(v.joints)[0];
  const worst = set.data ? [...set.data.variants].sort((a, b) => (joint(b)?.backlash ?? 0) - (joint(a)?.backlash ?? 0))[0] : null;

  const changed = new Set<string>([...(detail.data?.geometry?.changed_components.map((c) => c.component) ?? []),
    ...(detail.data?.deviations.slice(0, 8).map((d) => d.component) ?? [])]);
  const tint: Record<string, string> = {};
  if (mode !== "nominal") changed.forEach((c) => { tint[c] = "#d9773a"; });

  return (
    <div className="page">
      <div className="page-head"><h1>Virtual as-manufactured assemblies</h1><span className="sub">{model.data?.name}</span><span className="spacer" />
        <Field label="Sampling"><select value={method} onChange={(e) => setMethod(e.target.value)} style={{ width: 150 }}>
          <option value="monte_carlo">Monte Carlo</option><option value="latin_hypercube">Latin hypercube</option><option value="boundary">Boundary values</option><option value="corners">Worst-case corners</option></select></Field>
        <Field label="Variants"><div style={{ width: 80 }}><Num value={samples} min={1} max={500} step={1} onChange={setSamples} /></div></Field>
        <Field label="Seed"><div style={{ width: 80 }}><Num value={seed} step={1} onChange={setSeed} /></div></Field>
        <button className="btn primary" disabled={!hasTol || set.loading || !(samples >= 1 && samples <= 500)} onClick={() => { setPicked(null); setRequest((r) => r + 1); }}><RefreshCw />Generate</button>
      </div>
      {!hasTol && <Alert kind="warn">This model has no tolerances. Define them in Manufacturing before generating variants.</Alert>}
      <div className="split" style={{ gridTemplateColumns: "330px minmax(0, 1fr) 340px" }}>
        <Panel title="Variants" flush foot={set.data ? `${set.data.method}, seed ${set.data.seed}${set.data.note ? " · " + set.data.note : ""}` : undefined}>
          {request === 0 ? <Empty title="No variants generated">Choose a sampling method and generate virtual manufactured assemblies from the tolerance distributions.</Empty> : (
            <Load state={set} label="Generating variants">{(d) => (
              <table className="grid"><thead><tr><th>Variant</th><th className="num">Backlash mrad</th><th className="num">Play µm</th><th>Status</th></tr></thead><tbody>
                {d.variants.map((v) => { const j = joint(v); return (
                  <tr key={v.id} className={`click ${picked?.id === v.id ? "selected" : ""}`} onClick={() => setPicked(v)}>
                    <td>{v.id}{worst?.id === v.id && <> <Badge kind="info" title="Largest backlash in this set">worst</Badge></>}</td>
                    <td className="num">{j ? fmt(j.backlash * 1e3) : "–"}</td><td className="num">{j ? fmt(j.radial_play * 1e6) : "–"}</td>
                    <td>{v.violations.length > 0 ? <Badge kind="bad">{v.violations[0].category.replace(/_/g, " ")}</Badge> : v.out_of_spec.length > 0 ? <Badge kind="warn">out of spec</Badge> : <Badge kind="ok">assembles</Badge>}</td></tr>); })}
              </tbody></table>)}</Load>)}
        </Panel>
        <div className="col">
          <div className="row center">
            <div className="steps" style={{ width: 300 }}>{(["overlay", "nominal", "variant"] as const).map((k) => (
              <button key={k} className={`step ${mode === k ? "active" : ""}`} onClick={() => setMode(k)}>{k === "overlay" ? "Overlay" : k === "nominal" ? "Nominal" : "Variant"}</button>))}</div>
            <label className="row center muted small" style={{ gap: 6 }}>Deviation magnification ×{magnify}
              <input type="range" min={1} max={1000} step={1} value={magnify} onChange={(e) => setMagnify(Number(e.target.value))} aria-label="Deviation magnification" /></label>
          </div>
          {model.data && <Viewer modelId={model.data.id} stamp={model.data.geometry_fingerprint} components={model.data.components}
            pose={mode === "variant" && variantPose ? variantPose : nominalPose} tint={tint}
            overlay={mode === "overlay" && picked && variantPose ? { pose: variantPose, magnify, changed } : null}
            legend={picked ? `Orange: components with deviating features · overlay wireframe shows the variant pose magnified ×${magnify} (Level C misalignment)` : "Select a variant to compare it with the nominal assembly"} />}
        </div>
        <Panel title={picked ? `Variant ${picked.id}` : "Feature deviations"} flush>
          {!picked ? <Empty title="No variant selected">Select a variant to see exactly what changed.</Empty> : (
            <Load state={detail} label="Regenerating geometry">{(d) => (
              <div>
                {d.variant.violations.map((v, i) => <div key={i} style={{ padding: 8 }}><Alert kind="bad"><b>{v.subject}</b>: {v.message}</Alert></div>)}
                <div className="tree-group">Fits</div>
                <table className="grid"><tbody>{d.variant.fits.map((f) => <tr key={f.fit}><td>{f.fit}</td><td><Badge kind={f.state === "clearance" ? "ok" : "warn"}>{f.state}</Badge></td><td className="num">{signed(f.clearance * 1000)} µm</td></tr>)}</tbody></table>
                {d.geometry && <><div className="tree-group">Regenerated geometry (Level A, measured)</div>
                  <table className="grid"><tbody>
                    {Object.entries(d.geometry.measured_dimensions_mm).map(([k, v]) => <tr key={k}><td>{k.replace(/_/g, " ")}</td><td className="num">{fmt(v, 8)} mm</td></tr>)}
                    {Object.entries(d.geometry.interfaces).map(([k, v]) => <tr key={k}><td>{k.replace(/_/g, " ")} radial clearance</td><td className="num">{signed(v.radial_clearance_mm * 1000)} µm</td></tr>)}
                    {Object.entries(d.geometry.interfaces).filter(([, v]) => v.interference_mm3 > 1e-9).map(([k, v]) => <tr key={`${k}i`}><td>{k.replace(/_/g, " ")} interference volume</td><td className="num neg">{fmt(v.interference_mm3)} mm³</td></tr>)}
                  </tbody></table></>}
                <div className="tree-group">Gear stages (Level C, reduced order)</div>
                <table className="grid"><tbody>{d.variant.stages.map((s) => <tr key={s.stage}><td>{s.stage}</td><td className="num">{fmt(s.backlash_angle * 1e3)} mrad</td>
                  <td className="num">{fmt(s.min_mesh_backlash_mm * 1e3)} µm mesh</td><td>{s.binding ? <Badge kind="bad">binds</Badge> : <Badge kind="ok">free</Badge>}</td></tr>)}</tbody></table>
                <div className="tree-group">Dimension deviations</div>
                <table className="grid"><thead><tr><th>Tolerance</th><th className="num">Nominal</th><th className="num">Actual</th><th className="num">Δ</th><th /></tr></thead><tbody>
                  {d.deviations.map((x) => <tr key={x.tolerance}><td title={x.component}>{x.tolerance}</td><td className="num">{fmt(x.nominal, 6)}</td><td className="num">{fmt(x.actual, 6)}</td>
                    <td className="num">{signed(x.deviation, 3)}</td><td>{x.in_spec ? "" : <Badge kind="warn">out</Badge>}</td></tr>)}
                </tbody></table>
                <p className="small faint" style={{ padding: 8 }}>{d.levels_note}</p>
              </div>)}</Load>)}
        </Panel>
      </div>
    </div>
  );
}
