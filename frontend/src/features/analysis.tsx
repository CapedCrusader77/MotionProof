import { useEffect, useState } from "react";
import { Play, RotateCcw } from "lucide-react";
import { api } from "../lib/api";
import { isActive, useAsync, useJob } from "../hooks/useAsync";
import { useExperiment } from "../hooks/useModel";
import { useApp } from "../stores/app";
import type { Allocation, Analysis, Comparison, Minimised, Oat, Proportion, Scenario, Sobol, WorstCase } from "../lib/types";
import { Alert, Badge, Empty, Field, Load, NeedSelection, Num, Panel, Spinner, Stat, Tabs, fmt, metricFmt, metricLabel, metricUnit, pct, signed } from "../components/ui";
import { HBars, Histogram, Lines, Points } from "../components/charts";
import { TraceCharts } from "./mechanics";

function NoExperiment() {
  const go = useApp((s) => s.go);
  return <NeedSelection what="experiment" action={<button className="btn primary" onClick={() => go("monitor")}>Open experiments</button>} />;
}
const interval = (p: Proportion) => (p.interval ? `${pct(p.interval[0])} – ${pct(p.interval[1])}` : "not available");

function MetricSelect({ metrics, value, onChange }: { metrics: string[]; value: string; onChange: (m: string) => void }) {
  return <select style={{ width: 230 }} value={value} onChange={(e) => onChange(e.target.value)} aria-label="Performance metric">
    {metrics.map((m) => <option key={m} value={m}>{metricLabel(m)}</option>)}</select>;
}

function useDefaultMetric(a: Analysis | null, exp: ReturnType<typeof useExperiment>["data"]) {
  const [metric, setMetric] = useState("");
  useEffect(() => {
    if (!a || (metric && a.metrics.includes(metric))) return;
    setMetric(exp?.manifest.config.constraints[0]?.metric ?? a.metrics[0] ?? "");
  }, [a, exp, metric]);
  return [metric, setMetric] as const;
}

/** Launch a background analysis and reload its stored result when the job ends. */
function useAnalysis<R>(experimentId: string | null, name: string) {
  const file = useAsync(experimentId ? () => api.analysisFile<R>(experimentId, name) : null, [experimentId, name]);
  const [jobId, setJobId] = useState<string | null>(null);
  const notify = useApp((s) => s.notify);
  useEffect(() => { if (file.data?.job && isActive(file.data.job)) setJobId(file.data.job.id); }, [file.data]);
  const job = useJob(jobId, (j) => { if (j.status === "failed") notify("error", j.error ?? "Analysis failed"); file.reload(); });
  const start = async (body: Record<string, unknown>) => {
    if (!experimentId) return;
    try { setJobId((await api.optimise(experimentId, { kind: name, ...body })).id); } catch (e) { notify("error", (e as Error).message); }
  };
  const cancel = () => { if (jobId) void api.cancelJob(jobId); };
  return { result: file.data?.result ?? null, loading: file.loading, job, busy: isActive(job), start, cancel };
}
function JobLine({ job, onCancel }: { job: ReturnType<typeof useJob>; onCancel: () => void }) {
  if (!isActive(job)) return null;
  const p = job!.progress;
  return <div className="row center"><Spinner label={typeof p.done === "number" ? `${p.done} of ${p.total} evaluations${p.best != null ? ` · best ${fmt(Number(p.best))}` : ""}` : "Running"} />
    <button className="btn small" onClick={onCancel}>Cancel</button></div>;
}

// ---------------------------------------------------------------- robustness

