import { useState } from "react";
import { Download, FileJson, FileSpreadsheet, FileText, RefreshCw, Send } from "lucide-react";
import { api } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import { useApp } from "../stores/app";
import { Alert, Badge, Empty, Field, Load, NeedSelection, Panel, pct } from "../components/ui";
import { statusBadge } from "./projects";
import { ScenarioReplay } from "./analysis";
import { SettingsPage } from "./account";

export function ReportsScreen() {
  const { projectId, experimentId, setExperiment, setModel, go } = useApp();
  const list = useAsync(projectId ? () => api.experiments(projectId) : null, [projectId]);
  const report = useAsync(experimentId ? () => api.report(experimentId) : null, [experimentId]);
  const health = useAsync(() => api.health(), []);
  const [scenario, setScenario] = useState("S000001");
  const [replay, setReplay] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Awaited<ReturnType<typeof api.explain>> | null>(null);
  const [asking, setAsking] = useState(false);
  if (!projectId) return <NeedSelection what="project" action={<button className="btn primary" onClick={() => go("projects")}>Open projects</button>} />;
  const ask = async () => {
    if (!experimentId) return;
    setAsking(true);
    try { setAnswer(await api.explain(experimentId, question)); } catch (e) { setAnswer({ available: false, reason: (e as Error).message }); } finally { setAsking(false); }
  };
  const formats: ["pdf" | "markdown" | "json" | "csv", string, typeof FileText][] = [
    ["pdf", "PDF engineering report", FileText], ["markdown", "Markdown report", FileText], ["json", "JSON (full data)", FileJson], ["csv", "CSV (all scenarios)", FileSpreadsheet]];
  return (
    <div className="page">
      <div className="page-head"><h1>Reports and experiment history</h1></div>
      <div className="split two" style={{ gridTemplateColumns: "minmax(0, 1fr) 420px" }}>
        <div className="col">
          <Panel title="Experiment history" flush>
            <Load state={list}>{(rows) => rows.length === 0 ? <Empty title="No experiments yet" action={<button className="btn primary" onClick={() => go("builder")}>Build an experiment</button>} /> : (
              <table className="grid"><thead><tr><th>Experiment</th><th>Status</th><th>Created</th><th className="num">Scenarios</th><th className="num">Pass</th><th className="num">Failed</th><th className="num">Invalid</th></tr></thead><tbody>
                {rows.map((e) => (<tr key={e.id} className={`click ${e.id === experimentId ? "selected" : ""}`} onClick={() => { setExperiment(e.id); setModel(e.model_id); setReplay(null); setAnswer(null); }}>
                  <td>{e.name} <span className="faint">{e.id}</span></td><td>{statusBadge(e.status)}</td><td className="muted">{new Date(e.created).toLocaleString()}</td>
                  <td className="num">{e.summary?.scenarios.completed ?? "–"}</td><td className="num">{pct(e.summary?.all_constraints.pass_fraction)}</td>
                  <td className="num">{e.summary?.scenarios.failed ?? "–"}</td><td className="num">{e.summary?.scenarios.invalid ?? "–"}</td></tr>))}
              </tbody></table>)}</Load>
          </Panel>
          {experimentId && <Panel title={`Report for ${experimentId}`}>
            <Load state={report} label="Assembling the report">{(r) => (<div className="col">
              {r.synthetic_notice && <Alert kind="warn">{r.synthetic_notice}</Alert>}
              <div className="row wrap">{formats.map(([f, label, Icon]) => (
                <a key={f} className="btn" href={api.reportUrl(experimentId, f)} target="_blank" rel="noreferrer" download={f === "csv" || f === "pdf" ? "" : undefined}><Icon />{label}<Download /></a>))}</div>
              <div className="grid2">
                <div><h3>Assumptions</h3><ul className="small muted" style={{ paddingLeft: 18, margin: "4px 0" }}>{r.assumptions.length ? r.assumptions.map((a, i) => <li key={i}>{a}</li>) : <li>None recorded for this model.</li>}</ul></div>
                <div><h3>Limitations</h3><ul className="small muted" style={{ paddingLeft: 18, margin: "4px 0" }}>{r.limitations.map((a, i) => <li key={i}>{a}</li>)}</ul></div>
              </div>
              <p className="small faint">The report contains methodology, model fidelity, actual sample count, distributions, failures ({r.failure_count}), sensitivity, results, software versions ({Object.entries(r.versions).filter(([k]) => ["motionproof", "mujoco", "numpy", "scipy"].includes(k)).map(([k, v]) => `${k} ${v}`).join(", ")}) and limitations.</p>
            </div>)}</Load>
          </Panel>}
          {experimentId && <Panel title="Replay a stored scenario" actions={<>
            <div style={{ width: 130 }}><Field label="Scenario id"><input className="input mono" value={scenario} onChange={(e) => setScenario(e.target.value.trim())} /></Field></div>
            <button className="btn primary small" disabled={!/^S\d{6}$/.test(scenario)} onClick={() => setReplay(scenario)}><RefreshCw />Replay</button></>}>
            <p className="muted small">Re-simulates the scenario from the stored configuration and compares every metric with the stored result.</p>
          </Panel>}
          {experimentId && replay && <ScenarioReplay experimentId={experimentId} scenario={replay} />}
        </div>
        <Panel title="AI explanation (optional)" actions={<Badge kind={health.data?.ai.available ? "ok" : "plain"}>{health.data?.ai.available ? `local: ${health.data.ai.model}` : "not available"}</Badge>}
          foot="Explanations are generated text. Every number in MotionProof comes from the engineering engine, never from a language model.">
          {!health.data?.ai.available ? <Empty title="No local AI model">{health.data?.ai.reason ?? "Checking…"}. MotionProof works fully without it. To enable explanations, run a local Ollama server with a model installed.</Empty>
            : !experimentId ? <Empty title="Select an experiment" /> : (<div className="col">
              <Field label="Question about this experiment's evidence"><textarea rows={3} value={question} placeholder="e.g. Which tolerances drive the positioning failures?" onChange={(e) => setQuestion(e.target.value)} /></Field>
              <button className="btn primary" disabled={asking || question.trim().length === 0} onClick={ask}><Send />{asking ? "Generating…" : "Ask"}</button>
              {answer && (answer.available ? <><div style={{ whiteSpace: "pre-wrap" }}>{answer.answer}</div><p className="small faint">{answer.disclaimer}</p></> : <Alert kind="warn">{answer.reason}</Alert>)}
            </div>)}
        </Panel>
      </div>
    </div>
  );
}

export function SettingsScreen() {
  return <SettingsPage />;
}
