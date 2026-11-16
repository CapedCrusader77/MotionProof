import { Fragment, useEffect, useMemo, useState } from "react";
import { Plus, RefreshCw, Trash2 } from "lucide-react";
import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import { useModel, usePose } from "../hooks/useModel";
import { useApp } from "../stores/app";
import type { Distribution, Tolerance, ToleranceReviewRow, Variant } from "../lib/types";
import { Alert, Badge, Empty, Field, Load, NeedSelection, Num, fmt, pct, signed } from "../components/ui";
import { Viewer, type Marker } from "../components/Viewer";

const CHARACTERISTICS = ["length", "diameter", "thickness", "centre_distance", "gear_dimension", "position_x", "position_y",
  "radial_position", "runout", "concentricity", "phase", "parallelism", "perpendicularity", "angularity", "flatness",
  "circularity", "offset", "angular_misalignment", "radial_clearance", "axial_clearance", "backlash", "efficiency",
  "friction", "stiffness", "torque_scale", "other"];

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
        <XAxis dataKey="x" type="number" domain={["dataMin", "dataMax"]} tickFormatter={(v: number) => fmt(v, 4)} label={{ value: t.unit, position: "insideBottom", offset: -6 }} />
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
  const [dock, setDock] = useState<"findings" | "fits" | "corr">("findings");
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
    <div className="ws">
      <div className="ws-head">
        <h1>Tolerances</h1><span className="meta">{model.data?.name}</span>
        {list.data && <span className="meta">{list.data.tolerances.length} tolerances · {list.data.fits.length} fits · {list.data.correlations.length} correlations</span>}
        <span className="spacer" />
        <input className="input" style={{ width: 220 }} placeholder="Filter by id, component, parameter" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter tolerances" />
        <button className="btn primary" onClick={create}><Plus />Add tolerance</button>
      </div>
      <Load state={list}>{(data) => {
        const rows = data.tolerances.filter((t) => `${t.id} ${t.component} ${t.parameter}`.toLowerCase().includes(filter.toLowerCase()));
        const review = Object.fromEntries(data.review.map((r) => [r.id, r]));
        const rev = draft ? review[draft.id] : undefined;
        const mine = data.findings.filter((f) => f.tolerance === draft?.id);
        const byConf = (["specified", "measured", "estimated", "assumed"] as const).map((c) => [c, data.tolerances.filter((t) => t.confidence === c).length] as const);
        const pairs = draft ? data.correlations.filter((c) => c.parameters.includes(draft.id)) : [];
        return (
          <div className="tol-body">
            <div className="tol-main">
              <div className="tol-table">
                {data.tolerances.length === 0 ? <Empty title="No tolerances defined" action={<button className="btn primary" onClick={create}>Add the first tolerance</button>}>
                  MotionProof never invents tolerances: enter them from your drawings or process data.</Empty> : (
                  <table className="grid"><thead><tr><th>Id</th><th className="col-opt">Component</th><th>Parameter</th><th className="num">Nominal</th><th className="num">Lower</th>
                    <th className="num">Upper</th><th>Unit</th><th>Datum</th><th>Distribution within limits</th><th className="num" title="Probability of a part outside the limits under this distribution">P(out)</th><th>Evidence</th></tr></thead><tbody>
                    {rows.map((t) => (
                      <tr key={t.id} className={`click ${selected === t.id ? "selected" : ""}`} onClick={() => { setIsNew(false); setSelected(t.id); }}>
                        <td className="mono">{t.id}</td><td className="muted col-opt">{t.component}</td><td>{t.parameter}</td><td className="num">{fmt(t.nominal, 6)}</td>
                        <td className="num">{signed(t.lower)}</td><td className="num">{signed(t.upper)}</td><td className="muted">{t.unit}</td><td>{t.datum ?? <span className="faint">–</span>}</td>
                        <td><span className="dist-cell">{review[t.id] && <Spark row={review[t.id]} />}<span className="muted">{t.distribution.type.replace("_", " ")}</span></span></td>
                        <td className="num">{pct(review[t.id]?.fraction_out_of_spec, 2)}</td>
                        <td><Evidence c={t.confidence} /></td></tr>))}
                  </tbody></table>)}
              </div>
              <div className="tol-dock">
                <div className="ws-tabs" role="tablist" style={{ justifyContent: "flex-start" }}>
                  {([["findings", `Validation findings (${data.findings.length})`], ["fits", `Fits (${data.fits.length})`], ["corr", `Correlations (${data.correlations.length})`]] as const).map(([k, l]) =>
                    <button key={k} role="tab" style={{ flex: "none", padding: "8px 14px" }} aria-selected={dock === k} onClick={() => setDock(k)}>{l}</button>)}
                </div>
                <div style={{ overflow: "auto", minHeight: 0 }}>
                  {dock === "findings" && (data.findings.length === 0 ? <p className="muted small" style={{ padding: 12 }}>No findings.</p> : (
                    <table className="grid"><tbody>{data.findings.map((f, i) => (
                      <tr key={i} className={f.tolerance ? "click" : ""} onClick={() => { if (f.tolerance) { setIsNew(false); setSelected(f.tolerance); } }}>
                        <td style={{ width: 90 }}><Badge kind={f.severity === "error" ? "bad" : f.severity === "warning" ? "warn" : "info"}>{f.severity}</Badge></td>
                        <td className="mono" style={{ width: 220 }}>{f.tolerance ?? "model"}</td><td className="wrap">{f.message}</td></tr>))}</tbody></table>))}
                  {dock === "fits" && <table className="grid"><thead><tr><th>Fit</th><th>Class</th><th className="num">Min clearance (µm)</th><th className="num">Max clearance (µm)</th></tr></thead><tbody>
                    {data.fits.length === 0 && <tr><td colSpan={4} className="muted">No fits defined.</td></tr>}
                    {data.fits.map((f) => <tr key={f.fit}><td className="mono">{f.fit}</td><td>{f.class}</td>
                      <td className="num">{signed(f.min_clearance * 1000)}</td><td className="num">{signed(f.max_clearance * 1000)}</td></tr>)}
                  </tbody></table>}
                  {dock === "corr" && <table className="grid"><thead><tr><th>Correlated pair</th><th className="num">Coefficient</th><th>Basis</th></tr></thead><tbody>
                    {data.correlations.length === 0 && <tr><td colSpan={3} className="muted">No correlations: variables are sampled independently.</td></tr>}
                    {data.correlations.map((c, i) => <tr key={i}><td className="mono">{c.parameters.join(" ~ ")}</td><td className="num">{c.coefficient}</td><td><Evidence c={c.basis === "measured" ? "measured" : "assumed"} /></td></tr>)}
                  </tbody></table>}
                </div>
              </div>
            </div>
            <aside className="ws-side right" aria-label="Tolerance inspector">
              {!draft ? (
                <div style={{ padding: 12 }}>
                  <h2 style={{ marginBottom: 8 }}>Specification evidence</h2>
                  <dl className="kv">{byConf.map(([c, n]) => <Fragment key={c}><dt><Evidence c={c} /></dt><dd>{n}</dd></Fragment>)}</dl>
                  <p className="faint small" style={{ marginTop: 12 }}>Select a row to see its distribution against its limits and edit its specification.</p>
                </div>
              ) : (<>
                <div className="insp-head">
                  <div className="grow"><div className="mono" style={{ fontWeight: 600 }}>{isNew ? "New tolerance" : draft.id}</div>
                    {!isNew && <div className="muted small">{draft.parameter} · {draft.component}</div>}</div>
                  {!isNew && <button className="btn small danger" onClick={remove} aria-label="Delete tolerance"><Trash2 /></button>}
                  <button className="btn primary small" disabled={!draftValid || busy} onClick={save}>Save</button>
                </div>
                <div style={{ overflow: "auto", minHeight: 0, padding: "0 12px 12px" }}>
                  {rev && !isNew && <section className="insp-sec">
                    <h3>Distribution against limits</h3>
                    <DensityChart row={rev} t={draft} />
                    <dl className="kv">
                      <dt>Limits</dt><dd>{fmt(rev.lower_limit, 7)} … {fmt(rev.upper_limit, 7)} {draft.unit}</dd>
                      <dt>Mean</dt><dd>{fmt(rev.mean, 7)} {draft.unit}</dd><dt>Standard deviation</dt><dd>{fmt(rev.std, 4)} {draft.unit}</dd>
                      <dt>Outside limits</dt><dd>{pct(rev.fraction_out_of_spec, 3)}</dd>
                      {rev.capability && <><dt>Cp / Cpk ({rev.capability.basis})</dt><dd>{fmt(rev.capability.cp, 3)} / {fmt(rev.capability.cpk, 3)}</dd></>}
                    </dl>
                    <p className="small faint" style={{ marginTop: 4 }}>Computed from the saved definition. Save to refresh.</p>
                  </section>}
                  {mine.map((f, i) => <div key={i} style={{ marginTop: 8 }}><Alert kind={f.severity === "error" ? "bad" : f.severity === "warning" ? "warn" : "info"}>{f.message}</Alert></div>)}
                  <section className="insp-sec"><h3>Specification</h3>
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
                  </section><section className="insp-sec"><h3>Distribution model</h3>
                    <div className="form">
                      <Field label="Type" wide><select value={draft.distribution.type} onChange={(e) => patch({ distribution: defaultDistribution(e.target.value as Distribution["type"], draft) })}>
                        {["uniform", "normal", "truncated_normal", "lognormal", "discrete", "empirical"].map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}</select></Field>
                      <DistributionEditor d={draft.distribution} onChange={(d) => patch({ distribution: d })} />
                    </div>
                  </section><section className="insp-sec"><h3>Provenance</h3>
                    <div className="form">
                      <Field label="Source" wide><input className="input" value={draft.source} placeholder="Drawing number, standard, measurement report…" onChange={(e) => patch({ source: e.target.value })} /></Field>
                      <Field label="Confidence"><select value={draft.confidence} onChange={(e) => patch({ confidence: e.target.value as Tolerance["confidence"] })}>
                        {["specified", "measured", "estimated", "assumed"].map((c) => <option key={c}>{c}</option>)}</select></Field>
                      <Field label="Verification"><select value={draft.verification} onChange={(e) => patch({ verification: e.target.value as Tolerance["verification"] })}>
                        {["unverified", "measured", "inspected"].map((c) => <option key={c}>{c}</option>)}</select></Field>
                      <Field label="Correlation group" wide><input className="input" value={draft.correlation_group ?? ""} onChange={(e) => patch({ correlation_group: e.target.value || null })} /></Field>
                    </div>
                  </section>
                  {pairs.length > 0 && <section className="insp-sec"><h3>Correlations</h3>
                    <dl className="kv">{pairs.map((c, i) => <Fragment key={i}><dt>{c.parameters.filter((x) => x !== draft.id).join(", ")}</dt><dd>{c.coefficient} ({c.basis})</dd></Fragment>)}</dl></section>}
                  {model.data && markers.length > 0 && <section className="insp-sec"><h3>Mapped feature</h3>
                    <Viewer modelId={model.data.id} stamp={model.data.geometry_fingerprint} components={model.data.components}
                      pose={pose} markers={markers} selected={markers[0].component} height={240} status={<span>Feature <span className="mono">{draft.feature}</span></span>} /></section>}
                </div>
              </>)}
            </aside>
          </div>);
      }}</Load>
    </div>
  );
}