export function RobustnessScreen() {
  const { experimentId } = useApp();
  const exp = useExperiment();
  const a = useAsync(experimentId ? () => api.analysis(experimentId) : null, [experimentId]);
  const [category, setCategory] = useState<string | null>(null);
  const [status, setStatus] = useState("failed");
  const rows = useAsync(experimentId ? () => api.results(experimentId, category ? "all" : status, category ?? undefined, 300) : null, [experimentId, category, status]);
  const [picked, setPicked] = useState<Scenario | null>(null);
  if (!experimentId) return <NoExperiment />;
  return (
    <div className="page">
      <div className="page-head"><h1>Robustness analysis</h1><span className="sub">{exp.data?.name}</span></div>
      <Load state={a} label="Computing statistics">{(d) => {
        const s = d.summary;
        const cons = exp.data?.manifest.config.constraints ?? [];
        return (<>
          {exp.data?.manifest.model.synthetic && <Alert kind="warn">Synthetic reference design with assumed tolerances: these numbers demonstrate the method, they do not describe physical hardware.</Alert>}
          <div className="grid4">
            <Panel><Stat label="Scenarios completed" value={`${s.scenarios.completed} / ${s.scenarios.total}`} sub={`${s.scenarios.invalid} invalid simulations · ${s.scenarios.out_of_spec} with out-of-spec dimensions`} /></Panel>
            <Panel><Stat label="All constraints satisfied" value={pct(s.all_constraints.pass_fraction)} sub={`${s.all_constraints.passed} of ${s.all_constraints.n} valid scenarios`} /></Panel>
            <Panel><Stat label="Confidence interval" value={interval(s.all_constraints)} sub={s.all_constraints.interval_method === "none" ? s.all_constraints.note : s.all_constraints.interval_method} /></Panel>
            <Panel><Stat label="Failed scenarios" value={s.scenarios.failed} tone={s.scenarios.failed ? "neg" : "pos"} sub={`${s.method.sampling.replace(/_/g, " ")}, ${s.method.independent_draws ? "independent draws" : "non-independent design"}`} /></Panel>
          </div>
          {s.all_constraints.note && s.all_constraints.interval && <Alert kind="info">{s.all_constraints.note}.</Alert>}
          <div className="grid2">
            <Panel title="Constraints" flush>
              <table className="grid"><thead><tr><th>Constraint</th><th>Requirement</th><th className="num">Pass</th><th className="num">Interval</th><th className="num">Min margin</th><th className="num">Mean margin</th></tr></thead><tbody>
                {Object.entries(s.constraints).map(([name, c]) => { const [k, u] = metricUnit(c.metric ?? ""); return (
                  <tr key={name}><td>{name}</td><td>{metricLabel(c.metric ?? "")} {c.op} {fmt((c.limit ?? 0) * k)} {u}</td><td className="num">{pct(c.pass_fraction)}</td><td className="num">{interval(c)}</td>
                    <td className={`num ${(c.min_margin ?? 0) < 0 ? "neg" : ""}`}>{c.min_margin == null ? "–" : signed(c.min_margin, 3)}</td><td className="num">{c.mean_margin == null ? "–" : signed(c.mean_margin, 3)}</td></tr>); })}
              </tbody></table>
              <p className="small faint" style={{ padding: 8 }}>Margin is normalised by the limit; negative means the requirement is violated. {s.conditions.join(" · ")}.</p>
            </Panel>
            <Panel title="Failure categories" flush>
              {Object.keys(s.failure_categories).length === 0 ? <Empty title="No failures recorded">No scenario violated a constraint. This bounds the failure probability; it does not prove it is zero.</Empty> : (
                <table className="grid"><thead><tr><th>Category</th><th className="num">Scenarios</th><th className="num">Share</th><th /></tr></thead><tbody>
                  {Object.entries(s.failure_categories).sort((x, y) => y[1] - x[1]).map(([k, v]) => (
                    <tr key={k} className={`click ${category === k ? "selected" : ""}`} onClick={() => setCategory(category === k ? null : k)}>
                      <td><Badge kind="bad">{k.replace(/_/g, " ")}</Badge></td><td className="num">{v}</td><td className="num">{pct(v / Math.max(s.scenarios.completed, 1))}</td>
                      <td className="muted small">{category === k ? "showing below" : "click to list scenarios"}</td></tr>))}
                </tbody></table>)}
            </Panel>
          </div>
          <Panel title="Performance distributions">
            <div className="grid3">{cons.map((c) => { const [k, u] = metricUnit(c.metric); const h = d.histograms[c.metric]; return h ? (
              <div key={c.name}><div className="chart-title">{c.name}: {metricLabel(c.metric)} ({u || "–"}), n = {s.scenarios.valid}</div>
                <Histogram hist={h} scale={k} unit={u} limit={c.limit} failAbove={c.op === "<="} failBelow={c.op === ">="} /></div>) : null; })}</div>
          </Panel>
          <Panel title={category ? `Scenarios failing: ${category.replace(/_/g, " ")}` : "Scenarios"} flush
            actions={<>{category && <button className="btn small" onClick={() => setCategory(null)}>Clear filter</button>}
              {!category && <Tabs tabs={[["failed", "Failed"], ["passed", "Passed"], ["invalid", "Invalid"], ["all", "All"]]} value={status} onChange={setStatus} />}</>}>
            <Load state={rows}>{(r) => r.results.length === 0 ? <Empty title="No scenarios match this filter" /> : (
              <div className="table-wrap" style={{ maxHeight: 300 }}><table className="grid"><thead><tr><th>Scenario</th><th>Result</th>{cons.map((c) => <th key={c.name} className="num">{c.name}</th>)}<th>Failures</th></tr></thead><tbody>
                {r.results.map((x) => (<tr key={x.id} className={`click ${picked?.id === x.id ? "selected" : ""}`} onClick={() => setPicked(x)}>
                  <td>{x.id}</td><td>{!x.valid ? <Badge kind="warn">invalid</Badge> : x.passed ? <Badge kind="ok">pass</Badge> : <Badge kind="bad">fail</Badge>}</td>
                  {cons.map((c) => <td key={c.name} className={`num ${x.constraints[c.name]?.passed === false ? "neg" : ""}`}>{metricFmt(c.metric, x.metrics[c.metric])}</td>)}
                  <td className="wrap small">{x.failures.map((f) => f.name).join(", ") || x.message}</td></tr>))}
              </tbody></table>{r.total > r.results.length && <p className="small faint" style={{ padding: 8 }}>Showing {r.results.length} of {r.total}. Export the CSV for the full set.</p>}</div>)}</Load>
          </Panel>
          {picked && <ScenarioReplay experimentId={experimentId} scenario={picked.id} />}
        </>);
      }}</Load>
    </div>
  );
}

