import { useEffect } from "react";
import {
  Activity, BarChart3, Boxes, ChevronsLeft, ChevronsRight, Cog, Command as CommandIcon, Cpu, Crosshair,
  FileText, FlaskConical, FolderOpen, Gauge, GitCompare, Hourglass, Layers, ListChecks, Map, Moon, Radar,
  Ruler, Scale, ScanLine, Search, Settings, ShieldCheck, Sun, Target, TrendingUp, Trophy, Upload,
  Wrench, Factory, FlaskRound, LogOut,
} from "lucide-react";
import { api } from "./lib/api";
import { useAsync } from "./hooks/useAsync";
import { useApp, type Route } from "./stores/app";
import { Badge, ErrorBoundary } from "./components/ui";
import { ProjectsScreen } from "./features/projects";
import { FeaturesScreen, ImportScreen, WorkbenchScreen } from "./features/models";
import { TolerancesScreen, VirtualAssemblyScreen } from "./features/manufacturing";
import { MechanicsScreen } from "./features/mechanics";
import { BuilderScreen, MonitorScreen } from "./features/experiments";
import { ComparisonScreen, OptimisationScreen, RobustnessScreen, SensitivityScreen, WorstCaseScreen } from "./features/analysis";
import { CalibrationScreen } from "./features/calibration";
import { ReportsScreen, SettingsScreen } from "./features/reports";
import { AsBuiltScreen } from "./features/asbuilt";
import { BenchmarksScreen, ChallengeScreen, HardwareScreen, ProcessScreen, TrustScreen } from "./features/lab";
import { AdaptiveScreen, DegradationScreen, FidelityScreen, InvestigationScreen, WorkspaceScreen } from "./features/reliability";
import { CommandPalette } from "./components/CommandPalette";
import { PublicSite } from "./features/home";
import { ExternalValidationScreen } from "./features/external";

type Need = "project" | "model" | "experiment" | null;
const NAV: { group: string; items: [Route, string, typeof Cog, Need][] }[] = [
  { group: "Projects", items: [["projects", "Projects", FolderOpen, null]] },
  { group: "Models", items: [["import", "CAD import", Upload, "project"], ["workbench", "Assembly workbench", Boxes, "model"], ["features", "Features and datums", Crosshair, "model"]] },
  { group: "Manufacturing", items: [["tolerances", "Tolerances", Ruler, "model"], ["process", "Process batches", Factory, "model"], ["virtual", "Virtual assemblies", Layers, "model"], ["mechanics", "Mechanical model", Wrench, "model"]] },
  { group: "Inspection and test", items: [["asbuilt", "As-built inspection", ScanLine, "model"], ["hardware", "Hardware testing", Cpu, "model"], ["calibration", "Calibration", Cog, "model"]] },
  { group: "Experiments", items: [["builder", "Experiment builder", FlaskConical, "model"], ["monitor", "Live monitor", Activity, "project"], ["adaptive", "Adaptive experiment", Radar, "model"]] },
  { group: "Reliability", items: [["robustness", "Robustness", BarChart3, "experiment"], ["sensitivity", "Sensitivity", TrendingUp, "experiment"], ["investigate", "Failure investigation", Search, "experiment"],
    ["worstcase", "Worst case", Target, "experiment"], ["workspace", "Workspace analysis", Map, "model"], ["degradation", "Degradation", Hourglass, "model"], ["fidelity", "Model fidelity", Gauge, "model"]] },
  { group: "Optimisation", items: [["challenge", "Engineering Challenge", Trophy, "model"], ["optimisation", "Tolerance optimisation", Scale, "experiment"], ["comparison", "Design comparison", GitCompare, "experiment"]] },
  { group: "Evidence", items: [["trust", "Model trust", ShieldCheck, "model"], ["reports", "Reports", FileText, "project"], ["benchmarks", "Benchmarks", ListChecks, null], ["external", "External validation", FlaskRound, null]] },
];
const SCREENS: Record<Route, () => React.ReactElement> = {
  projects: ProjectsScreen, import: ImportScreen, workbench: WorkbenchScreen, features: FeaturesScreen, tolerances: TolerancesScreen,
  virtual: VirtualAssemblyScreen, mechanics: MechanicsScreen, builder: BuilderScreen, monitor: MonitorScreen, robustness: RobustnessScreen,
  sensitivity: SensitivityScreen, worstcase: WorstCaseScreen, optimisation: OptimisationScreen, comparison: ComparisonScreen,
  calibration: CalibrationScreen, reports: ReportsScreen, settings: SettingsScreen, asbuilt: AsBuiltScreen, process: ProcessScreen,
  hardware: HardwareScreen, adaptive: AdaptiveScreen, workspace: WorkspaceScreen, degradation: DegradationScreen, fidelity: FidelityScreen,
  investigate: InvestigationScreen, challenge: ChallengeScreen, trust: TrustScreen, benchmarks: BenchmarksScreen,
  external: ExternalValidationScreen,
};

