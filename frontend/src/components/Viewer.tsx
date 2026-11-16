// 3D engineering viewer. Renders the real component meshes served by the backend
// (millimetres, body frame), posed by backend kinematics. Z is up.
import { Suspense, useEffect, useMemo, useState, type KeyboardEvent, type ReactNode } from "react";
import { Canvas, useLoader, useThree } from "@react-three/fiber";
import { Bounds, GizmoHelper, GizmoViewport, Grid, Line, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { Axis3d, Eye, Layers, Maximize2, Scissors } from "lucide-react";
import { useApp } from "../stores/app";
import { api } from "../lib/api";
import type { Component, GeometryRef, Pose } from "../lib/types";

// Neutral engineering materials: components are told apart by value and hue family, not by
// saturated colour. Selection uses the application accent.
const GROUP_COLOR: Record<string, string> = {
  housing: "#b3b6b1", motor: "#55595a", bearing: "#bba46a", gear: "#96a4b0", shaft: "#cfd2cf",
  link: "#a3aea6", imported: "#a8b0b4", body: "#a8b0b4",
};
const SELECTED = "#c8402b";
export type Shading = "shaded" | "edges" | "wire";
const MM = 0.001;

export interface Marker { component: string; geometry: GeometryRef; color?: string }
export interface Overlay { pose: Pose; magnify: number; changed: Set<string> }
export interface ViewerProps {
  modelId: string;
  stamp: string;
  components: Component[];
  pose: Pose | null;
  selected?: string | null;
  onSelect?: (id: string | null) => void;
  hidden?: Set<string>;
  isolate?: string | null;
  markers?: Marker[];
  overlay?: Overlay | null;
  tint?: Record<string, string>;
  height?: number | string;
  legend?: string;
  /** Content of the status bar along the bottom edge of the viewport. */
  status?: ReactNode;
}

function centreOf(c: Component): THREE.Vector3 {
  const bb = c.bbox_mm ?? c.bbox;
  if (bb && bb.length === 2) {
    return new THREE.Vector3((bb[0][0] + bb[1][0]) / 2, (bb[0][1] + bb[1][1]) / 2, (bb[0][2] + bb[1][2]) / 2).multiplyScalar(MM);
  }
  return new THREE.Vector3();
}

function bodyMatrix(pose: Pose | null, body: string): THREE.Matrix4 {
  const b = pose?.bodies[body];
  const m = new THREE.Matrix4();
  if (!b) return m;
  const q = new THREE.Quaternion(b.quat[1], b.quat[2], b.quat[3], b.quat[0]);
  return m.compose(new THREE.Vector3(b.pos[0], b.pos[1], b.pos[2]), q, new THREE.Vector3(1, 1, 1));
}

/** Variant body pose with the deviation from nominal magnified for visibility. */
function magnified(nominal: Pose | null, variant: Pose, body: string, k: number): THREE.Matrix4 {
  const n = nominal?.bodies[body];
  const v = variant.bodies[body];
  if (!n || !v) return bodyMatrix(variant, body);
  const pn = new THREE.Vector3(...(n.pos as [number, number, number]));
  const pv = new THREE.Vector3(...(v.pos as [number, number, number]));
  const qn = new THREE.Quaternion(n.quat[1], n.quat[2], n.quat[3], n.quat[0]);
  const qv = new THREE.Quaternion(v.quat[1], v.quat[2], v.quat[3], v.quat[0]);
  const delta = qv.clone().multiply(qn.clone().invert());
  const angle = 2 * Math.acos(Math.min(1, Math.abs(delta.w)));
  const q = qn.clone();
  if (angle > 1e-12) {
    const axis = new THREE.Vector3(delta.x, delta.y, delta.z).normalize().multiplyScalar(Math.sign(delta.w) || 1);
    q.premultiply(new THREE.Quaternion().setFromAxisAngle(axis, angle * k));
  }
  const p = pn.clone().add(pv.sub(pn).multiplyScalar(k));
  return new THREE.Matrix4().compose(p, q, new THREE.Vector3(1, 1, 1));
}

function Part(props: { url: string; matrix: THREE.Matrix4; offset: THREE.Vector3; color: string; opacity: number;
  selected: boolean; clip: THREE.Plane[]; onClick?: () => void; wire?: boolean; shading?: Shading; edgeColor?: string }) {
  const geometry = useLoader(STLLoader, props.url);
  useMemo(() => { geometry.computeVertexNormals(); }, [geometry]);
  const edges = useMemo(() => (props.shading === "edges" || (props.selected && props.shading !== "wire")
    ? new THREE.EdgesGeometry(geometry, 28) : null), [geometry, props.shading, props.selected]);
  const wire = props.wire || props.shading === "wire";
  return (
    <group position={props.offset}>
      <group matrix={props.matrix} matrixAutoUpdate={false}>
        <mesh geometry={geometry} scale={MM}
          onClick={props.onClick ? (e) => { e.stopPropagation(); props.onClick?.(); } : undefined}>
          <meshStandardMaterial color={wire && props.selected ? SELECTED : props.color} metalness={0.15} roughness={0.55}
            emissive={props.selected ? SELECTED : "#000000"} emissiveIntensity={props.selected ? 0.22 : 0}
            transparent={props.opacity < 1} opacity={props.opacity} depthWrite={props.opacity >= 1}
            wireframe={wire} clippingPlanes={props.clip} side={THREE.DoubleSide}
            polygonOffset={!!edges} polygonOffsetFactor={1} polygonOffsetUnits={1} />
        </mesh>
        {edges && (
          <lineSegments geometry={edges} scale={MM}>
            <lineBasicMaterial color={props.selected ? SELECTED : props.edgeColor ?? "#2b2f2d"} clippingPlanes={props.clip}
              transparent={props.opacity < 1} opacity={Math.max(props.opacity, 0.35)} />
          </lineSegments>)}
      </group>
    </group>
  );
}

function FeatureMarker({ marker, matrix }: { marker: Marker; matrix: THREE.Matrix4 }) {
  const g = marker.geometry;
  const color = marker.color ?? "#d9462f";
  if (!g.point) return null;
  const p = new THREE.Vector3(g.point[0], g.point[1], g.point[2]).multiplyScalar(MM);
  const d = g.direction ? new THREE.Vector3(g.direction[0], g.direction[1], g.direction[2]).normalize() : new THREE.Vector3(0, 0, 1);
  const quat = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), d);
  if (g.kind === "cylinder" && g.radius && g.length) {
    const len = g.length * MM;
    return (
      <group matrix={matrix} matrixAutoUpdate={false}>
        <mesh position={p.clone().addScaledVector(d, len / 2)} quaternion={quat}>
          <cylinderGeometry args={[g.radius * MM * 1.03, g.radius * MM * 1.03, len, 40, 1, true]} />
          <meshBasicMaterial color={color} transparent opacity={0.55} side={THREE.DoubleSide} depthTest={false} />
        </mesh>
      </group>
    );
  }
  if (g.kind === "plane") {
    return (
      <group matrix={matrix} matrixAutoUpdate={false}>
        <mesh position={p} quaternion={new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 0, 1), d)}>
          <planeGeometry args={[0.05, 0.05]} />
          <meshBasicMaterial color={color} transparent opacity={0.4} side={THREE.DoubleSide} depthTest={false} />
        </mesh>
      </group>
    );
  }
  const a = p.clone().addScaledVector(d, -0.04);
  const b = p.clone().addScaledVector(d, 0.07);
  return (
    <group matrix={matrix} matrixAutoUpdate={false}>
      <Line points={[a, b]} color={color} lineWidth={2} dashed dashSize={0.006} gapSize={0.004} depthTest={false} />
    </group>
  );
}