/** One-line distribution strip from the backend's density curve, with the limits marked. */
function Spark({ row }: { row: ToleranceReviewRow }) {
  const { x, density } = row.curve;
  if (!x.length) return null;
  const lo = Math.min(x[0], row.lower_limit), hi = Math.max(x[x.length - 1], row.upper_limit);
  const span = hi - lo || 1, top = Math.max(...density) || 1, W = 96, H = 18;
  const px = (v: number) => ((v - lo) / span) * W;
  const path = x.map((v, i) => `${i ? "L" : "M"}${px(v).toFixed(1)},${(H - (density[i] / top) * (H - 2)).toFixed(1)}`).join("") + `L${px(x[x.length - 1]).toFixed(1)},${H}L${px(x[0]).toFixed(1)},${H}Z`;
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`distribution between ${fmt(row.lower_limit, 6)} and ${fmt(row.upper_limit, 6)}`} className="spark">
      <path d={path} fill="color-mix(in srgb, var(--mp-data) 22%, transparent)" stroke="var(--mp-data)" strokeWidth={1} />
      <line x1={px(row.lower_limit)} x2={px(row.lower_limit)} y1={0} y2={H} stroke="var(--bad)" strokeWidth={1} />
      <line x1={px(row.upper_limit)} x2={px(row.upper_limit)} y1={0} y2={H} stroke="var(--bad)" strokeWidth={1} />
    </svg>
  );
}

