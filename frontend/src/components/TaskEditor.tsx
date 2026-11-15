import type { Task } from "../lib/types";
import { Field, Num } from "./ui";

export const TASK_LABEL: Record<Task["type"], string> = {
  point_to_point: "Point-to-point move", reversal: "Joint reversal (lost motion)", static_hold: "Static payload hold",
  repeat_cycles: "Repeated cycles (repeatability)", workspace_sweep: "Workspace sweep",
};
export const TASK_METRICS: Record<Task["type"], string[]> = {
  point_to_point: ["ee_error_final", "angle_error_final", "tracking_error_max", "torque_utilisation_peak"],
  reversal: ["direction_error_ee", "lost_motion", "ee_error_max", "torque_utilisation_peak"],
  static_hold: ["ee_error_final", "angle_error_final", "torque_utilisation_peak", "torque_rms_ratio"],
  repeat_cycles: ["repeatability", "ee_error_max", "torque_rms_ratio"],
  workspace_sweep: ["ee_error_max", "ee_error_rms", "torque_utilisation_peak"],
};

export function defaultTask(type: Task["type"], joint: string): Task {
  switch (type) {
    case "point_to_point": return { type, start: { [joint]: 0 }, target: { [joint]: 1.0 }, duration: 1.0, settle: 0.4, payload_mass: 0.2 };
    case "reversal": return { type, target: { [joint]: 1.5708 }, joint, excursion: 0.2, move_time: 0.6, settle: 0.4, payload_mass: 0.2 };
    case "static_hold": return { type, pose: { [joint]: 0 }, duration: 0.6, payload_mass: 0.2 };
    case "repeat_cycles": return { type, a: { [joint]: 0 }, b: { [joint]: 1.0 }, cycles: 3, move_time: 0.8, settle: 0.3, payload_mass: 0.2 };
    case "workspace_sweep": return { type, poses: [{ [joint]: -0.8 }, { [joint]: 0 }, { [joint]: 0.8 }, { [joint]: 1.5708 }], move_time: 0.8, settle: 0.3, payload_mass: 0.2 };
  }
}

const deg = (rad: number) => Number(((rad * 180) / Math.PI).toFixed(4));
const rad = (d: number) => (d * Math.PI) / 180;

export function TaskEditor({ task, joints, onChange }: { task: Task; joints: string[]; onChange: (t: Task) => void }) {
  const joint = joints[0] ?? "";
  const angle = (label: string, value: number, set: (v: number) => void) => (
    <Field label={`${label} (deg)`} key={label}><Num value={deg(value)} onChange={(v) => set(rad(v))} /></Field>);
  const time = (label: string, value: number | undefined, key: string) => (
    <Field label={`${label} (s)`} key={key}><Num value={value ?? NaN} min={0.05} onChange={(v) => onChange({ ...task, [key]: v } as Task)} /></Field>);
  return (
    <div className="form">
      <Field label="Task" wide>
        <select value={task.type} onChange={(e) => onChange(defaultTask(e.target.value as Task["type"], joint))}>
          {(Object.keys(TASK_LABEL) as Task["type"][]).map((t) => <option key={t} value={t}>{TASK_LABEL[t]}</option>)}
        </select></Field>
      {task.type === "point_to_point" && <>
        {angle(`${joint} start`, task.start[joint] ?? 0, (v) => onChange({ ...task, start: { ...task.start, [joint]: v } }))}
        {angle(`${joint} target`, task.target[joint] ?? 0, (v) => onChange({ ...task, target: { ...task.target, [joint]: v } }))}
        {time("Move duration", task.duration, "duration")}{time("Settle time", task.settle, "settle")}</>}
      {task.type === "reversal" && <>
        <Field label="Joint"><select value={task.joint} onChange={(e) => onChange({ ...task, joint: e.target.value })}>{joints.map((j) => <option key={j}>{j}</option>)}</select></Field>
        {angle("Target", task.target[task.joint] ?? 0, (v) => onChange({ ...task, target: { ...task.target, [task.joint]: v } }))}
        {angle("Excursion", task.excursion ?? 0.2, (v) => onChange({ ...task, excursion: v }))}
        {time("Move time", task.move_time, "move_time")}{time("Settle time", task.settle, "settle")}</>}
      {task.type === "static_hold" && <>
        {angle(`${joint} pose`, task.pose[joint] ?? 0, (v) => onChange({ ...task, pose: { ...task.pose, [joint]: v } }))}
        {time("Hold duration", task.duration, "duration")}</>}
      {task.type === "repeat_cycles" && <>
        {angle(`${joint} A`, task.a[joint] ?? 0, (v) => onChange({ ...task, a: { ...task.a, [joint]: v } }))}
        {angle(`${joint} B`, task.b[joint] ?? 0, (v) => onChange({ ...task, b: { ...task.b, [joint]: v } }))}
        <Field label="Cycles"><Num value={task.cycles ?? 3} min={1} max={50} step={1} onChange={(v) => onChange({ ...task, cycles: v })} /></Field>
        {time("Move time", task.move_time, "move_time")}</>}
      {task.type === "workspace_sweep" && <>
        <Field label={`${joint} poses (deg, comma-separated)`} wide>
          <input className="input mono" defaultValue={task.poses.map((p) => deg(p[joint] ?? 0)).join(", ")}
            onBlur={(e) => { const vals = e.target.value.split(/[,\s]+/).filter(Boolean).map(Number).filter(Number.isFinite);
              if (vals.length >= 2) onChange({ ...task, poses: vals.map((v) => ({ [joint]: rad(v) })) }); }} /></Field>
        {time("Move time", task.move_time, "move_time")}{time("Settle time", task.settle, "settle")}</>}
      <Field label="Payload at the end effector (kg)"><Num value={task.payload_mass ?? 0} min={0} onChange={(v) => onChange({ ...task, payload_mass: v } as Task)} /></Field>
    </div>
  );
}
