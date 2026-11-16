import { useMemo, useRef, useState } from "react";
import { Eye, EyeOff, Focus, Plus, ShieldCheck, Trash2, UploadCloud } from "lucide-react";
import { api } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import { useModel, usePose } from "../hooks/useModel";
import { useApp } from "../stores/app";
import type { Component, Dict, Feature, ModelDetail, Readiness } from "../lib/types";
import { Alert, Badge, Empty, Field, Load, NeedSelection, Num, Panel, fmt } from "../components/ui";
import { Viewer, type Marker } from "../components/Viewer";

const FORMATS = [".step", ".stp", ".stl", ".obj", ".urdf", ".xml"];
const FEATURE_TYPES = ["shaft", "bore", "bearing_seat", "mounting_hole", "datum_plane", "datum_axis", "mating_face", "joint_interface", "gear_interface"];

function CheckList({ r }: { r: Readiness }) {
  const kind = { ok: "ok", warning: "warn", error: "bad", info: "info" } as const;
  return (
    <table className="grid"><tbody>{r.checks.map((c, i) => (
      <tr key={i}><td><Badge kind={kind[c.status]}>{c.status}</Badge></td><td className="muted">{c.area}</td><td className="wrap">{c.message}</td></tr>))}
    </tbody></table>
  );
}

// ---------------------------------------------------------------- import

export function ImportScreen() {
  const { projectId, setModel, go, notify } = useApp();
  const [files, setFiles] = useState<File[]>([]);
  const [units, setUnits] = useState("");
  const [over, setOver] = useState(false);
  const [stage, setStage] = useState<"idle" | "uploading" | "done">("idle");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Awaited<ReturnType<typeof api.importModel>> | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const detail = useAsync(result ? () => api.model(result.id) : null, [result?.id]);
  const pose = usePose(result?.id ?? null, {});
  if (!projectId) return <NeedSelection what="project" action={<button className="btn primary" onClick={() => go("projects")}>Open projects</button>} />;

  const primary = files[0];
  const ext = primary ? primary.name.slice(primary.name.lastIndexOf(".")).toLowerCase() : "";
  const isMesh = ext === ".stl" || ext === ".obj";
  const supported = !primary || FORMATS.includes(ext);
  const pick = (list: FileList | null) => { if (list && list.length) { setFiles(Array.from(list)); setError(null); setResult(null); setStage("idle"); } };
  const upload = async () => {
    setStage("uploading"); setError(null);
    try {
      const r = await api.importModel(projectId, files, units);
      setResult(r); setStage("done"); setModel(r.id);
      notify("ok", `${r.name} imported`);
    } catch (e) { setError((e as Error).message); setStage("idle"); }
  };

  return (
    <div className="page">
      <div className="page-head"><h1>CAD import</h1><span className="sub">STEP · STL · OBJ · URDF · MJCF</span></div>
      <div className="split two">
        <div className="col">
          <Panel title="File">
            <div className={`drop ${over ? "over" : ""}`} role="button" tabIndex={0}
              onClick={() => input.current?.click()} onKeyDown={(e) => { if (e.key === "Enter") input.current?.click(); }}
              onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
              onDrop={(e) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files); }}>
              <UploadCloud style={{ width: 26, height: 26 }} />
              <div><b>Drop a file here</b> or click to browse</div>
              <div className="small">For URDF or MJCF, select the model file first together with its mesh files.</div>
              <input ref={input} type="file" multiple hidden accept={FORMATS.join(",")} onChange={(e) => pick(e.target.files)} />
            </div>
            {primary && (
              <div className="col" style={{ marginTop: 10 }}>
                <dl className="kv"><dt>File</dt><dd>{primary.name}</dd><dt>Size</dt><dd>{(primary.size / 1024).toFixed(1)} kB</dd>
                  <dt>Companion files</dt><dd>{files.length - 1}</dd></dl>
                {!supported && <Alert kind="bad">Files of type “{ext || "unknown"}” are not supported. Supported: {FORMATS.join(", ")}.</Alert>}
                {isMesh && (
                  <Field label="Length unit of the mesh" hint="Mesh files carry no unit. MotionProof never guesses: leave unset to import dimensions as unknown.">
                    <select value={units} onChange={(e) => setUnits(e.target.value)}>
                      <option value="">Not stated</option><option value="mm">mm</option><option value="cm">cm</option><option value="m">m</option><option value="in">inch</option>
                    </select></Field>)}
                <div className="row center">
                  <button className="btn primary" disabled={!supported || stage === "uploading"} onClick={upload}>
                    {stage === "uploading" ? "Processing geometry…" : "Import"}</button>
                  {stage === "uploading" && <span className="muted small">Upload, validation and meshing run on the backend.</span>}
                </div>
              </div>)}
            {error && <div style={{ marginTop: 10 }}><Alert kind="bad"><b>Import failed.</b> {error}</Alert></div>}
          </Panel>
          {result && (
            <Panel title="Import result" actions={<button className="btn primary small" onClick={() => go("workbench")}>Open in workbench</button>}>
              <dl className="kv"><dt>Format</dt><dd>{result.inventory.format}</dd><dt>Components</dt><dd>{result.inventory.components.length}</dd>
                <dt>Geometry units</dt><dd>{result.inventory.units.geometry}</dd><dt>Model id</dt><dd>{result.id}</dd></dl>
              <div className="col" style={{ marginTop: 10, gap: 6 }}>
                {result.inventory.warnings.length === 0 ? <Alert kind="ok">No import warnings.</Alert>
                  : result.inventory.warnings.map((w, i) => <Alert key={i} kind="warn">{w}</Alert>)}
              </div>
            </Panel>)}
        </div>
        <Panel title="Preview" flush>
          {result && detail.data ? (
            <Viewer modelId={detail.data.id} stamp={detail.data.geometry_fingerprint} components={detail.data.components} pose={pose} height={520} />
          ) : <Empty title="No model imported yet">The imported geometry is shown here after processing.</Empty>}
        </Panel>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- workbench

