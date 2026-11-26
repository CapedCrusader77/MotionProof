import { useMemo, useState } from "react";
import { Download, Play } from "lucide-react";
import { ext, type AnyJson } from "../lib/api";
import { useAsync, useJob, isActive } from "../hooks/useAsync";
import { useApp } from "../stores/app";
import { Alert, Badge, Empty, Load, Panel, Spinner, Stat, fmt } from "../components/ui";
import { Histogram, Lines } from "../components/charts";

// External experimental validation: public robot datasets, pre-registered protocols,
// measured-versus-predicted on holdout trials. Everything shown comes from recorded runs.

const tone = (s: string) => (s === "PASS" ? "ok" : s === "FAIL" ? "bad" : "warn") as "ok" | "bad" | "warn";

function Plot({ p }: { p: AnyJson }) {
  const rows = useMemo(() => p.x.map((x: number, i: number) => ({
    x, measured: p.measured[i], predicted: p.predicted[i], ...(p.baseline ? { baseline: p.baseline[i] } : {}),
  })), [p]);
  const series = [{ key: "measured", name: "measured" }, { key: "predicted", name: "MotionProof model" }];
  if (p.baseline) series.push({ key: "baseline", name: "baseline" });
  return (<>
    <p className="small muted">Validation trial {p.trial} (holdout, never used for fitting)</p>
    <Lines data={rows} x="x" series={series.map((s, i) => ({ ...s, color: ["var(--text)", "var(--bad)", "var(--faint)"][i], dashed: s.key === "baseline" }))}
      xLabel={p.x_label} yLabel={p.y_label} height={240} />
  </>);
}

function Residuals({ h }: { h?: AnyJson }) {
  if (!h) return null;
  const x = h.edges.slice(0, -1).map((e: number, i: number) => (e + h.edges[i + 1]) / 2);
  return <Histogram hist={{ x, count: h.counts }} height={150} />;
}

function MetricTable({ m }: { m: AnyJson }) {
  const rows: [string, string, AnyJson][] = [];
  for (const which of ["model", "baseline"]) for (const split of ["identification", "validation"]) {
    const e = m?.[which]?.[split];
    if (e) rows.push([split, which, e]);
  }
  return (
    <table className="grid"><thead><tr><th>Set</th><th>Model</th><th className="num">RMSE</th><th className="num">MAE</th>
      <th className="num">Max abs</th><th className="num">Mean error</th><th className="num">NRMSE</th><th className="num">R²</th></tr></thead>
      <tbody>{rows.map(([s, w, e]) => <tr key={s + w}><td>{s}</td><td>{w === "model" ? "MotionProof" : "baseline"}</td>
        <td className="num">{fmt(e.rmse, 4)}</td><td className="num">{fmt(e.mae, 4)}</td><td className="num">{fmt(e.max_abs, 4)}</td>
        <td className="num">{fmt(e.mean_error, 3)}</td><td className="num">{e.nrmse == null ? "-" : fmt(e.nrmse, 3)}</td>
        <td className="num">{e.r2 == null ? "-" : fmt(e.r2, 3)}</td></tr>)}</tbody></table>
  );
}

function SubResult({ name, r }: { name: string; r: AnyJson }) {
  return (
    <Panel title={<>{name} <Badge kind={tone(r.status)}>{r.status}</Badge>
      {r.rmse_ratio_model_to_baseline != null && <span className="small muted"> RMSE ratio model/baseline {fmt(r.rmse_ratio_model_to_baseline, 3)}</span>}</>}>
      {r.metrics && <MetricTable m={r.metrics} />}
      {r.plot && <Plot p={r.plot} />}
      {r.residual_histogram && <><p className="small muted">Validation residuals (measured − predicted)</p><Residuals h={r.residual_histogram} /></>}
    </Panel>
  );
}

const count = (r: AnyJson, k: string): number => {
  const own = (r[k] ?? []).length;
  if (own) return own;
  return Object.values(r.axes ?? {}).reduce((n: number, a) => n + ((a as AnyJson)[k] ?? []).length, 0);
};

