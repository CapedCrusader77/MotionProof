// Centralised API client. Every screen reads real backend data through these functions.
import type * as T from "./types";
import { useApp } from "../stores/app";

const BASE = "/api/v1";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<R>(path: string, init?: RequestInit): Promise<R> {
  let res: Response;
  try {
    res = await fetch(BASE + path, init);
  } catch {
    throw new ApiError(0, "Cannot reach the MotionProof backend. Start it with `motionproof serve`.");
  }
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      const body = (await res.json()) as { error?: string; detail?: unknown };
      if (body.error) message = body.error;
      else if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail))
        message = (body.detail as { loc: (string | number)[]; msg: string }[])
          .map((d) => `${d.loc.slice(1).join(".")}: ${d.msg}`).join("; ");
    } catch { /* keep the status text */ }
    // the session expired or was closed elsewhere: back to the sign-in page
    if (res.status === 401 && !path.startsWith("/auth/")) useApp.getState().logout();
    throw new ApiError(res.status, message);
  }
  return (await res.json()) as R;
}

const json = (method: string, body: unknown): RequestInit => ({
  method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});
export interface User { id: number; email: string; name: string; admin: boolean }
export const auth = {
  config: () => request<{ registration: "open" | "closed" }>("/auth/config"),
  createUser: (email: string, password: string, name: string) =>
    request<User>("/admin/users", json("POST", { email, password, name })),
  me: () => request<{ user: User }>("/auth/me"),
  login: (email: string, password: string) => request<{ user: User }>("/auth/login", json("POST", { email, password })),
  register: (email: string, password: string, name: string) =>
    request<{ user: User }>("/auth/register", json("POST", { email, password, name })),
  logout: () => request<{ ok: boolean }>("/auth/logout", { method: "POST" }),
  account: () => request<User & { sessions: number }>("/account"),
  rename: (name: string) => request<{ ok: boolean }>("/account/name", json("POST", { name })),
  endOtherSessions: () => request<{ ended: number }>("/account/sessions/end-others", { method: "POST" }),
  changePassword: (current: string, next: string) => request<{ ok: boolean }>("/account/password", json("POST", { current, new: next })),
  deleteAccount: (password: string) => request<{ ok: boolean }>("/account/delete", json("POST", { password })),
  users: () => request<(User & { created: number })[]>("/admin/users"),
  resetPassword: (id: number, next: string) => request<{ ok: boolean }>(`/admin/users/${id}/password`, json("POST", { new: next })),
  deleteUser: (id: number) => request<{ ok: boolean }>(`/admin/users/${id}`, { method: "DELETE" }),
};

const qs = (params: Record<string, string | number | undefined | null>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
};