const EVIDENCE_GLYPH = { specified: ["ok", "\u25A0"], measured: ["ok", "\u25CF"], estimated: ["info", "\u25D0"], assumed: ["warn", "\u25CB"] } as const;
/** Evidence level as glyph and word (never colour alone). */
function Evidence({ c }: { c: keyof typeof EVIDENCE_GLYPH }) {
  const [k, g] = EVIDENCE_GLYPH[c];
  return <span className={`evidence ${k}`}><span aria-hidden="true">{g}</span>{c}</span>;
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
  const [vtab, setVtab] = useState<"validity" | "geometry" | "deviations">("validity");
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
  if (mode !== "nominal") changed.forEach((c) => { tint[c] = "#c9773a"; });

  const validity = (v: Variant) => v.violations.length > 0 ? ["bad", "\u2715", v.violations[0].category.replace(/_/g, " ")]
    : v.out_of_spec.length > 0 ? ["warn", "!", "out of spec"] : ["ok", "\u2713", "assembles"];
  return (
    <div className="ws">
      <div className="ws-head">
        <h1>Virtual assemblies</h1><span className="meta">{model.data?.name}</span><span className="spacer" />
        <label className="inline-field">Sampling<select value={method} onChange={(e) => setMethod(e.target.value)} style={{ width: 150 }}>
          <option value="monte_carlo">Monte Carlo</option><option value="latin_hypercube">Latin hypercube</option><option value="boundary">Boundary values</option><option value="corners">Worst-case corners</option></select></label>
        <label className="inline-field">Variants<div style={{ width: 72 }}><Num value={samples} min={1} max={500} step={1} onChange={setSamples} /></div></label>
        <label className="inline-field">Seed<div style={{ width: 64 }}><Num value={seed} step={1} onChange={setSeed} /></div></label>
        <button className="btn primary" disabled={!hasTol || set.loading || !(samples >= 1 && samples <= 500)} onClick={() => { setPicked(null); setRequest((r) => r + 1); }}><RefreshCw />Generate</button>
      </div>
      {!hasTol && <div style={{ padding: 12 }}><Alert kind="warn">This model has no tolerances. Define them in Tolerances before generating variants.</Alert></div>}
      <div className="ws-body va-body">
        <aside className="ws-side left" aria-label="Variants">
          <div className="ws-section" style={{ flex: "none" }}><div className="sec-title">Variants<span className="spacer" />
            {set.data && <span className="faint small">{set.data.method.replace(/_/g, " ")}, seed {set.data.seed}</span>}</div></div>
          <div style={{ flex: 1, overflow: "auto", minHeight: 0 }}>
            {request === 0 ? <Empty title="No variants generated">Choose a sampling method and generate as-manufactured assemblies from the tolerance distributions.</Empty> : (
              <Load state={set} label="Generating variants">{(d) => (
                <table className="grid"><thead><tr><th>Id</th><th className="num">Backlash mrad</th><th className="num">Play µm</th><th title="Assembly validity">Valid</th></tr></thead><tbody>
                  {d.variants.map((v) => { const j = joint(v); const [k, g, w] = validity(v); return (
                    <tr key={v.id} className={`click ${picked?.id === v.id ? "selected" : ""}`} onClick={() => setPicked(v)}>
                      <td className="mono">{v.id}{worst?.id === v.id && <span className="faint small" title="Largest backlash in this set"> max</span>}</td>
                      <td className="num">{j ? fmt(j.backlash * 1e3, 4) : "–"}</td><td className="num">{j ? fmt(j.radial_play * 1e6, 3) : "–"}</td>
                      <td title={w}><span className={`evidence ${k}`}><span aria-hidden="true" style={{ fontSize: 12 }}>{g}</span><span className="sr-only">{w}</span></span></td></tr>); })}
                </tbody></table>)}</Load>)}
          </div>
          {set.data && (() => { const vs = set.data.variants; const bad = vs.filter((v) => v.violations.length).length; const out = vs.filter((v) => !v.violations.length && v.out_of_spec.length).length;
            return <div className="ws-section" style={{ borderTop: "1px solid var(--border)", borderBottom: 0 }}><div className="sec-body" style={{ paddingTop: 8 }}>
              <dl className="kv"><dt>Assemble</dt><dd>{vs.length - bad - out} / {vs.length}</dd><dt>Out of specification</dt><dd>{out}</dd><dt>Cannot assemble</dt><dd>{bad}</dd></dl>
              {set.data.note && <p className="faint small" style={{ marginTop: 6 }}>{set.data.note}</p>}</div></div>; })()}
        </aside>
        <div className="va-centre">
          <div className="va-bar">
            <span className="muted small">Compare</span>
            <div className="seg" role="radiogroup" aria-label="Comparison mode">{(["nominal", "variant", "overlay"] as const).map((k) => (
              <button key={k} role="radio" aria-checked={mode === k} className={mode === k ? "on" : ""} onClick={() => setMode(k)} disabled={k !== "nominal" && !picked}>
                {k === "overlay" ? "Overlay" : k === "nominal" ? "Nominal" : "Variant"}</button>))}</div>
            {mode === "overlay" && <label className="inline-field">Magnify deviation ×<span className="mono" style={{ width: 36, textAlign: "right" }}>{magnify}</span>
              <input type="range" min={1} max={1000} step={1} value={magnify} onChange={(e) => setMagnify(Number(e.target.value))} aria-label="Deviation magnification" /></label>}
          </div>
          {model.data && <Viewer modelId={model.data.id} stamp={model.data.geometry_fingerprint} components={model.data.components}
            pose={mode === "variant" && variantPose ? variantPose : nominalPose} tint={tint}
            overlay={mode === "overlay" && picked && variantPose ? { pose: variantPose, magnify, changed } : null}
            status={picked ? <><span>Variant <span className="mono">{picked.id}</span></span><span>{mode === "overlay" ? `variant pose wireframe, deviation ×${magnify} (Level C)` : mode === "variant" ? "variant pose, true scale" : "nominal pose"}</span>
              {changed.size > 0 && <span><span style={{ color: "#c9773a" }}>■</span> {changed.size} components with deviating features</span>}</>
              : <span>Nominal assembly. Select a variant to compare.</span>} />}
        </div>
        <aside className="ws-side right" aria-label="Variant inspector">
          {!picked ? <div style={{ padding: 12 }}><Empty title="No variant selected">Select a variant to see whether it assembles, its fits and gear meshes, the regenerated geometry and every dimension deviation.</Empty></div> : (<>
            <div className="ws-tabs" role="tablist">{(["validity", "geometry", "deviations"] as const).map((k) => (
              <button key={k} role="tab" aria-selected={vtab === k} onClick={() => setVtab(k)}>{k[0].toUpperCase() + k.slice(1)}</button>))}</div>
            <div style={{ overflow: "auto", minHeight: 0 }}>
              <Load state={detail} label="Regenerating geometry">{(d) => (<>
                {vtab === "validity" && <div style={{ padding: 12 }} className="col">
                  {d.variant.violations.length === 0 ? <p className="pos small">{"\u2713"} No assembly violations.</p>
                    : d.variant.violations.map((v, i) => <Alert key={i} kind="bad"><b>{v.subject}</b>: {v.message}</Alert>)}
                  <section><h3>Fits</h3><table className="grid"><thead><tr><th>Fit</th><th>State</th><th className="num">Clearance (µm)</th></tr></thead><tbody>
                    {d.variant.fits.map((f) => <tr key={f.fit}><td className="mono">{f.fit}</td><td>{f.state}</td><td className="num">{signed(f.clearance * 1000, 3)}</td></tr>)}</tbody></table></section>
                  <section><h3>Gear stages (Level C, reduced order)</h3><table className="grid"><thead><tr><th>Stage</th><th className="num">Backlash (mrad)</th><th className="num">Mesh (µm)</th><th>Mesh</th></tr></thead><tbody>
                    {d.variant.stages.map((s) => <tr key={s.stage}><td className="mono">{s.stage}</td><td className="num">{fmt(s.backlash_angle * 1e3, 4)}</td>
                      <td className="num">{fmt(s.min_mesh_backlash_mm * 1e3, 3)}</td><td>{s.binding ? <span className="evidence bad"><span>{"\u2715"}</span>binds</span> : "free"}</td></tr>)}</tbody></table></section>
                </div>}
                {vtab === "geometry" && <div style={{ padding: 12 }} className="col">
                  {!d.geometry ? <p className="muted small">No regenerated geometry for this model: variants change model values (Level C), not meshes.</p> : <>
                    <section><h3>Regenerated geometry (Level A, measured on the CAD kernel)</h3><table className="grid"><tbody>
                      {Object.entries(d.geometry.measured_dimensions_mm).map(([k, v]) => <tr key={k}><td>{k.replace(/_/g, " ")}</td><td className="num">{fmt(v, 7)} mm</td></tr>)}</tbody></table></section>
                    <section><h3>Interfaces</h3><table className="grid"><thead><tr><th>Interface</th><th className="num">Radial clearance (µm)</th><th className="num">Interference (mm³)</th></tr></thead><tbody>
                      {Object.entries(d.geometry.interfaces).map(([k, v]) => <tr key={k}><td>{k.replace(/_/g, " ")}</td><td className="num">{signed(v.radial_clearance_mm * 1000, 3)}</td>
                        <td className={`num ${v.interference_mm3 > 1e-9 ? "neg" : ""}`}>{v.interference_mm3 > 1e-9 ? fmt(v.interference_mm3, 3) : "0"}</td></tr>)}</tbody></table></section>
                    {d.geometry.changed_components.length > 0 && <section><h3>Changed components</h3><table className="grid"><thead><tr><th>Component</th><th className="num">ΔV (mm³)</th><th className="num">COM shift (mm)</th></tr></thead><tbody>
                      {d.geometry.changed_components.map((c) => <tr key={c.component}><td className="mono">{c.component}</td><td className="num">{signed(c.volume_change_mm3, 3)}</td><td className="num">{fmt(c.com_shift_mm, 3)}</td></tr>)}</tbody></table></section>}
                  </>}
                  <p className="small faint">{d.levels_note}</p>
                </div>}
                {vtab === "deviations" && <table className="grid"><thead><tr><th>Tolerance</th><th className="num">Deviation</th><th title="Position of the actual value inside the tolerance zone, lower to upper limit">Zone</th></tr></thead><tbody>
                  {d.deviations.map((x) => <tr key={x.tolerance}><td className="mono ell" title={`${x.tolerance} · ${x.component} · nominal ${fmt(x.nominal, 6)} · actual ${fmt(x.actual, 6)} ${x.unit}`}>{x.tolerance}</td>
                    <td className="num">{signed(x.deviation, 3)} <span className="faint">{x.unit}</span></td>
                    <td><ZoneBar f={x.zone_fraction} ok={x.in_spec} /></td></tr>)}</tbody></table>}
              </>)}</Load>
            </div></>)}
        </aside>
      </div>
    </div>
  );
}

/** Where a value sits inside its tolerance zone: 0 at the lower limit, 1 at the upper. */
function ZoneBar({ f, ok }: { f: number; ok: boolean }) {
  const x = Math.min(Math.max(f, -0.1), 1.1);
  return (
    <span className="zone" role="img" aria-label={ok ? `${Math.round(f * 100)} % of the zone` : "outside the zone"}>
      <span className="zone-track" /><span className={`zone-mark ${ok ? "" : "out"}`} style={{ left: `${((x + 0.1) / 1.2) * 100}%` }} />
      {!ok && <span className="evidence warn" style={{ marginLeft: 66 }}><span>!</span>out</span>}
    </span>
  );
}