export function ScenarioReplay({ experimentId, scenario }: { experimentId: string; scenario: string }) {
  const r = useAsync(() => api.replay(experimentId, scenario), [experimentId, scenario]);
  return (
    <Panel title={`Replay of ${scenario}`}>
      <Load state={r} label="Re-simulating from the stored configuration">{(d) => (<div className="col">
        {d.reproduced ? <Alert kind="ok">Reproduced exactly: the fresh simulation matches every stored metric.</Alert>
          : <Alert kind="bad">Not reproduced. Differing metrics: {Object.keys(d.differences).join(", ") || "pass/fail status"}.</Alert>}
        <div className="row wrap">{d.replayed.failures.map((f, i) => <Badge key={i} kind="bad" title={f.constraint}>{f.category.replace(/_/g, " ")}: {f.name}</Badge>)}
          {d.replayed.out_of_spec.map((o) => <Badge key={o} kind="warn">out of spec: {o}</Badge>)}</div>
        {d.replayed.trace && <TraceCharts r={{ valid: true, metrics: d.replayed.metrics, message: "", trace: d.replayed.trace, measurements: [] }} />}
      </div>)}</Load>
    </Panel>
  );
}

// ---------------------------------------------------------------- sensitivity

export function SensitivityScreen() {
  const { experimentId } = useApp();
  const exp = useExperiment();
  const base = useAsync(experimentId ? () => api.analysis(experimentId) : null, [experimentId]);
  const [metric, setMetric] = useDefaultMetric(base.data, exp.data);
  const a = useAsync(experimentId && metric ? () => api.analysis(experimentId, metric) : null, [experimentId, metric]);
  const [tab, setTab] = useState<"rank" | "regression" | "oat" | "sobol">("rank");
  const [param, setParam] = useState<string | null>(null);
  const oat = useAnalysis<Oat>(experimentId, "one_at_a_time");
  const sobol = useAnalysis<Sobol>(experimentId, "sobol");
  const [baseSamples, setBaseSamples] = useState(32);
  if (!experimentId) return <NoExperiment />;
  const [k, u] = metricUnit(metric);
  return (
    <div className="page">
      <div className="page-head"><h1>Sensitivity explorer</h1><span className="sub">{exp.data?.name}</span><span className="spacer" />
        {base.data && <Field label="Performance metric"><MetricSelect metrics={base.data.metrics} value={metric} onChange={(m) => { setMetric(m); setParam(null); }} /></Field>}</div>
      <Tabs tabs={[["rank", "Rank correlation"], ["regression", "Regression and interactions"], ["oat", "One-at-a-time"], ["sobol", "Sobol indices"]]} value={tab} onChange={setTab} />
      {(tab === "rank" || tab === "regression") && <Load state={a} label="Analysing">{(d) => {
        const sens = d.sensitivity;
        if (!sens) return <Empty title="Select a metric" />;
        const top = sens.rank_correlation.rows.filter((r) => !r.note).slice(0, 14);
        const shown = param ?? top[0]?.parameter ?? null;
        const sc = shown ? d.scatter?.[shown] : undefined;
        return tab === "rank" ? (
          <div className="grid2">
            <Panel title="Parameter importance" foot={`${sens.rank_correlation.method}. ${sens.rank_correlation.caveat}. n = ${sens.scenarios}.`}>
              <HBars rows={top.map((r) => ({ name: r.parameter, value: r.rho, lo: r.interval[0], hi: r.interval[1] }))} domain={[-1, 1]} label="Spearman ρ with 95% interval" />
            </Panel>
            <div className="col">
              <Panel title={shown ? `Response: ${metricLabel(metric)} vs ${shown}` : "Response"}>
                {sc ? <Points points={sc.x.map((x, i) => ({ x, y: sc.y[i] * k, ok: sc.passed[i] }))} xLabel={shown ?? ""} yLabel={u || metric} height={230} />
                  : <Empty title="No scatter for this parameter">Scatter data are prepared for the six most correlated parameters.</Empty>}
              </Panel>
              <Panel title="Ranking" flush style={{ maxHeight: 280 }}>
                <table className="grid"><thead><tr><th>Parameter</th><th className="num">ρ</th><th className="num">95% interval</th><th>Direction of influence</th></tr></thead><tbody>
                  {sens.rank_correlation.rows.map((r) => (<tr key={r.parameter} className={`click ${shown === r.parameter ? "selected" : ""}`} onClick={() => setParam(r.parameter)}>
                    <td>{r.parameter}</td><td className="num">{signed(r.rho, 2)}</td><td className="num">{signed(r.interval[0], 2)} … {signed(r.interval[1], 2)}</td>
                    <td>{r.note ?? (r.direction.startsWith("not") ? <span className="faint">{r.direction}</span> : `${r.direction} ${metricLabel(metric)}`)}</td></tr>))}
                </tbody></table>
              </Panel>
            </div>
          </div>
        ) : (
          <div className="grid2">
            <Panel title="Variance share (linear model)" foot={sens.regression.note}>
              {sens.regression.r_squared == null ? <Empty title="Regression not available">{sens.regression.note}</Empty> : (<>
                <Alert kind={sens.regression.r_squared > 0.8 ? "ok" : "warn"}>The linear model explains R² = {fmt(sens.regression.r_squared, 3)} of the variance.
                  {sens.regression.r_squared <= 0.8 && " The response is not well described by a linear model: treat these shares as indicative only."}</Alert>
                <HBars rows={sens.regression.coefficients.slice(0, 12).map((c) => ({ name: c.parameter, value: c.src_squared }))} label="Squared standardised coefficient" /></>)}
            </Panel>
            <Panel title="Interaction screen" foot={sens.interactions.method ?? sens.interactions.note}>
              {sens.interactions.pairs.length === 0 ? <Empty title="No interaction screen">{sens.interactions.note}</Empty> : (<>
                <p className="small muted">R² linear {fmt(sens.interactions.r_squared_linear, 3)} → with pairwise terms {fmt(sens.interactions.r_squared_with_pairs, 3)}. A clear gain indicates interacting parameters.</p>
                <table className="grid"><thead><tr><th>Parameter pair</th><th className="num">Standardised coefficient</th></tr></thead><tbody>
                  {sens.interactions.pairs.slice(0, 10).map((p, i) => <tr key={i}><td>{p.parameters.join(" × ")}</td><td className="num">{signed(p.coefficient, 3)}</td></tr>)}</tbody></table></>)}
            </Panel>
          </div>);
      }}</Load>}
      {tab === "oat" && <Panel title="One-at-a-time sensitivity" actions={<><JobLine job={oat.job} onCancel={oat.cancel} />
        <button className="btn primary small" disabled={oat.busy || !metric} onClick={() => oat.start({ metric })}><Play />Run for {metricLabel(metric)}</button></>}
        foot="Each variable is moved alone from its design value to its lower and upper bound; every point is a real simulation. Interactions are not captured.">
        {!oat.result ? <Empty title="Not run yet">Runs 2 × variables + 1 simulations.</Empty> : (<>
          {oat.result.metric !== metric && <Alert kind="info">Stored result is for {metricLabel(oat.result.metric)}.</Alert>}
          <HBars rows={oat.result.rows.slice(0, 14).map((r) => ({ name: r.parameter, value: r.swing * metricUnit(oat.result!.metric)[0] }))} label={`change of ${metricLabel(oat.result.metric)} from lower to upper bound (${metricUnit(oat.result.metric)[1]})`} /></>)}
      </Panel>}
      {tab === "sobol" && <Panel title="Variance-based Sobol indices" actions={<><JobLine job={sobol.job} onCancel={sobol.cancel} />
        <Field label="Base samples (power of 2)"><div style={{ width: 90 }}><Num value={baseSamples} min={8} max={1024} step={1} onChange={setBaseSamples} /></div></Field>
        <button className="btn primary small" disabled={sobol.busy || !metric || (baseSamples & (baseSamples - 1)) !== 0} onClick={() => sobol.start({ metric, base_samples: baseSamples })}><Play />Compute</button></>}
        foot={sobol.result ? `${sobol.result.method}. ${sobol.result.evaluations} simulations.` : "Not computed. Sobol indices are only shown after this dedicated analysis has run; requires independent inputs."}>
        {!sobol.result ? <Empty title="Sobol indices have not been computed">Requires base samples × (variables + 2) simulations. Models with correlated tolerances are refused, because the method assumes independent inputs.</Empty> : (<>
          {sobol.result.metric !== metric && <Alert kind="info">Stored result is for {metricLabel(sobol.result.metric)}.</Alert>}
          <table className="grid"><thead><tr><th>Parameter</th><th className="num">First order</th><th className="num">95% interval</th><th className="num">Total order</th><th className="num">95% interval</th><th className="num">Interaction share</th></tr></thead><tbody>
            {sobol.result.indices.slice(0, 16).map((r) => <tr key={r.parameter}><td>{r.parameter}</td><td className="num">{fmt(r.first_order, 3)}</td><td className="num">{fmt(r.first_order_interval[0], 2)} … {fmt(r.first_order_interval[1], 2)}</td>
              <td className="num">{fmt(r.total_order, 3)}</td><td className="num">{fmt(r.total_order_interval[0], 2)} … {fmt(r.total_order_interval[1], 2)}</td><td className="num">{fmt(r.interaction_share, 3)}</td></tr>)}</tbody></table></>)}
      </Panel>}
    </div>
  );
}