export const api = {
  // server details (versions, workspace, jobs); needs a session. The public /health says only "ok".
  health: () => request<T.Health>("/system"),
  job: (id: string) => request<T.Job>(`/jobs/${id}`),
  cancelJob: (id: string) => request<T.Job>(`/jobs/${id}/cancel`, { method: "POST" }),

  projects: () => request<T.Project[]>("/projects"),
  project: (id: string) => request<T.ProjectDetail>(`/projects/${id}`),
  createProject: (name: string, description = "") => request<T.Project>("/projects", json("POST", { name, description })),
  deleteProject: (id: string) => request<{ deleted: string }>(`/projects/${id}${qs({ confirm: id })}`, { method: "DELETE" }),

  models: (projectId?: string) => request<T.ModelRow[]>(`/models${qs({ project_id: projectId })}`),
  model: (id: string) => request<T.ModelDetail>(`/models/${id}`),
  createReference: (projectId: string) => request<T.ModelRow>("/models/reference", json("POST", { project_id: projectId })),
  importModel: (projectId: string, files: File[], meshUnits: string) => {
    const form = new FormData();
    form.set("project_id", projectId);
    if (meshUnits) form.set("mesh_units", meshUnits);
    for (const f of files) form.append("files", f);
    return request<T.ModelRow & { inventory: { warnings: string[]; components: T.Component[]; units: T.Dict<string>; format: string } }>(
      "/models/import", { method: "POST", body: form });
  },
  validateModel: (id: string) => request<T.Readiness>(`/models/${id}/validate`, { method: "POST" }),
  meshUrl: (modelId: string, componentId: string, stamp: string) =>
    `${BASE}/models/${modelId}/meshes/${encodeURIComponent(componentId)}?v=${stamp}`,
  pose: (id: string, pose: T.Dict, values?: T.Dict | null) =>
    request<T.Pose>(`/models/${id}/pose`, json("POST", { pose, values: values ?? null })),
  suggestions: (id: string) => request<T.Dict<{ diameter: number; radius: number; length: number; external: boolean;
    axis_start: number[]; axis_direction: number[]; suggested_type: string; faces: number[] }[]>>(`/models/${id}/feature-suggestions`),
  saveFeature: (id: string, f: T.Feature) => request<T.Feature[]>(`/models/${id}/features`, json("POST", f)),
  deleteFeature: (id: string, fid: string) => request<unknown>(`/models/${id}/features/${encodeURIComponent(fid)}`, { method: "DELETE" }),
  configureMechanics: (body: { model_id: string } & Record<string, unknown>) =>
    request<T.ModelDetail>("/mechanics/configure", json("POST", body)),

  tolerances: (modelId: string) => request<T.ToleranceList>(`/tolerances${qs({ model_id: modelId })}`),
  createTolerance: (modelId: string, t: T.Tolerance) => request<T.ToleranceList>(`/tolerances${qs({ model_id: modelId })}`, json("POST", t)),
  updateTolerance: (modelId: string, t: T.Tolerance) =>
    request<T.ToleranceList>(`/tolerances/${encodeURIComponent(t.id)}${qs({ model_id: modelId })}`, json("PUT", t)),
  deleteTolerance: (modelId: string, id: string) =>
    request<T.ToleranceList>(`/tolerances/${encodeURIComponent(id)}${qs({ model_id: modelId })}`, { method: "DELETE" }),

  generateVariants: (modelId: string, method: string, samples: number, seed: number) =>
    request<T.VariantSet>("/assemblies/generate-variants", json("POST", { model_id: modelId, method, samples, seed })),
  variantDetail: (modelId: string, values: T.Dict) =>
    request<T.VariantDetail>("/assemblies/validate", json("POST", { model_id: modelId, values })),
  runTask: (modelId: string, task: T.Task, values: T.Dict = {}) =>
    request<T.SimResult>("/tasks", json("POST", { model_id: modelId, task, values })),

  experiments: (projectId?: string) => request<T.ExperimentRow[]>(`/experiments${qs({ project_id: projectId })}`),
  experiment: (id: string) => request<T.ExperimentDetail>(`/experiments/${id}`),
  createExperiment: (modelId: string, config: T.ExperimentConfig) =>
    request<T.ExperimentRow>("/experiments", json("POST", { model_id: modelId, config })),
  runExperiment: (id: string) => request<T.Job>(`/experiments/${id}/run`, { method: "POST" }),
  progress: (id: string) => request<T.Progress>(`/experiments/${id}/progress`),
  cancelExperiment: (id: string) => request<T.Job>(`/experiments/${id}/cancel`, { method: "POST" }),
  results: (id: string, status = "all", category?: string, limit = 200) =>
    request<{ total: number; results: T.Scenario[] }>(`/experiments/${id}/results${qs({ status, category, limit })}`),
  analysis: (id: string, metric?: string) => request<T.Analysis>(`/experiments/${id}/analysis${qs({ metric })}`),
  replay: (id: string, scenario: string) =>
    request<{ reproduced: boolean; differences: T.Dict<unknown>; stored: T.Scenario; replayed: T.Scenario; model_fingerprint_matches: boolean }>(
      `/experiments/${id}/replay`, json("POST", { scenario })),
  optimise: (id: string, body: Record<string, unknown>) => request<T.Job>(`/experiments/${id}/optimise`, json("POST", body)),
  analysisFile: <R,>(id: string, name: string) => request<T.AnalysisFile<R>>(`/experiments/${id}/analyses/${name}`),

  measurements: (projectId: string) => request<T.CsvPreview[]>(`/measurements${qs({ project_id: projectId })}`),
  importMeasurement: (projectId: string, file: File) => {
    const form = new FormData();
    form.set("project_id", projectId);
    form.set("file", file);
    return request<T.CsvPreview>("/measurements/import", { method: "POST", body: form });
  },
  calibrate: (body: Record<string, unknown>) => request<T.Job>("/calibration", json("POST", body)),
  calibration: (modelId: string) => request<T.AnalysisFile<T.CalibrationResult>>(`/calibration/${modelId}`),

  report: (id: string) => request<T.Report>(`/reports/${id}`),
  reportUrl: (id: string, format: "json" | "markdown" | "csv" | "pdf") => `${BASE}/reports/${id}?format=${format}`,
  explain: (experimentId: string, question: string) =>
    request<{ available: boolean; reason?: string; answer?: string; model?: string; disclaimer?: string }>(
      "/ai/explain", json("POST", { experiment_id: experimentId, question })),
};

