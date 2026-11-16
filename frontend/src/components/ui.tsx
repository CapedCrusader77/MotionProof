import { Component, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";
import type { Async } from "../hooks/useAsync";

export function Panel(props: { title?: ReactNode; actions?: ReactNode; foot?: ReactNode; flush?: boolean;
  children: ReactNode; className?: string; style?: React.CSSProperties }) {
  return (
    <section className={`panel ${props.className ?? ""}`} style={props.style}>
      {(props.title || props.actions) && (
        <header className="panel-head">
          <h2>{props.title}</h2>
          <span className="spacer" />
          {props.actions}
        </header>
      )}
      <div className={`panel-body ${props.flush ? "flush" : ""}`}>{props.children}</div>
      {props.foot && <footer className="panel-foot">{props.foot}</footer>}
    </section>
  );
}

export function Field(props: { label: string; hint?: string; wide?: boolean; children: ReactNode }) {
  return (
    <label className={`field ${props.wide ? "wide" : ""}`}>
      <span>{props.label}</span>
      {props.children}
      {props.hint && <span className="hint">{props.hint}</span>}
    </label>
  );
}

/** Numeric input that reports only finite numbers and marks invalid text. */
export function Num(props: { value: number; onChange: (v: number) => void; step?: number; min?: number;
  max?: number; disabled?: boolean; ariaLabel?: string }) {
  const bad = !Number.isFinite(props.value) || (props.min !== undefined && props.value < props.min)
    || (props.max !== undefined && props.value > props.max);
  return (
    <input className={`input num ${bad ? "invalid" : ""}`} type="number" step={props.step ?? "any"}
      value={Number.isFinite(props.value) ? props.value : ""} disabled={props.disabled}
      aria-label={props.ariaLabel} aria-invalid={bad}
      onChange={(e) => props.onChange(e.target.value === "" ? NaN : Number(e.target.value))} />
  );
}

export function Badge(props: { kind?: "ok" | "warn" | "bad" | "info" | "plain"; children: ReactNode; title?: string }) {
  return <span className={`badge ${props.kind ?? "plain"}`} title={props.title}>{props.children}</span>;
}

export function Alert(props: { kind: "ok" | "warn" | "bad" | "info"; children: ReactNode }) {
  const Icon = { ok: CheckCircle2, warn: AlertTriangle, bad: XCircle, info: Info }[props.kind];
  return <div className={`alert ${props.kind}`} role={props.kind === "bad" ? "alert" : "status"}><Icon /><div>{props.children}</div></div>;
}

export function Empty(props: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty">
      <b>{props.title}</b>
      {props.children && <div>{props.children}</div>}
      {props.action}
    </div>
  );
}

export const Spinner = ({ label }: { label?: string }) => (
  <span className="row center" style={{ gap: 7 }} role="status"><span className="spinner" />{label && <span className="muted">{label}</span>}</span>
);

/** Renders loading / error / empty states for an async resource, then the content. */
export function Load<T>(props: { state: Async<T>; children: (data: T) => ReactNode; label?: string }) {
  const { state } = props;
  if (state.error) {
    return (
      <Alert kind="bad">
        {state.error} <button className="btn small" onClick={state.reload} style={{ marginLeft: 8 }}>Retry</button>
      </Alert>
    );
  }
  if (state.data === null) return <div className="empty"><Spinner label={props.label ?? "Loading"} /></div>;
  return <>{props.children(state.data)}</>;
}

export function Tabs<K extends string>(props: { tabs: [K, string][]; value: K; onChange: (k: K) => void }) {
  return (
    <div className="tabs" role="tablist">
      {props.tabs.map(([k, label]) => (
        <button key={k} role="tab" aria-selected={k === props.value} className={`tab ${k === props.value ? "active" : ""}`}
          onClick={() => props.onChange(k)}>{label}</button>
      ))}
    </div>
  );
}

export function Stat(props: { label: string; value: ReactNode; sub?: ReactNode; tone?: "pos" | "neg" }) {
  return (
    <div className="stat">
      <span className={`v ${props.tone ?? ""}`}>{props.value}</span>
      <span className="l">{props.label}</span>
      {props.sub && <span className="s">{props.sub}</span>}
    </div>
  );
}