// ---------------------------------------------------------------- worst case

export function WorstCaseScreen() {
  const { experimentId } = useApp();
  const exp = useExperiment();
  const base = useAsync(experimentId ? () => api.analysis(experimentId) : null, [experimentId]);
  const [metric, setMetric] = useDefaultMetric(base.data, exp.data);
  const [direction, setDirection] = useState("maximise");
  const [algorithm, setAlgorithm] = useState("differential_evolution");
  const [budget, setBudget] = useState(300);
  const [seed, setSeed] = useState(0);
  const wc = useAnalysis<WorstCase>(experimentId, "worst_case");
  const mini = useAnalysis<Minimised>(experimentId, "minimise");
  if (!experimentId) return <NoExperiment />;
  const r = wc.result;
  return (
    <div className="page">
      <div className="page-head"><h1>Worst-case explorer</h1><span className="sub">{exp.data?.name}</span></div>
      <Panel title="Search" actions={<><JobLine job={wc.job} onCancel={wc.cancel} />
        <button className="btn primary small" disabled={wc.busy || !metric || !(budget >= 10)} onClick={() => wc.start({ metric, direction, algorithm, budget, seed })}><Play />Search</button></>}>
        <div className="form three" style={{ gridTemplateColumns: "repeat(5, minmax(0, 1fr))" }}>
          <Field label="Objective metric">{base.data ? <MetricSelect metrics={base.data.metrics} value={metric} onChange={setMetric} /> : <Spinner />}</Field>
          <Field label="Direction"><select value={direction} onChange={(e) => setDirection(e.target.value)}><option value="maximise">maximise</option><option value="minimise">minimise</option></select></Field>
          <Field label="Algorithm"><select value={algorithm} onChange={(e) => setAlgorithm(e.target.value)}><option value="differential_evolution">differential evolution</option><option value="random">random search</option><option value="corners">boundary corners</option></select></Field>
          <Field label="Evaluation budget"><Num value={budget} min={10} max={20000} step={1} onChange={setBudget} /></Field>
          <Field label="Seed"><Num value={seed} step={1} onChange={setSeed} /></Field>
        </div>
      </Panel>
      {!r ? <Panel><Empty title="No search has been run">The optimiser proposes a manufacturing configuration; MotionProof then confirms it with a fresh simulation before reporting it.</Empty></Panel> : (<>
        <div className="grid4">
          <Panel><Stat label={`Worst ${metricLabel(r.metric)} found`} value={metricFmt(r.metric, r.confirmed_value)} sub={`nominal ${metricFmt(r.metric, r.nominal_value)}`} tone="neg" /></Panel>
          <Panel><Stat label="Fresh confirmation run" value={r.confirmation_matches ? "matches" : "differs"} tone={r.confirmation_matches ? "pos" : "neg"} sub={`proposed ${metricFmt(r.metric, r.proposed_value)}`} /></Panel>
          <Panel><Stat label="Violates a constraint" value={r.is_failure ? "yes" : "no"} tone={r.is_failure ? "neg" : "pos"} sub="model-predicted, not measured" /></Panel>
          <Panel><Stat label="Search" value={`${r.evaluations} evals`} sub={`${r.algorithm.replace(/_/g, " ")}, seed ${r.seed}`} /></Panel>
        </div>
        <Alert kind="info">{r.note}.</Alert>
        <div className="grid2">
          <Panel title="Search history">
            <Lines data={r.history.filter((h) => h.best !== null).map((h) => ({ n: h.evaluation, best: (h.best ?? 0) * metricUnit(r.metric)[0], value: (h.value ?? NaN) * metricUnit(r.metric)[0] }))}
              x="n" xLabel="evaluation" yLabel={metricUnit(r.metric)[1]} series={[{ key: "value", name: "candidate", color: "var(--faint)" }, { key: "best", name: "best so far", color: "var(--bad)" }]} height={230} />
          </Panel>
          <Panel title="Violated requirements" flush>
            {r.confirmation.failures.length === 0 ? <Empty title="No constraint is violated">The worst configuration found still satisfies every requirement within this search budget.</Empty> : (
              <table className="grid"><thead><tr><th>Category</th><th>Requirement</th><th className="num">Value</th></tr></thead><tbody>
                {r.confirmation.failures.map((f, i) => <tr key={i}><td><Badge kind="bad">{f.category.replace(/_/g, " ")}</Badge></td><td className="wrap">{f.constraint}</td><td className="num">{f.value === undefined ? "–" : fmt(f.value)}</td></tr>)}</tbody></table>)}
            <div style={{ padding: 8 }} className="row center">
              <button className="btn small" disabled={!r.is_failure || mini.busy} onClick={() => mini.start({})}><RotateCcw />Minimise this failure</button><JobLine job={mini.job} onCancel={mini.cancel} /></div>
            {mini.result && mini.result.status === "minimised" && <div style={{ padding: "0 8px 8px" }}>
              <Alert kind={mini.result.confirmed ? "ok" : "warn"}>{Object.keys(mini.result.essential_parameters).length} of {Object.keys(r.configuration).length} deviations are enough to keep the failure
                ({mini.result.confirmed ? "confirmed by simulation" : "confirmation failed"}): {Object.keys(mini.result.essential_parameters).join(", ")}.</Alert></div>}
          </Panel>
        </div>
        <div className="grid2">
          <Panel title="Manufacturing configuration vs nominal" flush style={{ maxHeight: 380 }}>
            <table className="grid"><thead><tr><th>Variable</th><th className="num">Nominal</th><th className="num">Worst case</th><th className="num">Position in range</th></tr></thead><tbody>
              {Object.entries(r.configuration).map(([name, v]) => { const [lo, hi] = r.bounds[name]; const pos = hi > lo ? (v - lo) / (hi - lo) : 0.5;
                const essential = mini.result?.essential_parameters && name in mini.result.essential_parameters;
                return <tr key={name}><td>{name} {essential && <Badge kind="bad">essential</Badge>}</td><td className="num">{fmt(r.nominal[name], 6)}</td><td className="num">{fmt(v, 6)}</td>
                  <td className="num">{pos < 0.02 ? "lower bound" : pos > 0.98 ? "upper bound" : pct(pos, 0)}</td></tr>; })}
            </tbody></table>
          </Panel>
          <Panel title="Confirmation simulation traces">{r.confirmation.trace ? <TraceCharts r={{ valid: true, metrics: r.confirmation.metrics, message: "", trace: r.confirmation.trace, measurements: [] }} /> : <Empty title="No trace" />}</Panel>
        </div>
      </>)}
    </div>
  );
}

