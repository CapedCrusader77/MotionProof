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
const clamp = (v: number, a = 0, b = 1) => Math.min(b, Math.max(a, v));
// caption windows in scroll progress: [fade-in start, full, full end, fade-out end]
const CAPS: { id: string; w: [number, number, number, number]; eyebrow: string; title: string; body: string; cta?: boolean; stats?: [string, string][] }[] = [
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

type Cap = (typeof CAPS)[number];
interface FilmProps { caps: Cap[]; frames: number; url: (i: number) => string; label: string; alt: string; note?: string; hero?: boolean }
function ScrollFilm({ caps: CAPSx, frames: SEQ_FRAMES, url: seqUrl, label, alt, hero }: FilmProps) {
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
    const imgs: (ImageBitmap | HTMLImageElement | null)[] = Array(SEQ_FRAMES).fill(null);
    let count = 0, cur = 0, target = 0, raf = 0, dead = false;
    const order: number[] = [0, SEQ_FRAMES - 1];
    for (let step = 16; step >= stride; step = Math.max(stride, Math.floor(step / 2))) { for (let i = 0; i < SEQ_FRAMES; i += step * stride) order.push(i); if (step === stride) break; }
    for (let i = 0; i < SEQ_FRAMES; i += stride) order.push(i);
    const queue = [...new Set(order)].filter((i) => i % stride === 0 || i === SEQ_FRAMES - 1);
    let active = 0;
    const pump = () => {
      while (active < 8 && queue.length && !dead) {
        const i = queue.shift()!; active++;
        const im = new Image(); im.decoding = "async"; im.src = seqUrl(i);
        // pre-decode to an ImageBitmap so drawing never waits on decoding; re-render React only every 24 loads
        const done = (b: ImageBitmap | HTMLImageElement) => { if (dead) return; imgs[i] = b; count++; active--; if (count % 24 === 0 || !queue.length) setLoaded(count); pump(); };
        im.onload = () => { ("createImageBitmap" in window ? createImageBitmap(im) : Promise.reject()).then(done, () => done(im)); };
        im.onerror = () => { active--; pump(); };
      }
    };
    pump();
    const nearest = (i: number) => { for (let d = 0; d < SEQ_FRAMES; d++) { const a = imgs[i - d], b = imgs[i + d]; if (a) return a; if (b) return b; } return null; };
    // draw the nearest loaded frame; frames are dense enough that no blending (and no ghosting) is needed
    const draw = (i: number) => {
      const im = nearest(i); if (!im) return;
      const w = "naturalWidth" in im ? im.naturalWidth : im.width, h = "naturalHeight" in im ? im.naturalHeight : im.height;
      if (cv.width !== w) { cv.width = w; cv.height = h; }
      ctx.drawImage(im, 0, 0);
    };
    const progress = () => { const r = el.getBoundingClientRect(); return clamp(-r.top / (r.height - window.innerHeight)); };
    const onScroll = () => { const pr = progress(); target = pr * (SEQ_FRAMES - 1); setP(pr); };
    let shown = -1, drawnWith = -1;
    const tick = () => {
      cur += (target - cur) * (reduce ? 1 : 0.12);                  // damped follow: smooth, fully reversible
      if (Math.abs(target - cur) < 0.02) cur = target;
      const i = Math.round(cur);
      if (i !== shown || drawnWith !== count) { draw(i); shown = i; drawnWith = count; }   // redraw only on change
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
  const active = CAPSx.findIndex((c) => capOpacity(p, c.w) > 0.5);

  return (
    <section className={hero ? "sq" : "sq sq-b"} ref={wrap} aria-label={label}>
      <div className="sq-stick">
        <canvas ref={canvas} width={1600} height={900} className={loaded > 0 ? "on" : ""} role="img" aria-label={alt} />
        <div className="sq-shade" aria-hidden="true" style={{ ["--end" as string]: clamp((p - 0.9) / 0.05) } as React.CSSProperties} />
        <div className="sq-grain" aria-hidden="true" />
        {CAPSx.map((c, i) => (
          <div key={c.id} className={`sq-cap ${i === 0 ? "first" : ""}`} style={{ opacity: capOpacity(p, c.w), transform: `translateY(${(1 - capOpacity(p, c.w)) * 14}px)`, pointerEvents: capOpacity(p, c.w) > 0.5 ? "auto" : "none", visibility: capOpacity(p, c.w) > 0.02 ? "visible" : "hidden" }} aria-hidden={capOpacity(p, c.w) < 0.5}>
            <p className="sq-eyebrow"><b>{String(i + 1).padStart(2, "0")}</b><i />{c.eyebrow}</p>
            {hero && i === 0 ? <h1>{c.title}</h1> : <h2>{c.title}</h2>}
            <p className="hm-lede">{c.body}</p>
            {c.stats && <dl className="sq-stats">{c.stats.map(([v, k]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>}
            {c.cta && <div className="hm-cta">
              <a className="btn primary reg" href="#evidence" onClick={(e) => { e.preventDefault(); document.getElementById("evidence")?.scrollIntoView({ behavior: "smooth" }); }}>{c.stats ? "See the results" : "Explore the evidence"} <ArrowRight /></a>
              <a className="btn hm-ghost ink-ghost" href="#/signin">Open the workbench</a>
            </div>}
          </div>
        ))}
        <nav className="sq-dots" aria-label="Film chapters">
          {CAPSx.map((c, i) => <button key={c.id} className={i === active ? "on" : ""} onClick={() => jump((c.w[1] + c.w[2]) / 2)} aria-label={`Go to: ${c.title}`} aria-current={i === active}><span>{c.eyebrow}</span></button>)}
        </nav>
        <div className="sq-load" style={{ opacity: loaded >= SEQ_FRAMES / 2 ? 0 : 1 }} aria-hidden="true"><i style={{ width: `${(loaded / (SEQ_FRAMES / 2)) * 100}%` }} /></div>
        <div className="sq-prog" aria-hidden="true"><i style={{ transform: `scaleX(${p})` }} /><span>{String(Math.round(p * 100)).padStart(3, "0")}</span></div>
      </div>
    </section>
  );
}

function ScrollHero() {
  return <ScrollFilm hero caps={ENG_CAPS} frames={ENG_FRAMES} url={engUrl} label="Turbocharged engine, shown as a scroll-driven film"
    alt="Rendered turbocharged four-cylinder engine: the finished engine, taken apart, past the turbocharger and into one cylinder bore as you scroll."
    note="Illustrative engine, modelled in Blender. Not a real manufacturer's design, not a MotionProof result, not a validated simulation." />;
}

/* ------------------------------------------------------------------ hero film: engine (short cinematic cut) */
// the last 40 rendered frames (deep inside the bore) are the softest and are left out
const ENG_RENDERED = 480;
const ENG_FRAMES = 440;
// The film is played backwards: it opens on the finished engine, takes it apart and ends inside
// one cylinder bore, on a single toleranced dimension.
const engUrl = (i: number) => `/home/engine/f${String(ENG_RENDERED - 1 - i).padStart(4, "0")}.webp`;
const ENG_CAPS: Cap[] = [
  { id: "e1", w: [-0.02, 0.0, 0.08, 0.10], eyebrow: "Engine", title: "See how manufacturing tolerances change the way a mechanism moves.", body: "MotionProof connects manufacturing variation to mechanical performance, from CAD geometry and tolerances to dynamic simulation and reliability.", cta: true },
  { id: "e4", w: [0.10, 0.13, 0.33, 0.37], eyebrow: "Parts", title: "Taken apart, part by part.", body: "Each part pulled out along the axis it assembles on." },
  { id: "e3", w: [0.39, 0.42, 0.51, 0.54], eyebrow: "Turbo", title: "Stack-ups decide how it fits.", body: "Small deviations add up across flanges, housings and shafts." },
  { id: "e2", w: [0.74, 0.78, 0.87, 0.90], eyebrow: "Bore", title: "Every bore, pin and journal has a tolerance.", body: "Pistons, rods and crank follow slider-crank geometry. Each dimension can vary from part to part, down to this Ø86 H7 bore." },
  { id: "e5", w: [0.93, 0.955, 1.0, 1.02], eyebrow: "Results", title: "A thousand virtual copies. One pass rate.", body: "The numbers below come from MotionProof's reference design, a two-stage planetary robot joint, sampled and simulated 1000 times.", cta: true,
    stats: [["1000", "virtual assemblies"], ["73.9 %", "meet every requirement"], ["4", "requirements checked"]] },
];
/* ------------------------------------------------------------------ parts: the engine's toleranced features */
const PARTS: { key: string; name: string; alt: string; feats: [string, string][] }[] = [
  { key: "crank", name: "Pistons, rods and crank", alt: "Section through four cylinders: pistons, connecting rods and crankshaft",
    feats: [["Cylinder bore", "Ø86 H7"], ["Crank pin", "Ø44 g6"], ["Piston-to-bore clearance", "fit"], ["Main journal runout", "geometric"]] },
  { key: "timing", name: "Timing drive", alt: "Timing belt over two cam sprockets, idler, tensioner and crank pulley",
    feats: [["Cam journal", "Ø25 H7/f6"], ["Sprocket bore runout", "geometric"], ["Belt pitch length", "size"], ["Tensioner pivot position", "position"]] },
  { key: "turbo", name: "Turbocharger", alt: "Section through a turbocharger: compressor wheel, shaft and turbine wheel",
    feats: [["Wheel tip-to-shroud gap", "clearance"], ["Shaft runout", "geometric"], ["Bearing bore", "H6"], ["Housing flange flatness", "form"]] },
];

function Parts() {
  return (
    <section className="hm-sec hm-parts" id="parts" aria-labelledby="h-parts">
      <div className="hm-wrap">
        <div className="hm-parts-head">
          <h2 id="h-parts">Every moving part has a dimension that varies.</h2>
          <p className="hm-lede">MotionProof gives each toleranced feature a distribution, builds a thousand virtual copies of the assembly and runs every one.</p>
        </div>
        <ul className="hm-parts-grid">
          {PARTS.map((p) => (
            <li key={p.key} className="hm-part">
              <div className="hm-part-img"><img src={`/home/part-${p.key}.webp`} alt={p.alt} loading="lazy" width={1200} height={900} /></div>
              <h3>{p.name}</h3>
              <dl>{p.feats.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
            </li>
          ))}
        </ul>
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

/* ------------------------------------------------------------------ products: an index, a screen, a spec sheet */
interface Product { key: string; cat: string; name: string; lead: string; general: string; features: string[]; specs: [string, string][] }
const CATS = ["Model", "Manufacturing", "Simulation", "Analysis", "Evidence"] as const;
const PRODUCTS: Product[] = [
  { key: "projects", cat: "Model", name: "Projects", lead: "One place for a mechanism's models, experiments and results.",
    general: "Every model, experiment and artifact lives in a project. The overview shows what exists, what ran, and the next step.",
    features: ["Models and experiments listed with their outcomes", "Add the reference design in one action", "Experiment manifests are immutable"],
    specs: [["Storage", "SQLite workspace plus files"], ["Experiments", "Immutable manifests"], ["Replay", "Bit-exact, any scenario"], ["Resume", "Checkpointed runs"]] },
  { key: "workbench", cat: "Model", name: "Assembly workbench", lead: "Component tree, 3D view and a readiness check that refuses to hide assumed values.",
    general: "Import a CAD assembly, inspect it in 3D with x-ray and section views, and see what the model still lacks before anything runs.",
    features: ["Component tree with groups and bodies", "X-ray and section views", "Readiness check on every assumption"],
    specs: [["Import", "STEP, STL, OBJ, URDF, MJCF"], ["STEP solids", "Cylinder detection"], ["Fit measurement", "Exact, from the B-rep"], ["Provenance", "Specified, assumed, measured"]] },
  { key: "tolerances", cat: "Manufacturing", name: "Tolerances", lead: "Limits, distributions, datums, fits and correlations in one table.",
    general: "Each tolerance carries a distribution, a datum and a source. A validation panel flags what is missing or inconsistent.",
    features: ["Datums and fits per feature", "Correlated tolerances", "Validation panel"],
    specs: [["Distributions", "Six"], ["Correlation", "Gaussian copula"], ["Sampling designs", "Five"], ["Statistics", "Cp, Cpk, stack-ups"]] },
  { key: "mechanics", cat: "Simulation", name: "Mechanical model", lead: "A reduced-order drive-train on MuJoCo, with the physics you can name.",
    general: "Each driven joint couples a rotor to the output through a dead band and a torsional spring. Backlash is computed per variant from the gear stages.",
    features: ["Backlash from sun-planet and planet-ring clearance", "Stiffness, efficiency and friction", "Motor torque-speed limit"],
    specs: [["Engine", "MuJoCo 3.14 multibody"], ["Backlash", "Worst planet wins"], ["Fidelity", "Reduced order"], ["Not modelled", "Tooth contact, FEA"]] },
  { key: "hardware", cat: "Simulation", name: "Hardware testing", lead: "Run the same experiment on a physical rig and compare.",
    general: "A JSON-lines protocol connects a rig to MotionProof, with a safety monitor in front of every command.",
    features: ["JSON-lines rig protocol", "Safety monitor", "Encoder analysis without the model"],
    specs: [["Firmware", "ESP32 sketch included"], ["Protocol", "JSON lines"], ["Physical validation", "Not yet run"], ["Benchmark J", "Waits for a rig"]] },
  { key: "robustness", cat: "Analysis", name: "Robustness", lead: "How many virtual copies still meet the requirement, with an honest interval.",
    general: "Pass rate across every sampled assembly, the constraints that fail, and the distribution of each metric.",
    features: ["Wilson and Clopper-Pearson intervals", "Failure categories you can drill into", "Histograms with the limit drawn"],
    specs: [["Reference run", "1000 scenarios"], ["Pass rate", "73.9 % (739 of 1000)"], ["Interval", "71.1 to 76.5 %"], ["Requirements", "Four constraints"]] },
  { key: "sensitivity", cat: "Analysis", name: "Sensitivity", lead: "Which tolerances drive the error, and how sure we are.",
    general: "Rank every tolerance by its effect on a chosen metric, with intervals and the raw scatter behind each ranking.",
    features: ["Spearman rank correlation", "Standardised regression", "Sobol indices"],
    specs: [["Reference run", "1000 scenarios"], ["Top driver", "Output friction, rho 0.44"], ["Caveat", "Association, not causation"], ["Also", "Worst-case search"]] },
  { key: "trust", cat: "Evidence", name: "Model trust", lead: "The evidence behind every parameter.",
    general: "Every value is marked generated, estimated, assumed or measured, and the model's overall trust follows the weakest link.",
    features: ["Evidence level per parameter", "Calibration reports attached", "Nothing certified without measurement"],
    specs: [["Levels", "Specified, measured, estimated, assumed"], ["Reference design", "Synthetic, illustrative"], ["Claims", "Predictions, not certificates"], ["Calibration", "Physical, when measured"]] },
  { key: "benchmarks", cat: "Evidence", name: "Benchmarks", lead: "Fourteen reference problems with independent expected values.",
    general: "A fixed suite checks the engine against answers worked out another way. One benchmark stays marked not run until a physical rig exists.",
    features: ["Independent expected values", "Run from the app or the CLI", "Failures are shown, not hidden"],
    specs: [["Problems", "14"], ["Passing", "13"], ["Not run", "J, needs a physical rig"], ["Tests", "225 passing"]] },
];

function Products() {
  const [i, setI] = useState(5);
  const pr = PRODUCTS[i];
  const go = (n: number) => setI((n + PRODUCTS.length) % PRODUCTS.length);
  return (
    <section className="hm-sec hm-prod" id="app" aria-labelledby="h-app">
      <div className="hm-wrap">
        <div className="pr-head">
          <p className="hm-eyebrow">Products</p>
          <h2 id="h-app">Nine of the twenty-nine screens, built around the work.</h2>
        </div>
        <div className="pr-grid">
          <nav className="pr-index" aria-label="Products">
            {CATS.map((c, ci) => (
              <div key={c} className="pr-cat">
                <p><span>{String(ci + 1).padStart(2, "0")}</span>{c}</p>
                {PRODUCTS.map((x, n) => x.cat === c && (
                  <button key={x.key} className={n === i ? "on" : ""} onClick={() => setI(n)} aria-current={n === i}>{x.name}</button>))}
              </div>))}
          </nav>
          <div className="pr-stage">
            <div className="pr-top"><span>{String(i + 1).padStart(3, "0")} / {String(PRODUCTS.length).padStart(3, "0")}</span><span>{pr.cat}</span></div>
            <h3 className="pr-name">{pr.name}</h3>
            <div className="pr-frame">
              <div className="hm-chrome" aria-hidden="true"><i /><i /><i /><span>motionproof / {pr.key}</span></div>
              {PRODUCTS.map((x, n) => <img key={x.key} src={`/home/${x.key}.png`} alt={`${x.name} screen`} className={n === i ? "on" : ""} loading="lazy" />)}
            </div>
            <div className="pr-sheet">
              <div><h4><span>01</span>General information</h4><p className="lead">{pr.lead}</p><p>{pr.general}</p></div>
              <div><h4><span>02</span>Features</h4><ul>{pr.features.map((f) => <li key={f}>{f}</li>)}</ul></div>
              <div><h4><span>03</span>Specifications</h4><dl>{pr.specs.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl></div>
            </div>
            <div className="pr-nav">
              <button onClick={() => go(i - 1)}>Previous</button>
              <button onClick={() => go(i + 1)}>Next product <ArrowRight /></button>
            </div>
          </div>
        </div>
        <p className="hm-note">Screenshots show the synthetic reference design; its tolerances are illustrative assumptions. Figures are from the reference experiment EXP_001 and the project's test and benchmark records.</p>
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
          <a href="#app" onClick={(e) => { e.preventDefault(); document.getElementById("app")?.scrollIntoView({ behavior: "smooth" }); }}>Products</a></nav>
        <a className="btn primary hm-signin reg" href="#/signin">Sign in</a>
      </header>

      <main id="hm-main">
        <ScrollHero />
        <Parts />

        <Evidence />
        <Pipeline />
        <Products />

        <section className="hm-sec hm-close" aria-labelledby="h-close">
          <div className="hm-wrap hm-closegrid">
            <h2 id="h-close">Predictions, with their provenance.</h2>
            <div>
              <p className="hm-lede">Results are model predictions, conditional on the geometry, tolerances and drive-train values you supply. Nothing here certifies real-world reliability. Every value carries its provenance, and the app shows which is which.</p>
              <ul className="hm-prov"><li><i>■</i>Specified</li><li><i>●</i>Measured</li><li><i>◐</i>Estimated</li><li><i>○</i>Assumed</li></ul>
              <a className="btn primary reg" href="#/signin">Open the workbench <ArrowUpRight /></a>
            </div>
          </div>
        </section>
      </main>
      <footer className="hm-foot"><span>MotionProof</span><span>Engine film: an illustrative model rendered in Blender, not a real manufacturer’s design and not a MotionProof result.</span><span>MIT licence · MuJoCo 3.14 · Python 3.12</span></footer>
    </div>
  );
}
