// Typed mirrors of the MotionProof REST API payloads.

export type Dict<T = number> = Record<string, T>;

export interface Project {
  id: string; name: string; description: string; demo: number; created: string;
  models?: number | ModelRow[]; experiments?: number | ExperimentRow[];
}
export interface ProjectDetail extends Omit<Project, "models" | "experiments"> {
  models: ModelRow[]; experiments: ExperimentRow[];
}
export interface ModelRow {
  id: string; project_id: string; name: string; kind: string; synthetic: number; created: string;
}
export interface Component {
  id: string; name: string; body: string; group: string; mesh: string | null;
  mesh_units: string; valid?: boolean; volume_mm3?: number | null; area_mm2?: number;
  mass_kg?: number | null; density_kg_m3?: number | null; com_m?: number[]; com_mm?: number[];
  bbox?: number[][]; bbox_mm?: number[][]; note?: string; source?: string;
  inertia_com_kgm2?: number[][];
}
export type Distribution =
  | { type: "uniform"; low: number; high: number }
  | { type: "normal"; mean: number; std: number }
  | { type: "truncated_normal"; mean: number; std: number; low: number; high: number }
  | { type: "lognormal"; mu: number; sigma: number }
  | { type: "discrete"; values: number[]; probabilities?: number[] | null }
  | { type: "empirical"; samples: number[] };

export interface GeometryRef {
  kind: "cylinder" | "plane" | "axis" | "point" | "none";
  point?: number[] | null; direction?: number[] | null; radius?: number | null;
  length?: number | null; face_index?: number | null;
}
export interface Feature {
  id: string; component: string; type: string; nominal: Dict; unit: string;
  datum?: string | null; mates_with?: string | null; geometry: GeometryRef; source: string;
  status: "confirmed" | "suggested"; note?: string | null;
}
export interface Tolerance {
  id: string; component: string; feature?: string | null; parameter: string;
  characteristic: string; category: "dimensional" | "geometric" | "assembly" | "mechanical";
  nominal: number; upper: number; lower: number; unit: string; datum?: string | null;
  zone_group?: string | null; distribution: Distribution; correlation_group?: string | null;
  source: string; confidence: "specified" | "measured" | "estimated" | "assumed";
  verification: "unverified" | "measured" | "inspected";
  process?: { mean: number; std: number; sample_size?: number | null; basis: string } | null;
  note?: string | null;
}
export interface Correlation {
  parameters: [string, string]; coefficient: number; basis: "measured" | "assumed";
  note?: string | null;
}
export interface Motor {
  model?: string | null; continuous_torque: number; peak_torque: number; max_speed: number;
  torque_speed: [number, number][]; rotor_inertia: number; friction_torque: number;
  source: string; confidence: string;
}
export interface Gearbox {
  ratio: number; efficiency: number; backlash: number; stiffness: number;
  damping_ratio: number; source: string; confidence: string;
}
export interface Drive {
  motor: Motor; gearbox: Gearbox; controller: { bandwidth: number };
  friction: number; damping: number;
}
export interface GearStage {
  id: string; joint: string; order: number; sun_teeth: number; planet_teeth: number;
  ring_teeth: number; planets: number; module: number; pressure_angle: number;
}
export interface Spec {
  schema: string; name: string; description: string; synthetic: boolean;
  source: { kind: string; generator?: string | null; file?: string | null };
  fidelity: string; features: Feature[]; datums: { id: string; feature: string; type: string }[];
  tolerances: Tolerance[]; correlations: Correlation[];
  fits: { id: string; shaft: string; bore: string; role: string; joint?: string | null }[];
  gear_stages: GearStage[]; drives: Dict<Drive>; held_joints: Dict;
  effects: { tolerance: string; joint: string; target: string; mode: string; gain: number }[];
  end_effector?: { body: string; offset: number[] } | null;
  simulation: { timestep: number; gravity: number[] }; assumptions: string[];
  radial_supports: { joint: string; bearing_span: number }[];
}
export interface ModelDetail extends ModelRow {
  fingerprint: string; geometry_fingerprint: string; spec: Spec; components: Component[];
  units: Dict<string>; import_warnings: string[]; joints: string[]; has_dynamics: boolean;
  source_file?: string | null;
  dynamics?: { joints: { name: string; type: string; range: number[] }[] } | null;
}
export interface Check { area: string; status: "ok" | "warning" | "error" | "info"; message: string }
export interface Finding { tolerance: string | null; severity: string; message: string }
export interface Readiness {
  status: "ready" | "ready_with_warnings" | "blocked"; checks: Check[];
  tolerance_findings: Finding[]; fidelity: string;
}
export interface ToleranceReviewRow {
  id: string; design_value: number; lower_limit: number; upper_limit: number; mean: number;
  std: number; fraction_out_of_spec: number; curve: { x: number[]; density: number[] };
  capability: { cp: number; cpk: number; basis: string; warnings: string[] } | null;
}
export interface FitRange {
  fit: string; min_clearance: number; max_clearance: number; unit: string; class: string;
}
export interface ToleranceList {
  tolerances: Tolerance[]; correlations: Correlation[]; review: ToleranceReviewRow[];
  findings: Finding[]; fits: FitRange[];
}
export interface JointVariant {
  joint: string; ratio: number; backlash: number; efficiency: number; stiffness: number;
  friction: number; damping: number; torque_scale: number; radial_play: number;
  tilt_x: number; tilt_y: number; offset: number[]; zero_offset: number;
}
export interface FitResult {
  fit: string; shaft: number; bore: number; clearance: number; unit: string; state: string;
  violation: string | null;
}
export interface StageResult {
  stage: string; ratio: number; backlash_angle: number; min_mesh_backlash_mm: number;
  binding: boolean; te_amplitude_input: number;
}
export interface Variant {
  id?: string; values: Dict; joints: Dict<JointVariant>; fits: FitResult[];
  stages: StageResult[]; out_of_spec: string[];
  violations: { category: string; subject: string; message: string }[]; levels: Dict<string>;
}
export interface VariantSet { method: string; seed: number; note: string; nominal: Variant; variants: Variant[] }
export interface Deviation {
  tolerance: string; component: string; feature: string | null; parameter: string; unit: string;
  nominal: number; actual: number; deviation: number; zone_fraction: number; in_spec: boolean;
}
export interface VariantDetail {
  variant: Variant; nominal: Variant; deviations: Deviation[]; levels_note: string;
  geometry: {
    level: string; measured_dimensions_mm: Dict; mount_pattern_shift_mm: Dict;
    interfaces: Dict<Dict>; changed_components: { component: string; volume_change_mm3: number; com_shift_mm: number }[];
  } | null;
}
export interface Pose {
  bodies: Dict<{ pos: number[]; quat: number[] }>;
  joints?: { name: string; anchor: number[]; axis: number[]; range: number[] | null; driven: boolean }[];
}
export type Task =
  | { type: "point_to_point"; start: Dict; target: Dict; duration: number; settle?: number; payload_mass?: number }
  | { type: "reversal"; target: Dict; joint: string; excursion?: number; move_time?: number; settle?: number; payload_mass?: number }
  | { type: "static_hold"; pose: Dict; duration?: number; payload_mass?: number }
  | { type: "repeat_cycles"; a: Dict; b: Dict; cycles?: number; move_time?: number; settle?: number; payload_mass?: number }
  | { type: "workspace_sweep"; poses: Dict[]; move_time?: number; settle?: number; payload_mass?: number };