function Inspector({ c, model }: { c: Component; model: ModelDetail }) {
  const bb = c.bbox_mm ?? c.bbox;
  const feats = model.spec.features.filter((f) => f.component === c.id);
  const tols = model.spec.tolerances.filter((t) => t.component === c.id);
  return (
    <div className="col">
      <dl className="kv">
        <dt>Component</dt><dd>{c.id}</dd><dt>Body</dt><dd>{c.body}</dd><dt>Group</dt><dd>{c.group}</dd>
        <dt>Volume</dt><dd>{c.volume_mm3 == null ? "undefined" : `${fmt(c.volume_mm3, 6)} mm³`}</dd>
        <dt>Mass</dt><dd>{c.mass_kg == null ? "undefined (no density)" : `${fmt(c.mass_kg * 1000, 5)} g`}</dd>
        <dt>Density</dt><dd>{c.density_kg_m3 == null ? "–" : `${c.density_kg_m3} kg/m³`}</dd>
        {bb && <><dt>Extents</dt><dd>{bb[0].map((v, i) => fmt(bb[1][i] - v, 5)).join(" × ")} {c.mesh_units}</dd></>}
        {c.com_m && <><dt>Centre of mass</dt><dd>{c.com_m.map((v) => fmt(v * 1000, 4)).join(", ")} mm</dd></>}
        <dt>Source</dt><dd>{c.source ?? "–"}</dd>
      </dl>
      {c.inertia_com_kgm2 && <div><h3>Inertia about COM (kg·m²)</h3>
        <table className="grid"><tbody>{c.inertia_com_kgm2.map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j} className="num">{v.toExponential(3)}</td>)}</tr>)}</tbody></table></div>}
      {c.note && <Alert kind="info">{c.note}</Alert>}
      <div><h3>Features ({feats.length})</h3>{feats.map((f) => <div key={f.id} className="small">{f.id} <span className="faint">{f.type}</span></div>)}</div>
      <div><h3>Tolerances ({tols.length})</h3>{tols.map((t) => <div key={t.id} className="small">{t.id} <span className="faint">{t.lower}/{t.upper} {t.unit}</span></div>)}</div>
    </div>
  );
}