export default function App() {
  const s = useApp();
  useEffect(() => { document.documentElement.dataset.theme = s.theme; }, [s.theme]);
  const health = useAsync(() => api.health(), []);
  const project = useAsync(s.projectId ? () => api.project(s.projectId as string) : null, [s.projectId, s.route]);
  // forget ids that no longer exist (for example after the workspace was replaced)
  useEffect(() => {
    if (project.error && s.projectId) s.setProject(null);
    if (project.data) {
      if (s.modelId && !project.data.models.some((m) => m.id === s.modelId)) s.setModel(null);
      if (s.experimentId && !project.data.experiments.some((e) => e.id === s.experimentId)) s.setExperiment(null);
    }
  }, [project.data, project.error]); // eslint-disable-line react-hooks/exhaustive-deps
  const model = project.data?.models.find((m) => m.id === s.modelId);
  const experiment = project.data?.experiments.find((e) => e.id === s.experimentId);
  const has: Record<Exclude<Need, null>, boolean> = { project: !!s.projectId, model: !!s.modelId, experiment: !!s.experimentId };
  const label = NAV.flatMap((g) => g.items).find((i) => i[0] === s.route)?.[1] ?? "Settings";
  const Screen = SCREENS[s.route];
  if (!s.user) return <PublicSite />;

  return (
    <div className="shell">
      <nav className={`nav ${s.navCollapsed ? "collapsed" : ""}`} aria-label="Main navigation">
        <div className="brand"><i className="mark" /><span>MotionProof</span></div>
        {NAV.map((g) => (
          <div key={g.group}>
            <div className="nav-group">{g.group}</div>
            {g.items.map(([route, text, Icon, need]) => (
              <button key={route} className={`nav-item ${s.route === route ? "active" : ""}`} onClick={() => s.go(route)} data-needs={need !== null && !has[need] ? need : undefined}
                title={need !== null && !has[need] ? `${text} (opens a ${need} chooser)` : text} aria-current={s.route === route ? "page" : undefined}>
                <Icon /><span className="nav-label">{text}</span></button>))}
          </div>))}
        <div className="nav-foot">
          <button className={`nav-item ${s.route === "settings" ? "active" : ""}`} onClick={() => s.go("settings")} title="Settings"><Settings /><span className="nav-label">Settings</span></button>
          <button className="nav-item" onClick={s.toggleNav} title={s.navCollapsed ? "Expand navigation" : "Collapse navigation"}>
            {s.navCollapsed ? <ChevronsRight /> : <ChevronsLeft />}<span className="nav-label">Collapse</span></button>
        </div>
      </nav>
      <header className="topbar">
        <div className="crumbs">
          <span>{project.data?.name ?? "No project"}</span>
          {model && <><span>/</span><span>{model.name}</span>{model.synthetic ? <Badge kind="warn" title="Generated reference geometry, not user hardware">synthetic</Badge> : null}</>}
          {experiment && <><span>/</span><span>{experiment.name}</span></>}
          <span>/</span><b>{label}</b>
        </div>
        <span className="spacer" />
        {project.data && project.data.models.length > 0 && (
          <select style={{ width: 210 }} value={s.modelId ?? ""} onChange={(e) => s.setModel(e.target.value || null)} aria-label="Current model">
            <option value="">select model…</option>{project.data.models.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select>)}
        {project.data && project.data.experiments.length > 0 && (
          <select style={{ width: 210 }} value={s.experimentId ?? ""} onChange={(e) => { const id = e.target.value || null; s.setExperiment(id);
            const m = project.data?.experiments.find((x) => x.id === id)?.model_id; if (m) s.setModel(m); }} aria-label="Current experiment">
            <option value="">select experiment…</option>{project.data.experiments.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}</select>)}
        {health.error ? <Badge kind="bad" title={health.error}>backend offline</Badge>
          : health.data && health.data.active_jobs > 0 ? <Badge kind="info" title="Background simulation jobs">{health.data.active_jobs} job running</Badge> : null}
        <button className="btn ghost small" onClick={() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true }))} title="Command palette (Ctrl+K)" aria-label="Command palette"><CommandIcon />Ctrl+K</button>
        <button className="btn ghost" onClick={s.toggleTheme} aria-label={`Switch to ${s.theme === "light" ? "dark" : "light"} theme`}>{s.theme === "light" ? <Moon /> : <Sun />}</button>
        <button className="btn ghost" onClick={s.logout} aria-label={`Sign out ${s.user}`} title={`Sign out ${s.user}`}><LogOut /></button>
      </header>
      <main className="main">
        <ErrorBoundary name={s.route}><Screen /></ErrorBoundary>
      </main>
      <CommandPalette />
      <div className="toasts" aria-live="polite">
        {s.toasts.map((t) => <div key={t.id} className={`toast ${t.kind}`} role="status" onClick={() => s.dismiss(t.id)}>{t.text}</div>)}
      </div>
    </div>
  );
}