export function Modal(props: { title: string; onClose: () => void; children: ReactNode; foot?: ReactNode }) {
  return (
    <div className="modal-back" onMouseDown={(e) => { if (e.target === e.currentTarget) props.onClose(); }}
      onKeyDown={(e) => { if (e.key === "Escape") props.onClose(); }}>
      <div className="panel modal" role="dialog" aria-modal="true" aria-label={props.title}>
        <header className="panel-head"><h2>{props.title}</h2><span className="spacer" />
          <button className="btn ghost small" onClick={props.onClose} aria-label="Close">Close</button></header>
        <div className="panel-body">{props.children}</div>
        {props.foot && <footer className="panel-foot row center" style={{ justifyContent: "flex-end" }}>{props.foot}</footer>}
      </div>
    </div>
  );
}

export function NeedSelection(props: { what: string; action?: ReactNode }) {
  return <div className="page"><div className="panel" style={{ flex: 1 }}><Empty title={`No ${props.what} selected`} action={props.action}>
    Select or create one to use this workspace.</Empty></div></div>;
}

export class ErrorBoundary extends Component<{ children: ReactNode; name: string }, { error: string | null }> {
  state = { error: null as string | null };
  static getDerivedStateFromError(e: Error) { return { error: e.message }; }
  componentDidUpdate(prev: { name: string }) {
    if (prev.name !== this.props.name && this.state.error) this.setState({ error: null });
  }
  render() {
    if (this.state.error) {
      return <div className="page"><Alert kind="bad">This screen failed to render: {this.state.error}
        <button className="btn small" style={{ marginLeft: 8 }} onClick={() => this.setState({ error: null })}>Try again</button></Alert></div>;
    }
    return this.props.children;
  }
}

// ---- formatting ------------------------------------------------------------------------

export const fmt = (v: number | null | undefined, digits = 4): string => {
  if (v === null || v === undefined || !Number.isFinite(v)) return "–";
  if (v === 0) return "0";
  const a = Math.abs(v);
  return a >= 1e5 || a < 1e-4 ? v.toExponential(2) : Number(v.toPrecision(digits)).toString();
};
export const pct = (v: number | null | undefined, digits = 1) =>
  v === null || v === undefined || !Number.isFinite(v) ? "–" : `${(100 * v).toFixed(digits)}%`;
export const signed = (v: number, digits = 4) => (v > 0 ? "+" : "") + fmt(v, digits);

const UNITS: Record<string, [number, string]> = {
  ee_error: [1e3, "mm"], direction_error_ee: [1e3, "mm"], repeatability: [1e3, "mm"], radial_play: [1e6, "µm"],
  angle_error: [1e3, "mrad"], lost_motion: [1e3, "mrad"], backlash: [1e3, "mrad"], tracking_error: [1e3, "mrad"],
  transmission_deflection: [1e3, "mrad"], torque_utilisation: [100, "%"], torque_rms: [100, "%"],
  motor_speed_ratio: [100, "%"], saturated_fraction: [100, "%"], min_mesh_backlash_mm: [1e3, "µm"],
  min_fit_clearance: [1e3, "µm"], max_fit_interference: [1e3, "µm"], output_velocity: [1, "rad/s"],
  output_acceleration: [1, "rad/s²"], task_duration: [1, "s"], settling_speed: [1e3, "mrad/s"],
};
/** Display scaling for a metric key: [multiplier, unit]. The API always carries SI values. */
export function metricUnit(key: string): [number, string] {
  for (const [prefix, u] of Object.entries(UNITS)) if (key.startsWith(prefix)) return u;
  return [1, ""];
}
export function metricFmt(key: string, v: number | null | undefined): string {
  const [k, u] = metricUnit(key);
  return v === null || v === undefined ? "–" : `${fmt(v * k)}${u ? " " + u : ""}`;
}
export const metricLabel = (key: string) => key.replace(/_/g, " ");