// ---------------------------------------------------------------- optimisation

export function OptimisationScreen() {
  const { experimentId, modelId } = useApp();
  const exp = useExperiment();
  const tols = useAsync(modelId ? () => api.tolerances(modelId) : null, [modelId]);
  const base = useAsync(experimentId ? () => api.analysis(experimentId) : null, [experimentId]);
  const [metric, setMetric] = useDefaultMetric(base.data, exp.data);
  const [chosen, setChosen] = useState<string[]>([]);
  const [costs, setCosts] = useState<Record<string, number>>({});
  const [candidates, setCandidates] = useState(12);
  const [samples, setSamples] = useState(60);
  const [target, setTarget] = useState(0.95);
  const al = useAnalysis<Allocation>(experimentId, "allocation");
  const [pick, setPick] = useState<string | null>(null);
  if (!experimentId) return <NoExperiment />;
  const scalable = (tols.data?.tolerances ?? []).filter((t) => ["uniform", "normal", "truncated_normal"].includes(t.distribution.type));
  const priced = chosen.some((c) => Number.isFinite(costs[c]));
  const start = () => al.start({ allocation: { tolerances: chosen, candidates, samples, verify_samples: Math.max(4 * samples, 100), seed: 0, objective_metric: metric, target_pass_fraction: target,
    costs: Object.fromEntries(chosen.filter((c) => Number.isFinite(costs[c]) && costs[c] > 0).map((c) => [c, { coefficient: costs[c] }])) } });
  const r = al.result;
  const [k, u] = metricUnit(metric);
  const sel = r?.candidates.find((c) => c.id === (pick ?? r.recommended ?? "current"));
  return (
    <div className="page">
      <div className="page-head"><h1>Tolerance optimisation</h1><span className="sub">{exp.data?.name}</span></div>
      <div className="split two" style={{ gridTemplateColumns: "400px minmax(0, 1fr)" }}>
        <Panel title="Setup" actions={<><JobLine job={al.job} onCancel={al.cancel} /><button className="btn primary small" disabled={al.busy || chosen.length === 0 || !metric} onClick={start}><Play />Run screen</button></>}
          foot="Each candidate scales the spread of the selected tolerances (below 1 tightens). All candidates use the same random numbers and are evaluated with real simulations.">
          <div className="form">
            <Field label="Objective (95% quantile of)" wide>{base.data ? <MetricSelect metrics={base.data.metrics} value={metric} onChange={setMetric} /> : <Spinner />}</Field>
            <Field label="Candidates"><Num value={candidates} min={2} max={200} step={1} onChange={setCandidates} /></Field>
            <Field label="Scenarios per candidate"><Num value={samples} min={10} max={5000} step={1} onChange={setSamples} /></Field>
            <Field label="Required pass fraction" wide><Num value={target} min={0.01} max={1} onChange={setTarget} /></Field>
          </div>
          <h3 style={{ margin: "10px 0 4px" }}>Tolerance variables and cost coefficients</h3>
          <div className="table-wrap" style={{ maxHeight: 300 }}><table className="grid"><thead><tr><th /><th>Tolerance</th><th className="num">Cost coefficient</th></tr></thead><tbody>
            {scalable.map((t) => (<tr key={t.id}><td><input type="checkbox" checked={chosen.includes(t.id)} aria-label={`Optimise ${t.id}`}
              onChange={(e) => setChosen(e.target.checked ? [...chosen, t.id] : chosen.filter((c) => c !== t.id))} /></td><td>{t.id}</td>
              <td style={{ width: 120 }}><Num value={costs[t.id] ?? NaN} min={0} disabled={!chosen.includes(t.id)} onChange={(v) => setCosts({ ...costs, [t.id]: v })} ariaLabel={`Cost coefficient for ${t.id}`} /></td></tr>))}
          </tbody></table></div>
          <Alert kind={priced ? "info" : "warn"}>{priced ? "Cost = Σ coefficient ÷ scale, using your coefficients. It is an estimate, not a quotation."
            : "No cost data entered: a unit coefficient is used and the result is a relative cost index, not a price."}</Alert>
        </Panel>
        {!r ? <Panel><Empty title="No allocation has been run">Select tolerance variables and run the screen to see the cost–performance trade-off.</Empty></Panel> : r.status !== "completed" ? <Panel><Alert kind="info">The run was cancelled.</Alert></Panel> : (
          <div className="col">
            <Panel title="Cost versus performance" foot={`${r.method}. Cost axis: ${r.cost_label}.`}>
              <Points points={r.candidates.map((c) => ({ x: c.cost, y: c.objective * k, ok: c.pass_fraction >= r.target_pass_fraction, label: c.id, mark: c.pareto }))}
                xLabel={r.cost_label.split(" (")[0]} yLabel={`${r.objective.split(" of ")[0]} ${u}`} height={250} onPick={setPick} />
              <p className="small muted">Green diamonds are non-dominated candidates; red points miss the required pass fraction. Click a point or a row to inspect it.</p>
            </Panel>
            <Panel title="Candidate specifications" flush style={{ maxHeight: 250 }}>
              <table className="grid"><thead><tr><th>Candidate</th><th className="num">Cost</th><th className="num">{r.objective}</th><th className="num">Pass</th><th className="num">95% interval</th><th /></tr></thead><tbody>
                {[...r.candidates].sort((a, b) => a.cost - b.cost).map((c) => (<tr key={c.id} className={`click ${sel?.id === c.id ? "selected" : ""}`} onClick={() => setPick(c.id)}>
                  <td>{c.id}</td><td className="num">{fmt(c.cost)}</td><td className="num">{fmt(c.objective * k)} {u}</td><td className="num">{pct(c.pass_fraction)}</td><td className="num">{pct(c.pass_interval[0])} – {pct(c.pass_interval[1])}</td>
                  <td>{c.id === "current" && <Badge>current</Badge>} {c.pareto && <Badge kind="ok">Pareto</Badge>} {c.id === r.recommended && <Badge kind="info">recommended</Badge>}</td></tr>))}
              </tbody></table>
            </Panel>
            <div className="grid2">
              <Panel title={sel ? `Scales of ${sel.id}` : "Scales"} flush>{sel && <table className="grid"><thead><tr><th>Tolerance</th><th className="num">Width scale</th><th /></tr></thead><tbody>
                {Object.entries(sel.scales).map(([t, s]) => <tr key={t}><td>{t}</td><td className="num">×{fmt(s, 3)}</td><td className="muted small">{s < 0.98 ? "tighter" : s > 1.02 ? "looser" : "unchanged"}</td></tr>)}</tbody></table>}</Panel>
              <Panel title="Verification of the recommendation">
                {!r.recommended ? <Alert kind="warn">{r.note}</Alert> : !r.verification ? <Alert kind="warn">Verification did not complete.</Alert> : (
                  <div className="col"><Alert kind={r.verification.meets_target ? "ok" : "bad"}>Re-run of {r.recommended} with {r.verification.valid} fresh scenarios (independent seed {r.verification.seed}):
                    pass fraction {pct(r.verification.pass_fraction)} ({pct(r.verification.pass_interval[0])} – {pct(r.verification.pass_interval[1])}),
                    {r.verification.meets_target ? " meets" : " does not meet"} the required {pct(r.target_pass_fraction, 0)}.</Alert>
                    <p className="small muted">A candidate is reported as successful only after this independent verification run.</p></div>)}
              </Panel>
            </div>
          </div>)}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- comparison

export function ComparisonScreen() {
  const { experimentId, modelId } = useApp();
  const exp = useExperiment();
  const tols = useAsync(modelId ? () => api.tolerances(modelId) : null, [modelId]);
  const cmp = useAnalysis<Comparison>(experimentId, "comparison");
  const [variants, setVariants] = useState<{ name: string; scale: number; tolerances: string[] }[]>([{ name: "tightened", scale: 0.5, tolerances: [] }]);
  const [samples, setSamples] = useState(100);
  if (!experimentId) return <NoExperiment />;
  const scalable = (tols.data?.tolerances ?? []).filter((t) => ["uniform", "normal", "truncated_normal"].includes(t.distribution.type)).map((t) => t.id);
  const ok = variants.every((v) => v.name.trim() && v.name !== "current" && v.tolerances.length > 0 && v.scale > 0) && new Set(variants.map((v) => v.name)).size === variants.length;
  const start = () => cmp.start({ samples, seed: 0, variants: { current: {}, ...Object.fromEntries(variants.map((v) => [v.name, Object.fromEntries(v.tolerances.map((t) => [t, v.scale]))])) } });
  const r = cmp.result;
  const cons = exp.data?.manifest.config.constraints ?? [];
  const shown = r ? [...new Set([...cons.map((c) => c.metric), "backlash", "ee_error_max", "torque_utilisation_peak"])].filter((m) => r.metrics.includes(m)) : [];
  return (
    <div className="page">
      <div className="page-head"><h1>Design comparison</h1><span className="sub">{exp.data?.name}</span></div>
      <Panel title="Specification variants" actions={<><JobLine job={cmp.job} onCancel={cmp.cancel} />
        <Field label="Scenarios each"><div style={{ width: 90 }}><Num value={samples} min={10} max={5000} step={1} onChange={setSamples} /></div></Field>
        <button className="btn small" onClick={() => setVariants([...variants, { name: `variant_${variants.length + 1}`, scale: 0.5, tolerances: [] }])}>Add variant</button>
        <button className="btn primary small" disabled={cmp.busy || !ok} onClick={start}><Play />Compare</button></>}
        foot="Every variant is compared with the current specification using the same random numbers, the same task and the same constraints.">
        <div className="col">{variants.map((v, i) => { const upd = (p: Partial<typeof v>) => setVariants(variants.map((x, j) => (j === i ? { ...x, ...p } : x))); return (
          <div key={i} className="row center wrap">
            <div style={{ width: 170 }}><Field label="Variant name"><input className="input" value={v.name} onChange={(e) => upd({ name: e.target.value })} /></Field></div>
            <div style={{ width: 120 }}><Field label="Width scale"><Num value={v.scale} min={0.05} max={5} onChange={(s) => upd({ scale: s })} /></Field></div>
            <div className="grow"><Field label={`Tolerances scaled (${v.tolerances.length})`}>
              <select multiple size={4} style={{ height: 78 }} value={v.tolerances} onChange={(e) => upd({ tolerances: Array.from(e.target.selectedOptions, (o) => o.value) })} aria-label="Tolerances to scale">
                {scalable.map((t) => <option key={t}>{t}</option>)}</select></Field></div>
            <button className="btn ghost small" disabled={variants.length === 1} onClick={() => setVariants(variants.filter((_, j) => j !== i))}>Remove</button>
          </div>); })}</div>
      </Panel>
      {!r ? <Panel><Empty title="No comparison has been run">Define a revised tolerance specification above and compare it with the current one.</Empty></Panel> : (
        <Panel title="Comparison" flush foot={`${r.method}. ${r.samples} scenarios per variant, seed ${r.seed}.`}>
          <table className="grid"><thead><tr><th>Quantity</th>{Object.keys(r.variants).map((n) => <th key={n} className="num">{n}</th>)}</tr></thead><tbody>
            <tr><td>All constraints satisfied</td>{Object.values(r.variants).map((v, i) => <td key={i} className="num">{pct(v.pass_fraction)} <span className="faint">({v.pass_interval ? `${pct(v.pass_interval[0], 0)}–${pct(v.pass_interval[1], 0)}` : "–"})</span></td>)}</tr>
            {cons.map((c) => <tr key={c.name}><td>Constraint “{c.name}” pass fraction</td>{Object.values(r.variants).map((v, i) => <td key={i} className="num">{pct(v.constraint_pass_fraction[c.name])}</td>)}</tr>)}
            {shown.flatMap((m) => (["mean", "p95", "max"] as const).map((q) => (
              <tr key={`${m}${q}`}><td>{metricLabel(m)} — {q === "p95" ? "95% quantile" : q}</td>{Object.values(r.variants).map((v, i) => <td key={i} className="num">{metricFmt(m, v.metrics[m]?.[q])}</td>)}</tr>)))}
            <tr><td>Scaled tolerances</td>{Object.values(r.variants).map((v, i) => <td key={i} className="num wrap small">{Object.entries(v.scales).map(([t, s]) => `${t} ×${s}`).join(", ") || "none (current specification)"}</td>)}</tr>
          </tbody></table>
        </Panel>)}
    </div>
  );
}
