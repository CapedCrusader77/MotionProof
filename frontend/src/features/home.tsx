import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, ArrowUpRight } from "lucide-react";
import { LoginScreen } from "./login";
import "./home.css";


/** Signed-out site: the homepage, and the sign-in screen at #/signin. */
export function PublicSite() {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const f = () => { setHash(window.location.hash); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);
  return hash === "#/signin" ? <LoginScreen /> : <Home />;
}

/* ------------------------------------------------------------------ hero: scroll-scrubbed Blender sequence */
const SEQ_FRAMES = 180;
const seqUrl = (i: number) => `/home/seq/s${String(i).padStart(3, "0")}.webp`;
const clamp = (v: number, a = 0, b = 1) => Math.min(b, Math.max(a, v));
// caption windows in scroll progress: [fade-in start, full, full end, fade-out end]
const CAPS: { id: string; w: [number, number, number, number]; eyebrow: string; title: string; body: string; cta?: boolean }[] = [
  { id: "c1", w: [-0.02, 0.0, 0.05, 0.08], eyebrow: "Overview", title: "See how manufacturing tolerances change the way a mechanism moves.", body: "MotionProof connects manufacturing variation to mechanical performance, from CAD geometry and tolerances to dynamic simulation and reliability.", cta: true },
  { id: "c2", w: [0.14, 0.165, 0.23, 0.26], eyebrow: "Mechanism", title: "Motor, planetary gearbox and link.", body: "A motor, a planetary gearbox and a robotic link: the chain that turns electrical input into positioned motion." },
  { id: "c3", w: [0.28, 0.31, 0.40, 0.43], eyebrow: "Parts", title: "The assembly, taken apart.", body: "Motor, shafts, bearings, both gear stages and the link, drawn apart so each part can be read on its own." },
  { id: "c4", w: [0.44, 0.465, 0.55, 0.58], eyebrow: "Gearbox", title: "Two planetary stages, three planets each.", body: "Sun gear, three planets, a fixed ring and a carrier per stage. In this film: 20T sun and planets, 60T ring, 4 : 1 per stage." },
  { id: "c5", w: [0.59, 0.61, 0.67, 0.695], eyebrow: "Tolerances", title: "Every dimension varies from part to part.", body: "Shaft diameter, bearing clearance, hole position and backlash all vary from part to part. Each gets a tolerance in MotionProof." },
  { id: "c6", w: [0.70, 0.72, 0.76, 0.78], eyebrow: "Variants", title: "Virtual copies built from the tolerances.", body: "MotionProof builds virtual as-manufactured copies of an assembly from its tolerance definitions." },
  { id: "c7", w: [0.79, 0.81, 0.85, 0.87], eyebrow: "Motion", title: "The gear train under load.", body: "Ideal reduction kinematics: the sun turns four times for every turn of the carrier. No tooth contact is solved in this film." },
  { id: "c8", w: [0.875, 0.89, 0.92, 0.935], eyebrow: "Population", title: "One assembly tells you little. A thousand give a pass rate.", body: "Run a thousand virtual copies and count how many still meet the requirement." },
  { id: "c9", w: [0.94, 0.955, 1.0, 1.02], eyebrow: "Results", title: "Results from the reference design follow below.", body: "This film shows an illustrative assembly. The results below come from MotionProof’s own reference design.", cta: true },
];
const capOpacity = (p: number, w: [number, number, number, number]) => p < w[0] || p > w[3] ? 0 : p < w[1] ? (p - w[0]) / (w[1] - w[0]) : p <= w[2] ? 1 : (w[3] - p) / (w[3] - w[2]);