function RunView({ id }: { id: string }) {
  const rec = useAsync(() => ext.run(id), [id]);
  return (
    <Load state={rec}>{(d) => { const r = d.result; return (<>
      <div className="grid4">
        <Panel><Stat label="Status" value={<Badge kind={tone(r.status)}>{r.status}</Badge>} sub={`benchmark ${r.benchmark}`} /></Panel>
        <Panel><Stat label="Identification trials" value={count(r, "identification_trials") || "-"} /></Panel>
        <Panel><Stat label="Validation trials" value={count(r, "validation_trials") || "-"} /></Panel>
        <Panel><Stat label="RMSE model / baseline" value={r.rmse_ratio_model_to_baseline != null ? fmt(r.rmse_ratio_model_to_baseline, 3) : "per axis"} sub="validation, lower is better" /></Panel>
      </div>
      {r.reason && <Alert kind="warn">{r.reason}</Alert>}
      <Panel title="Protocol (pre-registered)">
        <table className="grid"><tbody>
          {[["System", r.system], ["Quantity", r.quantity], ["Baseline", r.baseline], ["MotionProof model", r.model], ["Acceptance", r.acceptance],
            ["Identification", r.split.identification], ["Validation", r.split.validation], ["Unused", r.split.unused], ["Scope", r.scope]].map(([k, v]) =>
            <tr key={k}><td style={{ width: 160 }}>{k}</td><td className="wrap">{v}</td></tr>)}
        </tbody></table>
      </Panel>
      {r.metrics && <SubResult name="Result" r={r} />}
      {Object.entries(r.axes ?? {}).map(([k, v]) => <SubResult key={k} name={k} r={v as AnyJson} />)}
      {Object.entries(r.joints ?? {}).map(([k, v]) => <SubResult key={k} name={k} r={v as AnyJson} />)}
      {r.plot && !r.metrics && <Panel title="Measured and predicted"><Plot p={r.plot} /></Panel>}
      <Panel title="Transformations and evidence">
        {(r.transformations ?? []).map((t: string) => <p key={t} className="small">• {t}</p>)}
        {(r.limitations ?? []).map((t: string) => <p key={t} className="small">• Limitation: {t}</p>)}
        <p className="small muted">{(r.evidence ?? []).length} evidence records: {Array.from(new Set((r.evidence ?? []).map((e: AnyJson) => e.evidence))).join(", ") || "none"}.
          External measurements are never treated as measurements of your own hardware.</p>
        <p className="small muted">Reproduce: <code>{r.reproduce}</code> · {d.created_utc} · MotionProof {d.motionproof_version} · adapter {d.adapter_version} · {Object.keys(d.files ?? {}).length} files with checksums</p>
      </Panel>
    </>); }}</Load>
  );
}

