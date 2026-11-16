// 3D engineering viewer. Renders the real component meshes served by the backend
// (millimetres, body frame), posed by backend kinematics. Z is up.
import { Suspense, useEffect, useMemo, useState } from "react";
import { Canvas, useLoader, useThree } from "@react-three/fiber";
import { Bounds, GizmoHelper, GizmoViewport, Grid, Line, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { Axis3d, Eye, Layers, Maximize2, Scissors } from "lucide-react";
import { api } from "../lib/api";
import type { Component, GeometryRef, Pose } from "../lib/types";

const GROUP_COLOR: Record<string, string> = {
  housing: "#8d98a8", motor: "#4b5563", bearing: "#c9a227", gear: "#5f86b8", shaft: "#b9bec7",
  link: "#6fa58c", imported: "#8fa3bd", body: "#8fa3bd",
};
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
  selected: boolean; clip: THREE.Plane[]; onClick?: () => void; wire?: boolean }) {
  const geometry = useLoader(STLLoader, props.url);
  useMemo(() => { geometry.computeVertexNormals(); }, [geometry]);
  return (
    <group position={props.offset}>
      <group matrix={props.matrix} matrixAutoUpdate={false}>
        <mesh geometry={geometry} scale={MM}
          onClick={props.onClick ? (e) => { e.stopPropagation(); props.onClick?.(); } : undefined}>
          <meshStandardMaterial color={props.selected ? "#e0842a" : props.color} metalness={0.25} roughness={0.6}
            transparent={props.opacity < 1} opacity={props.opacity} depthWrite={props.opacity >= 1}
            wireframe={props.wire} clippingPlanes={props.clip} side={THREE.DoubleSide} />
        </mesh>
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
    <div className="viewport" style={{ height: props.height ?? "100%" }}>
      <div className="hud">
        <button className="btn small" onClick={() => setFitKey((k) => k + 1)} title="Fit view"><Maximize2 />Fit</button>
        <button className="btn small" aria-pressed={axes} onClick={() => setAxes(!axes)} title="Joint axes and world frame"><Axis3d />Axes</button>
        <button className="btn small" aria-pressed={xray} onClick={() => setXray(!xray)} title="Translucent housing"><Eye />X-ray</button>
        <button className="btn small" aria-pressed={section} onClick={() => setSection(!section)} title="Section through the assembly centre"><Scissors />Section</button>
        <label className="btn small" title="Exploded view"><Layers />
          <input type="range" min={0} max={2} step={0.05} value={explode} aria-label="Explode"
            onChange={(e) => setExplode(Number(e.target.value))} style={{ width: 70 }} /></label>
      </div>
      {props.legend && <div className="legend">{props.legend}</div>}
      <div className="canvas-wrap">
      <Canvas camera={{ position: [0.35, -0.45, 0.3], up: [0, 0, 1], fov: 38, near: 0.001, far: 50 }}
        onPointerMissed={() => props.onSelect?.(null)} dpr={[1, 2]}>
        <Clipping enabled={section} />
        <ambientLight intensity={0.75} />
        <directionalLight position={[2, -3, 4]} intensity={1.3} />
        <directionalLight position={[-3, 2, 1]} intensity={0.5} />
        <Suspense fallback={null}>
          <Bounds key={`${props.modelId}-${fitKey}-${drawable.length}-${props.pose ? "posed" : "rest"}`} fit clip observe margin={1.25}>
            <group>
              {drawable.filter(visible).map((c) => {
                const offset = centreOf(c).sub(centre).multiplyScalar(explode);
                const base = props.tint?.[c.id] ?? GROUP_COLOR[c.group] ?? "#8fa3bd";
                const translucent = xray && c.group === "housing" && props.selected !== c.id;
                return (
                  <Part key={c.id} url={api.meshUrl(props.modelId, c.id, props.stamp)} matrix={bodyMatrix(props.pose, c.body)}
                    offset={offset} color={base} opacity={translucent ? 0.22 : props.overlay ? 0.55 : 1}
                    selected={props.selected === c.id} clip={clip}
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
          cellColor="#b8c0cc" sectionColor="#8e98a8" fadeDistance={1.6} infiniteGrid />
        <OrbitControls makeDefault enableDamping dampingFactor={0.15} />
        <GizmoHelper alignment="bottom-right" margin={[52, 52]}>
          <GizmoViewport axisColors={["#c0392b", "#2e8b57", "#2c6fbb"]} labelColor="#fff" />
        </GizmoHelper>
      </Canvas>
      </div>
    </div>
  );
}