function Clipping({ enabled }: { enabled: boolean }) {
  const gl = useThree((s) => s.gl);
  useEffect(() => { gl.localClippingEnabled = enabled; }, [gl, enabled]);
  return null;
}

export function Viewer(props: ViewerProps) {
  const [explode, setExplode] = useState(0);
  const [axes, setAxes] = useState(true);
  const [xray, setXray] = useState(true);
  const [section, setSection] = useState(false);
  const [fitKey, setFitKey] = useState(0);
  const [shading, setShading] = useState<Shading>("edges");
  const dark = useApp((st) => st.theme) === "dark";
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if ((e.target as HTMLElement).tagName === "INPUT") return;
    const k = e.key.toLowerCase();
    if (k === "f") setFitKey((x) => x + 1);
    else if (k === "1") setShading("shaded");
    else if (k === "2") setShading("edges");
    else if (k === "3") setShading("wire");
    else if (k === "a") setAxes((v) => !v);
    else if (k === "x") setXray((v) => !v);
    else if (k === "s") setSection((v) => !v);
    else if (k === "escape") props.onSelect?.(null);
    else return;
    e.preventDefault();
  };
  const drawable = props.components.filter((c) => c.mesh);
  const centre = useMemo(() => {
    const c = new THREE.Vector3();
    drawable.forEach((d) => c.add(centreOf(d)));
    return drawable.length ? c.divideScalar(drawable.length) : c;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.modelId, drawable.length]);
  // section plane through the gearbox axis (world Y), keeping the +Z half hidden
  const clip = useMemo(() => (section ? [new THREE.Plane(new THREE.Vector3(0, 0, -1), centre.z)] : []), [section, centre]);

  const visible = (c: Component) =>
    !(props.hidden?.has(c.id)) && (!props.isolate || props.isolate === c.id);

  if (drawable.length === 0) {
    return <div className="viewport" style={{ height: props.height ?? "100%" }}><div className="empty">This model has no drawable geometry.</div></div>;
  }
  return (
    <div className="viewport" style={{ height: props.height ?? "100%" }} tabIndex={0} onKeyDown={onKey}
      aria-label="3D viewport. Keys: F fit, 1 shaded, 2 shaded with edges, 3 wireframe, A axes, X x-ray, S section, Esc clear selection">
      <div className="hud" role="toolbar" aria-label="Viewport">
        <button className="btn small" onClick={() => setFitKey((k) => k + 1)} title="Fit view (F)"><Maximize2 />Fit</button>
        <span className="hud-sep" />
        {(["shaded", "edges", "wire"] as Shading[]).map((m, i) => (
          <button key={m} className="btn small" aria-pressed={shading === m} onClick={() => setShading(m)} title={`${m === "edges" ? "Shaded with edges" : m === "wire" ? "Wireframe" : "Shaded"} (${i + 1})`}>
            {m === "shaded" ? "Shaded" : m === "edges" ? "Edges" : "Wire"}</button>))}
        <span className="hud-sep" />
        <button className="btn small" aria-pressed={axes} onClick={() => setAxes(!axes)} title="Joint axes and world frame (A)"><Axis3d />Axes</button>
        <button className="btn small" aria-pressed={xray} onClick={() => setXray(!xray)} title="Translucent housing (X)"><Eye />X-ray</button>
        <button className="btn small" aria-pressed={section} onClick={() => setSection(!section)} title="Section through the assembly centre (S)"><Scissors />Section</button>
        <label className="btn small" title="Exploded view"><Layers />
          <input type="range" min={0} max={2} step={0.05} value={explode} aria-label="Explode"
            onChange={(e) => setExplode(Number(e.target.value))} style={{ width: 70 }} /></label>
      </div>
      {(props.status || props.legend) && <div className="statusbar">{props.status ?? props.legend}</div>}
      <div className="canvas-wrap">
      <Canvas camera={{ position: [0.35, -0.45, 0.3], up: [0, 0, 1], fov: 38, near: 0.001, far: 50 }}
        onPointerMissed={() => props.onSelect?.(null)} dpr={[1, 2]}>
        <Clipping enabled={section} />
        <hemisphereLight args={["#ffffff", "#b8bab4", 0.95]} />
        <directionalLight position={[2, -3, 4]} intensity={1.15} />
        <directionalLight position={[-3, 2, 1]} intensity={0.35} />
        <Suspense fallback={null}>
          <Bounds key={`${props.modelId}-${fitKey}-${drawable.length}-${props.pose ? "posed" : "rest"}-${props.isolate ?? "all"}`} fit clip observe margin={1.1}>
            <group>
              {drawable.filter(visible).map((c) => {
                const offset = centreOf(c).sub(centre).multiplyScalar(explode);
                const base = props.tint?.[c.id] ?? GROUP_COLOR[c.group] ?? "#8fa3bd";
                const translucent = xray && c.group === "housing" && props.selected !== c.id;
                return (
                  <Part key={c.id} url={api.meshUrl(props.modelId, c.id, props.stamp)} matrix={bodyMatrix(props.pose, c.body)}
                    offset={offset} color={base} opacity={translucent ? 0.22 : props.overlay ? 0.55 : 1}
                    selected={props.selected === c.id} clip={clip} shading={shading} edgeColor={dark ? "#141716" : "#2b2f2d"}
                    onClick={props.onSelect ? () => props.onSelect?.(c.id) : undefined} />
                );
              })}
              {props.overlay && drawable.filter(visible).filter((c) => props.overlay?.pose.bodies[c.body]).map((c) => (
                <Part key={`ov-${c.id}`} url={api.meshUrl(props.modelId, c.id, props.stamp)}
                  matrix={magnified(props.pose, props.overlay!.pose, c.body, props.overlay!.magnify)}
                  offset={centreOf(c).sub(centre).multiplyScalar(explode)}
                  color={props.overlay!.changed.has(c.id) ? "#d9462f" : "#c9773a"} opacity={0.5} selected={false} clip={clip} wire />
              ))}
            </group>
          </Bounds>
          {(props.markers ?? []).map((m, i) => {
            const comp = props.components.find((c) => c.id === m.component);
            return <FeatureMarker key={i} marker={m} matrix={bodyMatrix(props.pose, comp?.body ?? "world")} />;
          })}
        </Suspense>
        {axes && (props.pose?.joints ?? []).map((j) => {
          const a = new THREE.Vector3(...(j.anchor as [number, number, number]));
          const d = new THREE.Vector3(...(j.axis as [number, number, number])).multiplyScalar(0.07);
          return <Line key={j.name} points={[a.clone().sub(d), a.clone().add(d)]} color={j.driven ? "#d9462f" : "#3a7bd5"} lineWidth={2.5} depthTest={false} />;
        })}
        {axes && <axesHelper args={[0.05]} />}
        <Grid args={[2, 2]} rotation={[Math.PI / 2, 0, 0]} position={[0, 0, -0.08]} cellSize={0.01} sectionSize={0.05}
          cellColor={dark ? "#262a28" : "#d2d4ce"} sectionColor={dark ? "#3a3f3c" : "#b2b5ae"} fadeDistance={1.6} infiniteGrid />
        <OrbitControls makeDefault enableDamping dampingFactor={0.15} />
        <GizmoHelper alignment="bottom-right" margin={[52, 52]}>
          <GizmoViewport axisColors={["#b8473a", "#4b8a5c", "#3f6f9e"]} labelColor="#fff" />
        </GizmoHelper>
      </Canvas>
      </div>
    </div>
  );
}