export function WorkbenchScreen() {
  const model = useModel();
  const modelId = useApp((s) => s.modelId);
  const go = useApp((s) => s.go);
  const [selected, setSelected] = useState<string | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [isolate, setIsolate] = useState<string | null>(null);
  const [q, setQ] = useState<Dict>({});
  const pose = usePose(modelId, q);
  const readiness = useAsync(modelId ? () => api.validateModel(modelId) : null, [modelId, model.data?.fingerprint]);
  if (!modelId) return <NeedSelection what="model" action={<button className="btn primary" onClick={() => go("projects")}>Open projects</button>} />;

  const toggle = (id: string) => setHidden((h) => { const n = new Set(h); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  return (
    <div className="page">
      <Load state={model}>{(m) => {
        const groups = Array.from(new Set(m.components.map((c) => c.group)));
        const sel = m.components.find((c) => c.id === selected) ?? null;
        const joints = pose?.joints ?? [];
        return (<>
          <div className="page-head"><h1>Assembly workbench</h1><span className="sub">{m.name}</span>
            {m.spec.synthetic && <Badge kind="warn" title="Generated by MotionProof for demonstration; not user hardware">synthetic reference design</Badge>}
            <Badge>{m.spec.fidelity.replace(/_/g, " ")}</Badge><span className="spacer" />
            {readiness.data && <Badge kind={readiness.data.status === "ready" ? "ok" : readiness.data.status === "blocked" ? "bad" : "warn"}><ShieldCheck style={{ width: 12, height: 12 }} />{readiness.data.status.replace(/_/g, " ")}</Badge>}
          </div>
          <div className="split">
            <Panel title="Assembly" flush foot={`${m.components.length} components · ${m.joints.length} joints`}>
              {groups.map((g) => (<div key={g}><div className="tree-group">{g}</div>
                {m.components.filter((c) => c.group === g).map((c) => (
                  <div key={c.id} className={`list-item ${selected === c.id ? "selected" : ""} ${hidden.has(c.id) ? "dim" : ""}`}>
                    <button className="btn ghost small" onClick={() => toggle(c.id)} aria-label={hidden.has(c.id) ? `Show ${c.name}` : `Hide ${c.name}`}>{hidden.has(c.id) ? <EyeOff /> : <Eye />}</button>
                    <button className="name" style={{ border: 0, background: "none", font: "inherit", color: "inherit", textAlign: "left", cursor: "pointer", padding: 0 }} onClick={() => setSelected(c.id)}>{c.name}</button>
                    <button className="btn ghost small" aria-pressed={isolate === c.id} onClick={() => setIsolate(isolate === c.id ? null : c.id)} aria-label={`Isolate ${c.name}`} title="Isolate"><Focus /></button>
                  </div>))}</div>))}
              <div className="tree-group">Joints</div>
              {joints.length === 0 && <div className="list-item dim"><span className="name">No joints (geometry-only model)</span></div>}
              {joints.map((j) => (
                <div key={j.name} style={{ padding: "4px 10px" }}>
                  <div className="row center" style={{ gap: 6 }}><span className="grow">{j.name}</span>{j.driven && <Badge kind="info">driven</Badge>}
                    <span className="mono faint">{fmt(((q[j.name] ?? m.spec.held_joints[j.name] ?? 0) * 180) / Math.PI, 3)}°</span></div>
                  <input type="range" style={{ width: "100%" }} aria-label={`${j.name} angle`} min={j.range ? j.range[0] : -3.14} max={j.range ? j.range[1] : 3.14} step={0.01}
                    value={q[j.name] ?? m.spec.held_joints[j.name] ?? 0} onChange={(e) => setQ({ ...q, [j.name]: Number(e.target.value) })} />
                </div>))}
            </Panel>
            <Viewer modelId={m.id} stamp={m.geometry_fingerprint} components={m.components} pose={pose} selected={selected}
              onSelect={setSelected} hidden={hidden} isolate={isolate}
              legend="Drag to orbit · right-drag to pan · wheel to zoom · click a part to inspect" />
            <div className="col">
              <Panel title={sel ? sel.name : "Inspector"}>{sel ? <Inspector c={sel} model={m} /> : <Empty title="Nothing selected">Click a component in the tree or the viewport.</Empty>}</Panel>
              <Panel title="Model readiness" flush><Load state={readiness}>{(r) => <CheckList r={r} />}</Load></Panel>
            </div>
          </div>
        </>);
      }}</Load>
    </div>
  );
}

// ---------------------------------------------------------------- features

const blank = (component: string): Feature => ({ id: "", component, type: "shaft", nominal: {}, unit: "mm", datum: null, mates_with: null,
  geometry: { kind: "none" }, source: "manual registration", status: "confirmed", note: null });

export function FeaturesScreen() {
  const model = useModel();
  const { modelId, go, notify } = useApp();
  const suggestions = useAsync(modelId ? () => api.suggestions(modelId) : null, [modelId]);
  const pose = usePose(modelId, {});
  const [selected, setSelected] = useState<string | null>(null);
  const [draft, setDraft] = useState<Feature | null>(null);
  const [component, setComponent] = useState<string | null>(null);
  const markers = useMemo<Marker[]>(() => {
    const list: Marker[] = [];
    const feats = model.data?.spec.features ?? [];
    for (const f of feats) if (f.id === selected && f.geometry.kind !== "none") list.push({ component: f.component, geometry: f.geometry });
    if (draft && draft.geometry.kind !== "none") list.push({ component: draft.component, geometry: draft.geometry, color: "#2e8b57" });
    return list;
  }, [model.data, selected, draft]);
  if (!modelId) return <NeedSelection what="model" action={<button className="btn primary" onClick={() => go("projects")}>Open projects</button>} />;

  const save = async () => {
    if (!draft) return;
    try {
      await api.saveFeature(modelId, { ...draft, id: draft.id.trim() });
      notify("ok", `Feature ${draft.id} saved`); setSelected(draft.id.trim()); setDraft(null); model.reload();
    } catch (e) { notify("error", (e as Error).message); }
  };
  const remove = async (id: string) => {
    try { await api.deleteFeature(modelId, id); notify("ok", `Feature ${id} removed`); setSelected(null); model.reload(); }
    catch (e) { notify("error", (e as Error).message); }
  };

  return (
    <div className="page">
      <Load state={model}>{(m) => {
        const comp = component ?? m.components[0]?.id ?? "";
        const sug = suggestions.data?.[comp] ?? [];
        const nominalDia = draft?.nominal.diameter;
        return (<>
          <div className="page-head"><h1>Feature and datum mapping</h1><span className="sub">{m.name}</span><span className="spacer" />
            <button className="btn primary" onClick={() => setDraft(blank(comp))}><Plus />Register feature</button></div>
          <div className="split">
            <Panel title={`Registered features (${m.spec.features.length})`} flush>
              {m.spec.features.length === 0 ? <Empty title="No features registered">Register shafts, bores, bearing seats, mounting holes and datums so tolerances can refer to them.</Empty>
                : <div className="list">{m.spec.features.map((f) => (
                  <button key={f.id} className={`list-item ${selected === f.id ? "selected" : ""}`} onClick={() => { setSelected(f.id); setDraft(null); }}>
                    <span className="name">{f.id}<br /><span className="faint small">{f.type.replace(/_/g, " ")} · {f.component}</span></span>
                    {f.datum && <Badge kind="info">datum {f.datum}</Badge>}{f.status === "suggested" && <Badge kind="warn">unconfirmed</Badge>}
                  </button>))}</div>}
              <div className="tree-group">Datums</div>
              {m.spec.datums.length === 0 && <div className="list-item dim"><span className="name">No datums defined</span></div>}
              {m.spec.datums.map((d) => <div key={d.id} className="list-item"><Badge kind="info">{d.id}</Badge><span className="name">{d.feature} <span className="faint">({d.type})</span></span></div>)}
            </Panel>
            <Viewer modelId={m.id} stamp={m.geometry_fingerprint} components={m.components} pose={pose} markers={markers}
              selected={draft?.component ?? m.spec.features.find((f) => f.id === selected)?.component ?? null}
              onSelect={(id) => { if (id) { setComponent(id); if (draft) setDraft({ ...draft, component: id }); } }}
              legend="Click a component to choose it · the selected feature is highlighted" />
            <div className="col">
              {draft ? (
                <Panel title="Register feature" actions={<><button className="btn small" onClick={() => setDraft(null)}>Cancel</button>
                  <button className="btn primary small" disabled={!draft.id.trim() || !draft.component} onClick={save}>Save</button></>}>
                  <div className="form">
                    <Field label="Feature id"><input className="input" value={draft.id} onChange={(e) => setDraft({ ...draft, id: e.target.value })} /></Field>
                    <Field label="Type"><select value={draft.type} onChange={(e) => setDraft({ ...draft, type: e.target.value })}>{FEATURE_TYPES.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}</select></Field>
                    <Field label="Component" wide><select value={draft.component} onChange={(e) => { setDraft({ ...draft, component: e.target.value }); setComponent(e.target.value); }}>{m.components.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
                    <Field label="Nominal diameter" hint="Leave empty when not applicable"><Num value={nominalDia ?? NaN} onChange={(v) => { const n = { ...draft.nominal }; if (Number.isFinite(v)) n.diameter = v; else delete n.diameter; setDraft({ ...draft, nominal: n }); }} /></Field>
                    <Field label="Unit"><select value={draft.unit} onChange={(e) => setDraft({ ...draft, unit: e.target.value })}><option>mm</option><option>cm</option><option>m</option><option>in</option></select></Field>
                    <Field label="Datum reference"><select value={draft.datum ?? ""} onChange={(e) => setDraft({ ...draft, datum: e.target.value || null })}><option value="">none</option>{m.spec.datums.map((d) => <option key={d.id}>{d.id}</option>)}</select></Field>
                    <Field label="Mates with"><select value={draft.mates_with ?? ""} onChange={(e) => setDraft({ ...draft, mates_with: e.target.value || null })}><option value="">none</option>{m.spec.features.map((f) => <option key={f.id}>{f.id}</option>)}</select></Field>
                  </div>
                  <p className="small muted" style={{ marginTop: 8 }}>Geometry reference: {draft.geometry.kind === "none" ? "none (pick a detected cylinder below to attach one)" : `${draft.geometry.kind}, r = ${fmt(draft.geometry.radius ?? NaN)}`}</p>
                </Panel>
              ) : (
                <Panel title="Feature">{(() => {
                  const f = m.spec.features.find((x) => x.id === selected);
                  if (!f) return <Empty title="No feature selected">Select a registered feature or register a new one.</Empty>;
                  return (<div className="col"><dl className="kv"><dt>Id</dt><dd>{f.id}</dd><dt>Type</dt><dd>{f.type}</dd><dt>Component</dt><dd>{f.component}</dd>
                    {Object.entries(f.nominal).map(([k, v]) => <><dt key={k}>{k}</dt><dd key={`${k}v`}>{v} {f.unit}</dd></>)}
                    <dt>Datum</dt><dd>{f.datum ?? "–"}</dd><dt>Mates with</dt><dd>{f.mates_with ?? "–"}</dd><dt>Reference</dt><dd>{f.geometry.kind}</dd>
                    {f.geometry.point && <><dt>Point</dt><dd>{f.geometry.point.map((v) => fmt(v)).join(", ")}</dd></>}
                    <dt>Source</dt><dd>{f.source}</dd><dt>Status</dt><dd>{f.status}</dd></dl>
                    <div className="row"><button className="btn small" onClick={() => setDraft({ ...f })}>Edit</button>
                      <button className="btn small danger" onClick={() => remove(f.id)}><Trash2 />Remove</button></div></div>);
                })()}</Panel>)}
              <Panel title="Detected cylinders (suggestions)" flush foot="Detected from B-rep faces. STEP carries no design intent: confirm before use.">
                <div style={{ padding: 8 }}><select value={comp} onChange={(e) => setComponent(e.target.value)} aria-label="Component for suggestions">{m.components.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
                {sug.length === 0 ? <Empty title="No suggestions">Feature detection is available for imported STEP solids. Features of other models are registered manually.</Empty> : (
                  <table className="grid"><thead><tr><th>Kind</th><th className="num">⌀ mm</th><th className="num">Length</th><th /></tr></thead><tbody>
                    {sug.map((s, i) => (<tr key={i}><td>{s.external ? "external" : "internal"}</td><td className="num">{fmt(s.diameter, 6)}</td><td className="num">{fmt(s.length, 5)}</td>
                      <td><button className="btn small" onClick={() => setDraft({ ...blank(comp), type: s.suggested_type, id: `${comp}_${s.suggested_type}_${i + 1}`,
                        nominal: { diameter: Number(s.diameter.toFixed(6)) }, source: "detected cylinder, confirmed by user",
                        geometry: { kind: "cylinder", point: s.axis_start, direction: s.axis_direction, radius: s.radius, length: s.length, face_index: s.faces[0] } })}>Use</button></td></tr>))}
                  </tbody></table>)}
              </Panel>
            </div>
          </div>
        </>);
      }}</Load>
    </div>
  );
}