function ScrollHero() {
  const wrap = useRef<HTMLElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [p, setP] = useState(0);
  const [loaded, setLoaded] = useState(0);
  const reduce = useMemo(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches, []);

  useEffect(() => {
    const el = wrap.current!, cv = canvas.current!;
    const ctx = cv.getContext("2d")!;
    const small = window.matchMedia("(max-width: 760px)").matches;
    const stride = small ? 2 : 1;                                    // phones fetch every second frame
    const imgs: (HTMLImageElement | null)[] = Array(SEQ_FRAMES).fill(null);
    let count = 0, cur = 0, target = reduce ? SEQ_FRAMES - 1 : 0, raf = 0, shown = -1, dead = false;
    const order: number[] = [0, SEQ_FRAMES - 1];
    for (let step = 16; step >= stride; step = Math.max(stride, Math.floor(step / 2))) { for (let i = 0; i < SEQ_FRAMES; i += step * stride) order.push(i); if (step === stride) break; }
    for (let i = 0; i < SEQ_FRAMES; i += stride) order.push(i);
    const queue = [...new Set(order)].filter((i) => i % stride === 0 || i === SEQ_FRAMES - 1);
    let active = 0;
    const pump = () => {
      while (active < 4 && queue.length && !dead) {
        const i = queue.shift()!; active++;
        const im = new Image(); im.decoding = "async"; im.src = seqUrl(i);
        im.onload = () => { imgs[i] = im; count++; active--; setLoaded(count); pump(); };
        im.onerror = () => { active--; pump(); };
      }
    };
    pump();
    const nearest = (i: number) => { for (let d = 0; d < SEQ_FRAMES; d++) { const a = imgs[i - d], b = imgs[i + d]; if (a) return a; if (b) return b; } return null; };
    const draw = (i: number) => {
      const im = nearest(i); if (!im) return;
      if (cv.width !== im.naturalWidth) { cv.width = im.naturalWidth; cv.height = im.naturalHeight; }
      ctx.drawImage(im, 0, 0);
    };
    const progress = () => { const r = el.getBoundingClientRect(); return clamp(-r.top / (r.height - window.innerHeight)); };
    const onScroll = () => { const pr = progress(); target = pr * (SEQ_FRAMES - 1); setP(pr); };
    const tick = () => {
      cur += (target - cur) * (reduce ? 1 : 0.14);                   // damped follow: smooth, fully reversible
      const i = Math.round(cur);
      if (i !== shown || count % 5 === 0) { draw(i); shown = i; }
      raf = requestAnimationFrame(tick);
    };
    onScroll(); window.addEventListener("scroll", onScroll, { passive: true }); window.addEventListener("resize", onScroll);
    raf = requestAnimationFrame(tick);
    return () => { dead = true; cancelAnimationFrame(raf); window.removeEventListener("scroll", onScroll); window.removeEventListener("resize", onScroll); };
  }, [reduce]);

  const jump = (q: number) => {
    const el = wrap.current!; const top = el.getBoundingClientRect().top + window.scrollY;
    window.scrollTo({ top: top + q * (el.offsetHeight - window.innerHeight), behavior: reduce ? "auto" : "smooth" });
  };
  const active = CAPS.findIndex((c) => capOpacity(p, c.w) > 0.5);

  return (
    <section className="sq" ref={wrap} aria-label="Reference design, shown as a scroll-driven film">
      <div className="sq-stick">
        <canvas ref={canvas} width={1600} height={900} className={loaded > 0 ? "on" : ""} role="img" aria-label="Rendered two-stage planetary gearbox and arm, filmed from a close-up to a wide shot as you scroll." />
        <div className="sq-shade" aria-hidden="true" />
        {CAPS.map((c, i) => (
          <div key={c.id} className={`sq-cap ${i === 0 ? "first" : ""}`} style={{ opacity: capOpacity(p, c.w), transform: `translateY(${(1 - capOpacity(p, c.w)) * 14}px)`, pointerEvents: capOpacity(p, c.w) > 0.5 ? "auto" : "none" }} aria-hidden={capOpacity(p, c.w) < 0.5}>
            {i === 0 ? <h1>{c.title}</h1> : <h2>{c.title}</h2>}
            <p className="hm-lede">{c.body}</p>
            {c.cta && <div className="hm-cta">
              <a className="btn primary" href="#evidence" onClick={(e) => { e.preventDefault(); document.getElementById("evidence")?.scrollIntoView({ behavior: "smooth" }); }}>Explore the evidence <ArrowRight /></a>
              <a className="btn hm-ghost" href="#/signin">Open the workbench</a>
            </div>}
          </div>
        ))}
        <nav className="sq-dots" aria-label="Film chapters">
          {CAPS.map((c, i) => <button key={c.id} className={i === active ? "on" : ""} onClick={() => jump((c.w[1] + c.w[2]) / 2)} aria-label={`Go to: ${c.title}`} aria-current={i === active}><span>{c.eyebrow}</span></button>)}
        </nav>
        <div className="sq-load" style={{ opacity: loaded >= SEQ_FRAMES / 2 ? 0 : 1 }} aria-hidden="true"><i style={{ width: `${(loaded / (SEQ_FRAMES / 2)) * 100}%` }} /></div>
        <p className="sq-note">Illustrative assembly (20T / 60T, 16 : 1). Not the reference design behind the results below. No tooth contact is simulated.</p>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ real results */
interface Variant { id: string; scenario: string; passed: boolean; metrics: Record<string, number>; failures: { constraint: string; value: number; limit: number }[]; values: Record<string, number> }
interface Data {
  provenance: { statement: string; experiment: { id: string; name: string; scenarios: number; valid: number; passed: number } };
  variants: Variant[];
  population: { direction_error_ee: number[]; lost_motion: number[]; passed: boolean[] };
  sensitivity: { metric: string; method: string; caveat: string; rows: { parameter: string; rho: number; interval: number[]; direction: string }[] };
}
const wilson = (k: number, n: number): [number, number] => { const z = 1.96, p = k / n, d = 1 + z * z / n, c = p + z * z / (2 * n), m = z * Math.sqrt((p * (1 - p) + z * z / (4 * n)) / n); return [(c - m) / d, (c + m) / d]; };
const pretty = (s: string) => s.replace(/_/g, " ").replace(/^s(\d) /, "stage $1 ");

function Evidence() {
  const [data, setData] = useState<Data | null>(null);
  const [err, setErr] = useState(false);
  const [limit, setLimit] = useState(2.0);        // direction error at the end effector, mm (model requirement: 2.0)
  const [vi, setVi] = useState(2);
  useEffect(() => { fetch("/assets/motionproof/data.json").then((r) => r.json()).then(setData).catch(() => setErr(true)); }, []);

  const view = useMemo(() => {
    if (!data) return null;
    const mm = data.population.direction_error_ee.map((v) => v * 1000);
    const BINS = 28, MAX = 3.0, bins = new Array(BINS).fill(0);
    mm.forEach((v) => { bins[Math.min(BINS - 1, Math.floor((v / MAX) * BINS))]++; });
    const under = mm.filter((v) => v <= limit).length;
    return { bins, BINS, MAX, under, n: mm.length, top: Math.max(...bins) };
  }, [data, limit]);

  return (
    <section className="hm-sec hm-sim" id="evidence" aria-labelledby="h-sim">
      <div className="hm-wrap">
        <h2 id="h-sim">Results: 1000 virtual assemblies of the reference design</h2>
        {err && <p className="hm-lede">The results file could not be loaded. Start the MotionProof server or rebuild the web app to include it.</p>}
        {data && view && (() => {
          const e = data.provenance.experiment, [lo, hi] = wilson(e.passed, e.valid), v = data.variants[vi];
          return (
            <div className="hm-ev">
              <div className="hm-evmain">
                <figure className="hm-hist" aria-label={`${view.under} of ${view.n} assemblies have direction error at or below ${limit.toFixed(2)} millimetres`}>
                  <div className="hm-big"><b className={e.passed / e.valid >= 0.95 ? "ok" : "bad"}>{((e.passed / e.valid) * 100).toFixed(1)}%</b>
                    <span>{e.passed} of {e.valid} assemblies meet every requirement. Wilson 95 % interval {(lo * 100).toFixed(1)}–{(hi * 100).toFixed(1)} %.</span></div>
                  <svg viewBox="0 0 100 52" preserveAspectRatio="none" role="presentation">
                    {view.bins.map((n, i) => {
                      const h = (n / view.top) * 44, fail = ((i + 0.5) / view.BINS) * view.MAX > limit;
                      return <rect key={i} x={(i / view.BINS) * 100} y={48 - h} width={100 / view.BINS - 0.5} height={Math.max(h, 0.4)} className={fail ? "f" : "p"} />;
                    })}
                    <line x1={(limit / view.MAX) * 100} x2={(limit / view.MAX) * 100} y1="0" y2="48" className="lim" vectorEffect="non-scaling-stroke" />
                    <line x1="0" x2="100" y1="48" y2="48" className="ax" vectorEffect="non-scaling-stroke" />
                  </svg>
                  <div className="hm-axis"><span>0</span><span>Direction error at the end effector, mm</span><span>3.0</span></div>
                  <label className="hm-slide"><span>Limit <b>{limit.toFixed(2)} mm</b>{Math.abs(limit - 2) < 0.011 ? " (the model’s own requirement)" : ""}</span>
                    <input type="range" min="0.2" max="3" step="0.05" value={limit} onChange={(ev) => setLimit(+ev.target.value)} /></label>
                  <p className="hm-sub"><b>{view.under}</b> of {view.n} assemblies are at or below {limit.toFixed(2)} mm. This one requirement; the pass rate above applies all four.</p>
                </figure>

                <div className="hm-var">
                  <div className="hm-tabs" role="tablist" aria-label="Real scenarios">
                    {data.variants.map((x, n) => <button key={x.id} role="tab" aria-selected={n === vi} className={n === vi ? "on" : ""} onClick={() => setVi(n)}>{x.id === "typical" ? "Typical" : x.id === "p90" ? "90th percentile" : "Worst"}</button>)}
                  </div>
                  <dl className="hm-facts hm-facts4">
                    <div><dt>Scenario</dt><dd>{v.scenario}</dd></div>
                    <div><dt>Direction error</dt><dd>{(v.metrics.direction_error_ee * 1000).toFixed(2)} mm</dd></div>
                    <div><dt>Lost motion</dt><dd>{(v.metrics.lost_motion * 1000).toFixed(2)} mrad</dd></div>
                    <div><dt>Result</dt><dd className={v.passed ? "okc" : "badc"}>{v.passed ? "● Passed" : "■ Failed"}</dd></div>
                  </dl>
                  <p className="hm-sub">{v.passed ? "Meets all four requirements." : v.failures.map((f) => `${f.constraint.replace("_", " ")}: ${f.value.toPrecision(3)} against ${f.limit}`).join(" · ")}</p>
                </div>
              </div>

              <div className="hm-sens">
                <h3>Which tolerances drive the error</h3>
                <ol>
                  {data.sensitivity.rows.slice(0, 6).map((r) => (
                    <li key={r.parameter}><span>{pretty(r.parameter)}</span><i style={{ width: `${Math.abs(r.rho) * 180}%` }} /><b>{r.rho.toFixed(2)}</b></li>))}
                </ol>
                <p className="hm-sub">Spearman rank correlation with maximum angle error across the 1000 scenarios. {data.sensitivity.caveat}.</p>
                <p className="hm-sub hm-prov2">Synthetic reference design: tolerances, motor and gearbox values are illustrative assumptions, not anyone’s hardware. Experiment {e.id}, {e.scenarios} scenarios.</p>
              </div>
            </div>);
        })()}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ pipeline */
const STEPS = [
  ["Import", "STEP, STL, OBJ, URDF or MJCF. Cylinders on STEP solids are detected and fits are measured exactly from the B-rep."],
  ["Specify", "Limits, distributions, datums, fits and correlations, with a validation panel that flags what is missing."],
  ["Sample", "Monte Carlo, Latin hypercube or Sobol designs with Gaussian-copula correlation, turned into virtual as-manufactured assemblies."],
  ["Simulate", "MuJoCo multibody plus a drive-train with backlash, stiffness, friction and a motor torque-speed limit. Every scenario replays bit for bit."],
  ["Optimise", "Search for the cheapest tolerance set that still meets the requirement, then check the answer on fresh scenarios."],
] as const;

function Pipeline() {
  const [on, setOn] = useState(3);
  return (
    <section className="hm-sec hm-pipe" id="how" aria-labelledby="h-how">
      <div className="hm-wrap">
        <h2 id="h-how">Workflow: from a CAD file to a tolerance specification</h2>
        <ol className="hm-steps">
          {STEPS.map(([t, d], i) => (
            <li key={t} className={i === on ? "on" : ""}>
              <button onClick={() => setOn(i)} onMouseEnter={() => setOn(i)} onFocus={() => setOn(i)} aria-expanded={i === on}>
                <span className="n">0{i + 1}</span><span className="t">{t}</span>
              </button>
              <p>{d}</p>
            </li>
          ))}
        </ol>
        <div className="hm-track" aria-hidden="true"><i style={{ width: `${((on + 1) / STEPS.length) * 100}%` }} /></div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ the application */
const SHOTS = [
  ["robustness", "Robustness", "200 virtual assemblies of a two-stage 33:1 planetary elbow. Pass rate with its confidence interval, failures in red."],
  ["sensitivity", "Sensitivity", "Which tolerances drive the error, with 95 % intervals and the raw scatter behind each ranking."],
  ["workbench", "Workbench", "Component tree, 3D view with x-ray and section, and a readiness check that refuses to hide assumed values."],
  ["tolerances", "Tolerances", "Limits, distributions, datums, fits and correlations, with a validation panel."],
] as const;

function App() {
  const [i, setI] = useState(0);
  return (
    <section className="hm-sec hm-app" id="app" aria-labelledby="h-app">
      <div className="hm-wrap">
        <div className="hm-apphead">
          <div><h2 id="h-app">The application</h2></div>
          <div className="hm-tabs" role="tablist" aria-label="Screens">
            {SHOTS.map(([k, label], n) => <button key={k} role="tab" aria-selected={n === i} className={n === i ? "on" : ""} onClick={() => setI(n)}>{label}</button>)}
          </div>
        </div>
        <div className="hm-frame">
          <div className="hm-chrome" aria-hidden="true"><i /><i /><i /><span>motionproof / {SHOTS[i][0]}</span></div>
          {SHOTS.map(([k], n) => <img key={k} src={`/home/${k}.png`} alt={`${SHOTS[n][1]} screen`} className={n === i ? "on" : ""} loading="lazy" />)}
        </div>
        <p className="hm-note">{SHOTS[i][2]} Screenshots show the synthetic reference design; its tolerances are illustrative assumptions.</p>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ page */
function Home() {
  return (
    <div className="hm">
      <a className="skip-link" href="#hm-main">Skip to content</a>
      <header className="hm-nav">
        <a className="hm-brand" href="#/"><i className="mark" />MotionProof</a>
        <nav aria-label="Sections"><a href="#evidence" onClick={(e) => { e.preventDefault(); document.getElementById("evidence")?.scrollIntoView({ behavior: "smooth" }); }}>Evidence</a>
          <a href="#how" onClick={(e) => { e.preventDefault(); document.getElementById("how")?.scrollIntoView({ behavior: "smooth" }); }}>Workflow</a>
          <a href="#app" onClick={(e) => { e.preventDefault(); document.getElementById("app")?.scrollIntoView({ behavior: "smooth" }); }}>Application</a></nav>
        <a className="btn primary hm-signin" href="#/signin">Sign in</a>
      </header>

      <main id="hm-main">
        <ScrollHero />

        <Evidence />
        <Pipeline />
        <App />

        <section className="hm-sec hm-close" aria-labelledby="h-close">
          <div className="hm-wrap hm-closegrid">
            <h2 id="h-close">Predictions, with their provenance.</h2>
            <div>
              <p className="hm-lede">Results are model predictions, conditional on the geometry, tolerances and drive-train values you supply. Nothing here certifies real-world reliability. Every value carries its provenance, and the app shows which is which.</p>
              <ul className="hm-prov"><li><i>■</i>Specified</li><li><i>●</i>Measured</li><li><i>◐</i>Estimated</li><li><i>○</i>Assumed</li></ul>
              <a className="btn primary" href="#/signin">Open the workbench <ArrowUpRight /></a>
            </div>
          </div>
        </section>
      </main>
      <footer className="hm-foot"><span>MotionProof</span><span>MIT licence · MuJoCo 3.14 · Python 3.12</span></footer>
    </div>
  );
}
