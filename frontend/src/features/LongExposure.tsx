// Live version of scripts/make_signin_art.py: points fixed on the three 21-tooth planets of the
// reference gearbox's first stage draw light trails as the 12-tooth sun turns (ring fixed,
// carrier output, exact planetary kinematics). Trails add up like a long exposure and fade
// slowly, so the picture keeps building. Reduced motion shows the rendered still instead.
import { useEffect, useRef, useState } from "react";

const ZS = 12, ZP = 21, ZR = 54;
const RATIO = (ZS + ZR) / ZS;
const RP = ZP / 2, CD = (ZS + ZP) / 2, RR = ZR / 2;
const SPEED = 0.85;          // sun, rad/s
const PER_PLANET = 7;

function colour(t: number): [number, number, number] {
  const stops: [number, [number, number, number]][] = [[0, [92, 140, 217]], [0.55, [242, 230, 209]], [1, [255, 148, 51]]];
  for (let i = 1; i < stops.length; i++) {
    const [b, cb] = stops[i], [a, ca] = stops[i - 1];
    if (t <= b) { const u = (t - a) / (b - a); return [0, 1, 2].map((k) => Math.round(ca[k] + u * (cb[k] - ca[k]))) as [number, number, number]; }
  }
  return stops[stops.length - 1][1];
}

interface Tracer { planet: number; rho: number; alpha: number; rgb: string; width: number }

export function LongExposure({ className }: { className?: string }) {
  const trails = useRef<HTMLCanvasElement>(null);
  const heads = useRef<HTMLCanvasElement>(null);
  const [still] = useState(() => typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);

  useEffect(() => {
    if (still) return;
    const tc = trails.current!, hc = heads.current!;
    const t = tc.getContext("2d")!, h = hc.getContext("2d")!;
    // deterministic tracers (same idea as the still: radii spread across each planet)
    let seed = 7;
    const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
    const tracers: Tracer[] = [];
    for (let k = 0; k < 3; k++) for (let j = 0; j < PER_PLANET; j++) {
      const rho = RP * (0.18 + 0.82 * (j + 0.2 + 0.6 * rnd()) / PER_PLANET);
      const [r, g, b] = colour(rho / RP);
      tracers.push({ planet: k, rho, alpha: rnd() * 2 * Math.PI, rgb: `${r},${g},${b}`, width: 0.7 + 0.6 * (rho / RP) });
    }

    let w = 0, ht = 0, dpr = 1, cx = 0, cy = 0, sc = 1;
    const resize = () => {
      dpr = Math.min(2, window.devicePixelRatio || 1);
      w = tc.clientWidth; ht = tc.clientHeight;
      for (const c of [tc, hc]) { c.width = Math.round(w * dpr); c.height = Math.round(ht * dpr); }
      t.setTransform(dpr, 0, 0, dpr, 0, 0); h.setTransform(dpr, 0, 0, dpr, 0, 0);
      cx = w * 0.52; cy = ht * 0.40;
      sc = (Math.min(w, ht * 0.85) * 0.44) / RR;
      t.fillStyle = "#050608"; t.fillRect(0, 0, w, ht);
      warm(5 * 2 * Math.PI);
    };
    const pos = (tr: Tracer, sun: number): [number, number] => {
      const car = sun / RATIO;
      const phi = car + (2 * Math.PI * tr.planet) / 3;
      const pl = (ZS * (phi - sun) + ZP * (phi + Math.PI) - Math.PI) / ZP;
      return [cx + sc * (CD * Math.cos(phi) + tr.rho * Math.cos(pl + tr.alpha)),
              cy + sc * (CD * Math.sin(phi) + tr.rho * Math.sin(pl + tr.alpha))];
    };
    let sun = 0;
    const segment = (from: number, to: number, steps: number) => {
      t.globalCompositeOperation = "lighter";
      t.lineCap = "round";
      for (const tr of tracers) {
        t.beginPath();
        let [x, y] = pos(tr, from);
        t.moveTo(x, y);
        for (let i = 1; i <= steps; i++) { [x, y] = pos(tr, from + ((to - from) * i) / steps); t.lineTo(x, y); }
        // a wide faint pass for the glow, then the bright core
        t.strokeStyle = `rgba(${tr.rgb},0.045)`; t.lineWidth = tr.width * 6; t.stroke();
        t.strokeStyle = `rgba(${tr.rgb},0.34)`; t.lineWidth = tr.width; t.stroke();
      }
      t.globalCompositeOperation = "source-over";
    };
    // draw some exposure up front so the panel is never empty
    const warm = (span: number) => { segment(sun - span, sun, Math.round(span * 60)); };

    const drawHeads = () => {
      h.clearRect(0, 0, w, ht);
      // the fixed ring and the sun, as faint outlines
      h.strokeStyle = "rgba(150,160,172,0.35)"; h.lineWidth = 1;
      for (const r of [RR + 1, RR - 1.25]) { h.beginPath(); h.arc(cx, cy, sc * r, 0, 2 * Math.PI); h.stroke(); }
      h.beginPath(); h.arc(cx, cy, sc * ZS / 2, 0, 2 * Math.PI); h.stroke();
      h.globalCompositeOperation = "lighter";
      for (const tr of tracers) {
        const [x, y] = pos(tr, sun);
        const g = h.createRadialGradient(x, y, 0, x, y, 9);
        g.addColorStop(0, `rgba(${tr.rgb},0.95)`); g.addColorStop(0.25, `rgba(${tr.rgb},0.35)`); g.addColorStop(1, `rgba(${tr.rgb},0)`);
        h.fillStyle = g; h.beginPath(); h.arc(x, y, 9, 0, 2 * Math.PI); h.fill();
      }
      h.globalCompositeOperation = "source-over";
    };

    let raf = 0, prev = 0, visible = true, fade = 0;
    const frame = (now: number) => {
      raf = requestAnimationFrame(frame);
      if (!visible || document.hidden) { prev = now; return; }
      const dt = prev ? Math.min(0.05, (now - prev) / 1000) : 0;
      prev = now;
      const next = sun + SPEED * dt;
      segment(sun, next, 4);
      sun = next;
      // slow fade, so old trails give way and the picture keeps changing
      fade += dt;
      if (fade > 0.2) { fade = 0; t.fillStyle = "rgba(5,6,8,0.018)"; t.fillRect(0, 0, w, ht); }
      drawHeads();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(tc);
    const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; });
    io.observe(tc);
    resize();
    raf = requestAnimationFrame(frame);
    return () => { cancelAnimationFrame(raf); ro.disconnect(); io.disconnect(); };
  }, [still]);

  if (still) return <img className={className} src="/home/signin.webp" alt="" width={1200} height={1500} decoding="async" />;
  return (
    <div className={className} aria-hidden="true">
      <canvas ref={trails} className="lx-layer" />
      <canvas ref={heads} className="lx-layer" />
    </div>
  );
}
