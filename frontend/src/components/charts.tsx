import {
  Bar, BarChart, CartesianGrid, Cell, ErrorBar, Line, LineChart, ReferenceLine, ResponsiveContainer,
  Scatter, ScatterChart, Tooltip, XAxis, YAxis,
} from "recharts";
import type { Hist } from "../lib/types";
import { fmt } from "./ui";

const C = { main: "var(--data)", ok: "var(--ok)", bad: "var(--bad)", alt: "var(--data-2)", muted: "var(--faint)" };
const tip = {
  contentStyle: { background: "var(--surface)", border: "1px solid var(--border-strong)", borderRadius: 4, fontSize: 12, color: "var(--text)" },
  formatter: (v: unknown) => (typeof v === "number" ? fmt(v) : String(v)),
};
const tick = (v: number) => fmt(v, 3);

export function Histogram(props: { hist: Hist; scale?: number; unit?: string; limit?: number; height?: number;
  failAbove?: boolean; failBelow?: boolean }) {
  const k = props.scale ?? 1;
  const data = props.hist.x.map((x, i) => ({ x: x * k, count: props.hist.count[i] }));
  const lim = props.limit === undefined ? undefined : props.limit * k;
  const failing = (x: number) => lim !== undefined && ((props.failAbove && x > lim) || (props.failBelow && x < lim));
  return (
    <ResponsiveContainer width="100%" height={props.height ?? 170}>
      <BarChart data={data} margin={{ top: 6, right: 10, bottom: 14, left: 0 }} barCategoryGap={0}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="x" type="number" domain={["dataMin", "dataMax"]} tickFormatter={tick}
          label={{ value: props.unit ?? "", position: "insideBottom", offset: -8 }} />
        <YAxis width={34} allowDecimals={false} />
        <Tooltip {...tip} labelFormatter={(v) => `${fmt(Number(v))} ${props.unit ?? ""}`} />
        <Bar dataKey="count" isAnimationActive={false}>
          {data.map((d) => <Cell key={d.x} fill={failing(d.x) ? C.bad : C.main} />)}
        </Bar>
        {lim !== undefined && <ReferenceLine x={lim} stroke={C.bad} strokeDasharray="4 3" label={{ value: "limit", fill: "var(--bad)", fontSize: 11, position: "top" }} />}
      </BarChart>
    </ResponsiveContainer>
  );
}

export interface SeriesDef { key: string; name: string; color?: string; dashed?: boolean }
export function Lines(props: { data: Record<string, number>[]; x: string; series: SeriesDef[]; height?: number;
  xLabel?: string; yLabel?: string }) {
  const palette = [C.main, C.bad, C.ok, C.alt, C.muted];
  return (
    <ResponsiveContainer width="100%" height={props.height ?? 190}>
      <LineChart data={props.data} margin={{ top: 6, right: 12, bottom: 14, left: 4 }}>
        <CartesianGrid />
        <XAxis dataKey={props.x} type="number" domain={["dataMin", "dataMax"]} tickFormatter={tick}
          label={{ value: props.xLabel ?? "", position: "insideBottom", offset: -8 }} />
        <YAxis width={52} tickFormatter={tick} domain={["auto", "auto"]}
          label={props.yLabel ? { value: props.yLabel, angle: -90, position: "insideLeft", offset: 8 } : undefined} />
        <Tooltip {...tip} labelFormatter={(v) => `${props.xLabel ?? props.x} ${fmt(Number(v))}`} />
        {props.series.map((s, i) => (
          <Line key={s.key} dataKey={s.key} name={s.name} dot={false} isAnimationActive={false} strokeWidth={1.6}
            stroke={s.color ?? palette[i % palette.length]} strokeDasharray={s.dashed ? "5 3" : undefined} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

export function HBars(props: { rows: { name: string; value: number; lo?: number; hi?: number }[]; height?: number;
  domain?: [number, number]; label?: string }) {
  const data = props.rows.map((r) => ({ ...r, err: r.lo !== undefined && r.hi !== undefined ? [r.value - r.lo, r.hi - r.value] : undefined }));
  return (
    <ResponsiveContainer width="100%" height={props.height ?? Math.max(120, 22 * data.length + 40)}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 14, bottom: 14, left: 4 }}>
        <CartesianGrid horizontal={false} />
        <XAxis type="number" domain={props.domain ?? ["auto", "auto"]} tickFormatter={tick}
          label={{ value: props.label ?? "", position: "insideBottom", offset: -8 }} />
        <YAxis type="category" dataKey="name" width={190} tick={{ fontSize: 11 }} interval={0} />
        <Tooltip {...tip} />
        <ReferenceLine x={0} stroke="var(--border-strong)" />
        <Bar dataKey="value" isAnimationActive={false}>
          {data.map((d) => <Cell key={d.name} fill={d.value >= 0 ? C.main : C.alt} />)}
          {data.some((d) => d.err) && <ErrorBar dataKey="err" width={3} stroke="var(--text)" direction="x" />}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function Points(props: { points: { x: number; y: number; ok?: boolean; label?: string; mark?: boolean }[];
  xLabel: string; yLabel: string; height?: number; yLimit?: number; onPick?: (label: string) => void }) {
  const groups: [string, string, typeof props.points][] = [
    ["pass", C.main, props.points.filter((p) => p.ok !== false && !p.mark)],
    ["fail", C.bad, props.points.filter((p) => p.ok === false && !p.mark)],
    ["marked", C.ok, props.points.filter((p) => p.mark)],
  ];
  return (
    <ResponsiveContainer width="100%" height={props.height ?? 200}>
      <ScatterChart margin={{ top: 6, right: 12, bottom: 16, left: 4 }}>
        <CartesianGrid />
        <XAxis dataKey="x" type="number" domain={["auto", "auto"]} tickFormatter={tick} name={props.xLabel}
          label={{ value: props.xLabel, position: "insideBottom", offset: -9 }} />
        <YAxis dataKey="y" type="number" domain={["auto", "auto"]} tickFormatter={tick} width={52} name={props.yLabel}
          label={{ value: props.yLabel, angle: -90, position: "insideLeft", offset: 8 }} />
        <Tooltip {...tip} cursor={{ strokeDasharray: "3 3" }} />
        {props.yLimit !== undefined && <ReferenceLine y={props.yLimit} stroke={C.bad} strokeDasharray="4 3" />}
        {groups.map(([name, color, pts]) => pts.length > 0 && (
          <Scatter key={name} name={name} data={pts} fill={color} isAnimationActive={false}
            shape={name === "marked" ? "diamond" : "circle"}
            onClick={(p) => { const label = (p as unknown as { payload?: { label?: string } }).payload?.label ?? (p as unknown as { label?: string }).label;
              if (label && props.onPick) props.onPick(label); }} />
        ))}
      </ScatterChart>
    </ResponsiveContainer>
  );
}

/** Convert trace arrays into recharts rows, applying a display multiplier per series. */
export function traceRows(trace: Record<string, number[]>, keys: Record<string, number>): Record<string, number>[] {
  const t = trace.t ?? [];
  return t.map((time, i) => {
    const row: Record<string, number> = { t: time };
    for (const [k, mult] of Object.entries(keys)) row[k] = (trace[k]?.[i] ?? NaN) * mult;
    return row;
  });
}
