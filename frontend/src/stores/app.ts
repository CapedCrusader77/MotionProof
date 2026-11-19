import { create } from "zustand";

export type Route =
  | "projects" | "import" | "workbench" | "features" | "virtual" | "tolerances" | "mechanics"
  | "builder" | "monitor" | "robustness" | "sensitivity" | "worstcase" | "optimisation"
  | "comparison" | "calibration" | "reports" | "settings" | "asbuilt" | "process" | "hardware"
  | "adaptive" | "workspace" | "degradation" | "fidelity" | "investigate" | "challenge"
  | "trust" | "benchmarks" | "external";

export interface Toast { id: number; kind: "ok" | "error" | "info"; text: string }

interface AppState {
  route: Route;
  projectId: string | null;
  modelId: string | null;
  experimentId: string | null;
  theme: "light" | "dark";
  navCollapsed: boolean;
  toasts: Toast[];
  user: string | null;
  login: (email: string) => void;
  logout: () => void;
  go: (route: Route) => void;
  setProject: (id: string | null) => void;
  setModel: (id: string | null) => void;
  setExperiment: (id: string | null) => void;
  toggleTheme: () => void;
  toggleNav: () => void;
  notify: (kind: Toast["kind"], text: string) => void;
  dismiss: (id: number) => void;
}

const KEY = "motionproof.ui";
type Saved = Pick<AppState, "projectId" | "modelId" | "experimentId" | "theme" | "navCollapsed" | "user">;

function load(): Partial<Saved> {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "{}") as Partial<Saved>;
  } catch {
    return {};
  }
}
function save(s: AppState) {
  const data: Saved = {
    projectId: s.projectId, modelId: s.modelId, experimentId: s.experimentId, theme: s.theme,
    navCollapsed: s.navCollapsed, user: s.user,
  };
  try {
    localStorage.setItem(KEY, JSON.stringify(data));
  } catch { /* storage unavailable: preferences are simply not remembered */ }
}

const ROUTES: Route[] = ["projects", "import", "workbench", "features", "virtual", "tolerances",
  "mechanics", "builder", "monitor", "robustness", "sensitivity", "worstcase", "optimisation",
  "comparison", "calibration", "reports", "settings", "asbuilt", "process", "hardware", "adaptive",
  "workspace", "degradation", "fidelity", "investigate", "challenge", "trust", "benchmarks", "external"];
const fromHash = (): Route => {
  const h = window.location.hash.replace("#/", "") as Route;
  return ROUTES.includes(h) ? h : "projects";
};

let toastId = 1;
const saved = load();

export const useApp = create<AppState>((set, get) => ({
  route: fromHash(),
  projectId: saved.projectId ?? null,
  modelId: saved.modelId ?? null,
  experimentId: saved.experimentId ?? null,
  theme: saved.theme ?? "dark",
  navCollapsed: saved.navCollapsed ?? false,
  toasts: [],
  user: saved.user ?? null,
  login: (user) => { set({ user }); save(get()); },
  logout: () => { set({ user: null }); save(get()); },
  go: (route) => {
    window.location.hash = `#/${route}`;
    set({ route });
  },
  setProject: (projectId) => {
    if (projectId !== get().projectId) set({ projectId, modelId: null, experimentId: null });
    save(get());
  },
  setModel: (modelId) => { set({ modelId }); save(get()); },
  setExperiment: (experimentId) => { set({ experimentId }); save(get()); },
  toggleTheme: () => { set({ theme: get().theme === "light" ? "dark" : "light" }); save(get()); },
  toggleNav: () => { set({ navCollapsed: !get().navCollapsed }); save(get()); },
  notify: (kind, text) => {
    const id = toastId++;
    set({ toasts: [...get().toasts, { id, kind, text }] });
    window.setTimeout(() => get().dismiss(id), kind === "error" ? 9000 : 4000);
  },
  dismiss: (id) => set({ toasts: get().toasts.filter((t) => t.id !== id) }),
}));

window.addEventListener("hashchange", () => useApp.setState({ route: fromHash() }));