// ---- advanced subsystems -------------------------------------------------------------------
export type AnyJson = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export interface Artifact {
  id: string; project_id: string; model_id: string | null; experiment_id: string | null;
  kind: string; name: string; status: string; created: string; summary: AnyJson | null;
}

export const adv = {
  artifacts: (kind?: string, projectId?: string, modelId?: string) =>
    request<Artifact[]>(`/artifacts${qs({ kind, project_id: projectId, model_id: modelId })}`),
  artifact: <R = AnyJson,>(id: string, part: string) => request<R>(`/artifacts/${id}/${part}`),
  importScan: (modelId: string, file: File, units: string, scanner: string, captureDate: string) => {
    const form = new FormData();
    form.set("model_id", modelId);
    if (units) form.set("units", units);
    if (scanner) form.set("scanner", scanner);
    if (captureDate) form.set("capture_date", captureDate);
    form.set("file", file);
    return request<AnyJson>("/scans/import", { method: "POST", body: form });
  },
  registerScan: (id: string, body: AnyJson) => request<T.Job>(`/scans/${id}/register`, json("POST", body)),
  analyseScan: (id: string, body: AnyJson) => request<T.Job>(`/scans/${id}/analyse`, json("POST", body)),
  scan: (id: string) => request<AnyJson>(`/scans/${id}`),
  decide: (scanId: string, mid: string, status: "approved" | "rejected") =>
    request<AnyJson>(`/scans/${scanId}/measurements/${encodeURIComponent(mid)}`, json("POST", { status })),
  asBuilt: (modelId: string) => request<AnyJson>(`/models/${modelId}/as-built`),
  trust: (modelId: string) => request<AnyJson>(`/models/${modelId}/trust`),
  batch: (body: AnyJson) => request<T.Job>("/manufacturing/batches", json("POST", body)),
  adaptive: (body: AnyJson) => request<T.Job>("/experiments/adaptive", json("POST", body)),
  workspace: (body: AnyJson) => request<T.Job>("/workspace/analyse", json("POST", body)),
  degradation: (body: AnyJson) => request<T.Job>("/degradation/experiments", json("POST", body)),
  fidelity: (body: AnyJson) => request<T.Job>("/fidelity/compare", json("POST", body)),
  rootcause: (experimentId: string, scenario: string) =>
    request<T.Job>("/rootcause", json("POST", { experiment_id: experimentId, scenario })),
  devices: () => request<AnyJson[]>("/hardware/devices"),
  hardware: (body: AnyJson) => request<T.Job>("/hardware/experiments", json("POST", body)),
  hardwareCsv: (id: string) => `${BASE}/hardware/experiments/${id}/measurements`,
  challenge: (modelId: string, config: AnyJson) =>
    request<T.Job & { challenge_id: string }>("/challenges", json("POST", { model_id: modelId, config })),
  benchmarks: () => request<AnyJson>("/benchmarks"),
  runBenchmarks: (ids?: string[]) => request<T.Job>("/benchmarks/run", json("POST", { ids: ids ?? null })),
};

// ---- external experimental validation
export const ext = {
  datasets: () => request<AnyJson[]>("/external/datasets"),
  protocols: () => request<AnyJson[]>("/external/protocols"),
  signals: (key: string) => request<AnyJson[]>(`/external/datasets/${key}/signals?limit=1`),
  importDataset: (key: string) => request<T.Job>(`/external/datasets/${key}/import`, { method: "POST" }),
  validate: (pid: string) => request<T.Job>(`/external/validate/${pid}`, { method: "POST" }),
  runs: () => request<AnyJson[]>("/external/runs"),
  run: (id: string) => request<AnyJson>(`/external/runs/${id}`),
};
