// Scan and comparison viewers. Meshes and points are in millimetres; scene units are metres.
// Several viewers can share one camera through a CameraLink.
import { Suspense, useEffect, useMemo, useRef } from "react";
import { Canvas, useFrame, useLoader, useThree } from "@react-three/fiber";
import { Bounds, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import type { OrbitControls as OrbitImpl } from "three-stdlib";

const MM = 0.001;

/** Shared camera state for linked viewers. */
export class CameraLink {
  position = new THREE.Vector3();
  target = new THREE.Vector3();
  owner: string | null = null;
  version = 0;
  publish(owner: string, cam: THREE.Camera, target: THREE.Vector3) {
    this.position.copy(cam.position);
    this.target.copy(target);
    this.owner = owner;
    this.version += 1;
  }
}

function Linked({ link, id }: { link?: CameraLink; id: string }) {
  const controls = useThree((s) => s.controls) as unknown as OrbitImpl | null;
  const camera = useThree((s) => s.camera);
  const seen = useRef(0);
  useEffect(() => {
    if (!link || !controls) return;
    const onChange = () => link.publish(id, camera, controls.target);
    controls.addEventListener("change", onChange);
    return () => controls.removeEventListener("change", onChange);
  }, [link, controls, camera, id]);
  useFrame(() => {
    if (!link || !controls || link.version === seen.current) return;
    seen.current = link.version;
    if (link.owner === id) return;
    camera.position.copy(link.position);
    controls.target.copy(link.target);
    controls.update();
  });
  return null;
}

function MeshPart({ url, color, opacity }: { url: string; color: string; opacity: number }) {
  const geometry = useLoader(STLLoader, url);
  useMemo(() => geometry.computeVertexNormals(), [geometry]);
  return (
    <mesh geometry={geometry} scale={MM}>
      <meshStandardMaterial color={color} metalness={0.2} roughness={0.6} transparent={opacity < 1}
        opacity={opacity} depthWrite={opacity >= 1} side={THREE.DoubleSide} />
    </mesh>
  );
}

/** Diverging colour for a signed deviation: blue (inside material) - grey - red (outside). */
export function deviationColor(v: number, limit: number): THREE.Color {
  const t = Math.max(-1, Math.min(1, v / (limit || 1e-9)));
  const c = new THREE.Color();
  if (t >= 0) c.setRGB(0.75 + 0.2 * t, 0.75 - 0.55 * t, 0.75 - 0.6 * t);
  else c.setRGB(0.75 + 0.55 * t, 0.75 + 0.3 * t, 0.75 - 0.2 * t);
  return c;
}

function Cloud({ points, values, limit, missing }: { points: number[][]; values?: number[];
  limit: number; missing?: number[][] }) {
  const geom = useMemo(() => {
    const g = new THREE.BufferGeometry();
    const pos = new Float32Array(points.length * 3);
    const col = new Float32Array(points.length * 3);
    points.forEach((p, i) => {
      pos.set([p[0] * MM, p[1] * MM, p[2] * MM], i * 3);
      const c = values ? deviationColor(values[i], limit) : new THREE.Color("#3a7bd5");
      col.set([c.r, c.g, c.b], i * 3);
    });
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    g.setAttribute("color", new THREE.BufferAttribute(col, 3));
    return g;
  }, [points, values, limit]);
  const miss = useMemo(() => {
    if (!missing?.length) return null;
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(
      new Float32Array(missing.flatMap((p) => [p[0] * MM, p[1] * MM, p[2] * MM])), 3));
    return g;
  }, [missing]);
  return (<>
    <points geometry={geom}><pointsMaterial size={2.2} sizeAttenuation={false} vertexColors /></points>
    {miss && <points geometry={miss}><pointsMaterial size={3} sizeAttenuation={false} color="#c58a00" /></points>}
  </>);
}

export interface ScanViewProps {
  id: string;
  meshUrl?: string | null;
  meshOpacity?: number;
  meshColor?: string;
  points?: number[][];
  values?: number[];
  limit?: number;
  missing?: number[][];
  link?: CameraLink;
  height?: number | string;
  caption?: string;
  empty?: string;
}

export function ScanView(p: ScanViewProps) {
  const nothing = !p.meshUrl && !p.points?.length;
  return (
    <div className="viewport" style={{ height: p.height ?? 360 }}>
      {p.caption && <div className="legend" style={{ top: 8, bottom: "auto" }}>{p.caption}</div>}
      {nothing ? <div className="empty">{p.empty ?? "Nothing to display."}</div> : (
        <div className="canvas-wrap">
          <Canvas camera={{ position: [0.08, -0.12, 0.08], up: [0, 0, 1], fov: 35, near: 0.0005, far: 20 }} dpr={[1, 2]}>
            <ambientLight intensity={0.8} />
            <directionalLight position={[1, -2, 3]} intensity={1.2} />
            <Suspense fallback={null}>
              <Bounds fit clip margin={1.3}>
                <group>
                  {p.meshUrl && <MeshPart url={p.meshUrl} color={p.meshColor ?? "#9aa6b6"} opacity={p.meshOpacity ?? 1} />}
                  {p.points && p.points.length > 0 && <Cloud points={p.points} values={p.values} limit={p.limit ?? 0.05} missing={p.missing} />}
                </group>
              </Bounds>
            </Suspense>
            <axesHelper args={[0.01]} />
            <OrbitControls makeDefault enableDamping={false} />
            <Linked link={p.link} id={p.id} />
          </Canvas>
        </div>)}
    </div>
  );
}

export function DeviationLegend({ limit, unit = "mm" }: { limit: number; unit?: string }) {
  const stops = [-1, -0.5, 0, 0.5, 1];
  return (
    <div className="row center small" style={{ gap: 6 }} aria-label="Deviation colour scale">
      <span className="muted">inside material</span>
      {stops.map((s) => (
        <span key={s} className="row center" style={{ gap: 3 }}>
          <span style={{ width: 14, height: 10, background: `#${deviationColor(s * limit, limit).getHexString()}`, border: "1px solid var(--border)" }} />
          <span className="mono">{s > 0 ? "+" : ""}{(s * limit).toPrecision(2)}</span>
        </span>))}
      <span className="muted">{unit}, outside material</span>
      <span className="row center" style={{ gap: 3 }}><span style={{ width: 14, height: 10, background: "#c58a00" }} /><span className="muted">no scan coverage</span></span>
    </div>
  );
}