export function ExternalValidationScreen() {
  const notify = useApp((s) => s.notify);
  const datasets = useAsync(() => ext.datasets(), []);
  const runs = useAsync(() => ext.runs(), []);
  const [jobId, setJobId] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [ds, setDs] = useState<string | null>(null);
  const job = useJob(jobId, (j) => {
    if (j.status !== "completed") notify("error", j.error ?? `job ${j.status}`);
    datasets.reload();
    runs.reload();
    const res = (j as unknown as { result?: AnyJson }).result;
    if (res?.id) setOpen(String(res.id));
  });
  const launch = (p: Promise<{ id: string }>) => p.then((j) => setJobId(j.id), (e: Error) => notify("error", e.message));
  const latest = useMemo(() => {
    const m: Record<string, AnyJson> = {};
    for (const r of runs.data ?? []) m[r.protocol] = r;
    return m;
  }, [runs.data]);

  return (
    <div className="page">
      <div className="page-head"><h1>External validation</h1><span className="sub">public experimental robot datasets, holdout predictions</span><span className="spacer" />
        <button className="btn primary" disabled={isActive(job)} onClick={() => launch(ext.validate("transmission-error-v4"))}><Play />Run X1</button></div>
      {isActive(job) && <Spinner label="Running on the backend" />}
      <Alert kind="info">These are measurements of other people's robots (Stäubli, Unitree H1, SO-101, KUKA, UR5). They test how well MotionProof's model components reproduce real behaviour; they are not measurements of your gearbox and do not validate it. Failed validations are shown, not hidden.</Alert>
      <Panel title="Datasets" flush>
        <Load state={datasets}>{(rows) => (
          <table className="grid"><thead><tr><th>Dataset</th><th>System</th><th>Licence</th><th className="num">Imported files</th><th>Validations</th><th /></tr></thead>
            <tbody>{rows.map((d) => <tr key={d.key} className="click" onClick={() => setDs(ds === d.key ? null : d.key)}>
              <td><b>{d.key}</b><br /><span className="small muted">{d.version}</span></td><td className="wrap">{d.system}</td><td className="small wrap">{d.licence}</td>
              <td className="num">{d.imported_files || <Badge kind="warn">not imported</Badge>}</td>
              <td>{d.protocols.map((p: string) => <span key={p} style={{ marginRight: 6 }}>
                <button className="btn small" disabled={isActive(job)} onClick={(e) => { e.stopPropagation(); launch(ext.validate(p)); }}>{p}</button>
                {latest[p] && <Badge kind={tone(latest[p].status)}>{latest[p].status}</Badge>}</span>)}</td>
              <td><button className="btn ghost small" title="Downloads the protocol files from the publisher and verifies them" disabled={isActive(job)}
                onClick={(e) => { e.stopPropagation(); launch(ext.importDataset(d.key)); }}><Download />Import</button></td></tr>)}</tbody></table>)}</Load>
        {ds && datasets.data && (() => { const d = datasets.data.find((x) => x.key === ds)!; return (
          <div style={{ padding: 10 }}>
            <h2>{d.title}</h2>
            <p className="small"><a href={d.url} target="_blank" rel="noreferrer">{d.url}</a>{d.doi && <> · doi:{d.doi}</>} · {d.publisher}</p>
            <p className="small"><b>Citation.</b> {d.citation}</p>
            <p className="small"><b>Measured:</b> {d.measured.join(", ")}</p>
            <p className="small"><b>Not measured:</b> {d.not_measured.join(", ")}</p>
            {d.notes.map((n: string) => <p key={n} className="small muted">• {n}</p>)}
            <SignalMap ds={d.key} imported={d.imported_files > 0} />
          </div>); })()}
      </Panel>
      <div className="split" style={{ gridTemplateColumns: "280px minmax(0, 1fr)", minHeight: 0 }}>
        <Panel title="Recorded runs" flush>
          <Load state={runs}>{(rows) => rows.length === 0 ? <Empty title="No runs yet">Import a dataset and run its validation.</Empty> : (
            <div className="list">{[...rows].reverse().map((r) => (
              <button key={r.id} className={`list-item ${r.id === open ? "selected" : ""}`} onClick={() => setOpen(r.id)}>
                <span className="name">{r.benchmark} {r.protocol}<br /><span className="faint small">{r.id} · {r.created_utc}</span></span>
                <Badge kind={tone(r.status)}>{r.status}</Badge></button>))}</div>)}</Load>
        </Panel>
        <div>{open ? <RunView id={open} /> : <Panel><Empty title="Select a run">Measured-versus-predicted plots, residuals and metrics appear here.</Empty></Panel>}</div>
      </div>
    </div>
  );
}

function SignalMap({ ds, imported }: { ds: string; imported: boolean }) {
  const sig = useAsync(imported ? () => ext.signals(ds) : null, [ds, imported]);
  if (!imported) return <p className="small muted">Import the dataset to see its signal mapping.</p>;
  return (
    <Load state={sig}>{(rows) => rows.length === 0 ? null : (<>
      <p className="small"><b>Signal mapping</b> (trial {rows[0].trial})</p>
      <table className="grid"><thead><tr><th>Signal</th><th>Unit (SI)</th><th>Source field</th><th>Conversion</th><th className="num">Samples</th></tr></thead>
        <tbody>{Object.entries(rows[0].signals as Record<string, AnyJson>).slice(0, 14).map(([k, v]) =>
          <tr key={k}><td>{k}</td><td>{v.unit}</td><td className="small">{v.source_field}</td><td className="small">{v.conversion}</td><td className="num">{v.samples}</td></tr>)}</tbody></table>
    </>)}</Load>
  );
}