export type Trace = Dict<number[]>;
export interface SimResult {
  valid: boolean; metrics: Dict; message: string; trace: Trace; fidelity?: string;
  measurements: { label: string; time: number; ee_error: number; angle_error: Dict }[];
  variant?: Variant;
}
export interface Constraint { name: string; metric: string; op: "<=" | ">="; limit: number }
export interface ExperimentConfig {
  name: string; task: Task;
  sampling: { method: string; samples: number; seed: number; replicates: number };
  operating: Dict<Distribution>; constraints: Constraint[]; fixed?: Dict;
}
export interface Proportion {
  n: number; passed: number; failed: number; pass_fraction: number | null;
  interval: [number, number] | null; interval_method: string; note?: string;
  metric?: string; op?: string; limit?: number; min_margin?: number | null; mean_margin?: number | null;
}
export interface Summary {
  scenarios: { total: number; completed: number; valid: number; invalid: number; passed: number; failed: number; out_of_spec: number };
  all_constraints: Proportion; constraints: Dict<Proportion>; failure_categories: Dict;
  metrics: Dict<{ mean: number; std: number; min: number; p05: number; p50: number; p95: number; max: number }>;
  method: { sampling: string; independent_draws: boolean; replicates: number; notes: string[] };
  conditions: string[];
}
export interface ExperimentRow {
  id: string; project_id: string; model_id: string; name: string; status: string; created: string;
  summary: { scenarios: Summary["scenarios"]; all_constraints: Proportion; failure_categories: Dict } | null;
}
export interface ExperimentDetail extends ExperimentRow {
  manifest: {
    id: string; name: string; created: string; config: ExperimentConfig; versions: Dict<string>;
    model: { name: string; synthetic: boolean; fingerprint: string; fidelity: string };
    design: { names: string[]; scenarios: number; independent: boolean; notes: string[] };
  };
  analyses: string[];
}
export interface Job {
  id: string; kind: string; subject: string; status: "queued" | "running" | "completed" | "failed" | "cancelled";
  progress: Dict<number | string | null>; error: string | null; elapsed?: number;
}
export interface Progress { status: string; job: Job | null; done: number; total: number; progress: Dict<number | string> }
export interface Failure { category: string; severity: string; constraint: string; name: string; value?: number; limit?: number }
export interface Scenario {
  id: string; index: number; replicate: number; valid: boolean; passed: boolean; message: string;
  values: Dict; operating: Dict; metrics: Dict; failures: Failure[]; out_of_spec: string[];
  constraints: Dict<{ value: number; passed: boolean; margin: number }>;
  trace?: Trace; variant?: Variant;
}
export interface Hist { x: number[]; count: number[]; width?: number }
export interface RankRow { parameter: string; rho: number; interval: [number, number]; p_value: number; direction: string; note?: string }
export interface Sensitivity {
  metric: string; scenarios: number;
  rank_correlation: { method: string; caveat: string; rows: RankRow[] };
  regression: { method: string; r_squared: number | null; note: string; coefficients: { parameter: string; src: number; src_squared: number }[] };
  interactions: { pairs: { parameters: string[]; coefficient: number }[]; r_squared_linear?: number; r_squared_with_pairs?: number; method?: string; note?: string };
}
export interface Analysis {
  summary: Summary; histograms: Dict<Hist>; metrics: string[]; variables: string[];
  sensitivity?: Sensitivity; scatter?: Dict<{ x: number[]; y: number[]; passed: boolean[] }>;
}
export interface AnalysisFile<T> { available: boolean; job: Job | null; result?: T }
export interface WorstCase {
  status: string; metric: string; direction: string; algorithm: string; seed: number; evaluations: number;
  proposed_value: number; confirmed_value: number; confirmation_matches: boolean; nominal_value: number;
  is_failure: boolean; configuration: Dict; nominal: Dict; bounds: Dict<[number, number]>;
  confirmation: Scenario; history: { evaluation: number; value: number | null; best: number | null }[]; note: string;
}
export interface Minimised {
  status: string; failure_categories: string[]; returned_to_nominal: string[]; confirmed: boolean;
  essential_parameters: Dict<{ value: number; nominal: number }>;
}
export interface Candidate {
  id: string; scales: Dict; cost: number; valid: number; objective: number; mean: number;
  pass_fraction: number; pass_interval: [number, number]; pareto: boolean;
}
export interface Allocation {
  status: string; method: string; cost_label: string; objective: string; target_pass_fraction: number;
  tolerances: string[]; candidates: Candidate[]; recommended: string | null; note: string | null;
  verification: { valid: number; pass_fraction: number; pass_interval: [number, number]; objective: number; meets_target: boolean; seed: number } | null;
}
export interface Comparison {
  samples: number; seed: number; method: string; metrics: string[];
  variants: Dict<{ scales: Dict; valid: number; passed: number; pass_fraction: number | null; pass_interval: [number, number] | null;
    metrics: Dict<{ mean: number; p95: number; max: number }>; constraint_pass_fraction: Dict }>;
}
export interface Sobol {
  method: string; metric: string; base_samples: number; evaluations: number;
  indices: { parameter: string; first_order: number; total_order: number; first_order_interval: [number, number]; total_order_interval: [number, number]; interaction_share: number }[];
}
export interface Oat {
  metric: string; method: string;
  rows: { parameter: string; low: number; high: number; response_low: number; response_high: number; response_nominal: number; swing: number; max_change: number; direction: string }[];
}
export interface CsvPreview { file: string; columns: string[]; rows: string[][]; row_count: number }
export interface Series { name: string; samples: number; time: number[]; signals: Dict<{ measured: number[]; predicted: number[]; residual: number[] }> }
export interface CalibrationResult {
  parameters: { joint: string; name: string; estimate: number; std_error: number | null; lower: number; upper: number; at_bound: boolean }[];
  correlation: number[][] | null; condition_number: number; warnings: string[]; assessment: string; statement: string;
  solver: { method: string; evaluations: number };
  calibration: Series & { errors: Dict<{ rmse: number; mae: number; max_abs: number; samples: number }> };
  holdout: Series & { errors: Dict<{ rmse: number; mae: number; max_abs: number; samples: number }>; split: string; rmse_ratio: Dict };
}
export interface Health {
  status: string; versions: Dict<string>; workspace: string; active_jobs: number;
  ai: { available: boolean; reason?: string; model?: string; provider?: string; cloud?: boolean;
        host?: string; daily_limit?: number; used_today?: number };
}
export interface Report {
  synthetic_notice: string | null; assumptions: string[]; limitations: string[]; versions: Dict<string>;
  failure_count: number; reproduce: string; summary: Summary;
}
