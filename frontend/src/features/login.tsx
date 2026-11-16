import { useMemo, useState, type FormEvent, type PointerEvent, type KeyboardEvent } from "react";
import { ArrowRight, Eye, EyeOff, Moon, Sun } from "lucide-react";
import { useApp } from "../stores/app";
import "./login.css";

/** Trace geometry: transmission error of a gear pair as a sum of mesh orders (illustrative). */
const W = 640, H = 260, MID = 130;
const N = 320;
function trace(phase: number, amp: number): number[] {
  return Array.from({ length: N + 1 }, (_, i) => {
    const t = (i / N) * Math.PI * 2 * 3;
    return MID - amp * (Math.sin(t + phase) * 0.62 + Math.sin(2 * t + phase * 1.7) * 0.24 + Math.sin(7.3 * t) * 0.07 + Math.sin(0.33 * t + 1) * 0.3);
  });
}
const path = (ys: number[]) => ys.map((y, i) => `${i ? "L" : "M"}${((i / N) * W).toFixed(1)} ${y.toFixed(1)}`).join(" ");
const um = (y: number) => ((MID - y) / 54) * 3.2; // illustrative scale: 54 px = 3.2 um

function Plate() {
  const measured = useMemo(() => trace(0.35, 54), []);
  const simulated = useMemo(() => trace(0, 50), []);
  const [hover, setHover] = useState<number | null>(null);
  const onMove = (e: PointerEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    setHover(Math.max(0, Math.min(N, Math.round(((e.clientX - r.left) / r.width) * N))));
  };
  const dev = hover === null ? null : um(measured[hover]) - um(simulated[hover]);
  const peak = Math.max(...measured.map((y, i) => Math.abs(um(y) - um(simulated[i]))));
  return (
    <aside className="lg-plate" aria-hidden="true">
      <div className="lg-plate-top">
        <a className="lg-brand" href="#/" style={{ color: "inherit", textDecoration: "none" }}><i className="mark" />MotionProof</a>
        <span className="lg-tag">Rev. 0.1 · local build</span>
      </div>

      <div className="lg-plate-body">
        <h2 className="lg-claim">Does the<br />assembly move<br />the way the<br />model says?</h2>
        <p className="lg-sub">Tolerance stacks, virtual assemblies and measured motion, checked against each other.</p>
        <dl className="lg-stats">
          <div><dt>Orders tracked</dt><dd>1 · 2 · 7.3</dd></div>
          <div><dt>Peak deviation</dt><dd>{peak.toFixed(2)} µm</dd></div>
          <div><dt>At cursor</dt><dd className={dev === null ? "dim" : ""}>{dev === null ? "move over trace" : `${dev >= 0 ? "+" : "−"}${Math.abs(dev).toFixed(2)} µm`}</dd></div>
        </dl>
      </div>

      <figure className="lg-scope">
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="presentation" onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
          {Array.from({ length: 13 }, (_, i) => <line key={`v${i}`} x1={i * 53.3} x2={i * 53.3} y1="0" y2={H} className="g" />)}
          {Array.from({ length: 6 }, (_, i) => <line key={`h${i}`} y1={i * 52} y2={i * 52} x1="0" x2={W} className="g" />)}
          <line x1="0" x2={W} y1={MID} y2={MID} className="zero" />
          <rect x="0" y={MID - 36} width={W} height="72" className="band" />
          <path d={path(simulated)} className="t sim" pathLength="1" />
          <path d={path(measured)} className="t mea" pathLength="1" />
          {hover !== null && <g className="cur">
            <line x1={(hover / N) * W} x2={(hover / N) * W} y1="0" y2={H} />
            <line x1={(hover / N) * W} x2={(hover / N) * W} y1={simulated[hover]} y2={measured[hover]} className="gap" />
          </g>}
        </svg>
        <div className="lg-legend">
          <span><i className="sw sim" />Simulated</span>
          <span><i className="sw mea" />Measured</span>
          <span className="lg-ill">Illustrative trace</span>
        </div>
      </figure>
    </aside>
  );
}

export function LoginScreen() {
  const login = useApp((s) => s.login);
  const theme = useApp((s) => s.theme);
  const toggleTheme = useApp((s) => s.toggleTheme);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [caps, setCaps] = useState(false);
  const [err, setErr] = useState<{ email?: string; password?: string }>({});

  function submit(e: FormEvent) {
    e.preventDefault();
    const next: typeof err = {};
    if (!/^\S+@\S+\.\S+$/.test(email)) next.email = "Enter an email address, like name@lab.org.";
    if (password.length < 1) next.password = "Enter your password.";
    setErr(next);
    if (next.email || next.password) return;
    setBusy(true);
    window.setTimeout(() => login(email.trim()), 450);
  }

  return (
    <div className="lg">
      <Plate />
      <main className="lg-side" id="main-content">
        <button className="btn ghost lg-theme" onClick={toggleTheme} aria-label={`Switch to ${theme === "light" ? "dark" : "light"} theme`}>
          {theme === "light" ? <Moon /> : <Sun />}
        </button>
        <form className="lg-form" onSubmit={submit} noValidate>
          <a className="lg-brand sm" href="#/"><i className="mark" />MotionProof</a>
          <h1>Sign in</h1>
          <p className="lg-lede">Open your workspace and pick up where the last run stopped.</p>

          <label className="lg-f">
            <span>Email</span>
            <input className="input" type="email" autoComplete="username" inputMode="email" value={email} autoFocus
              onChange={(e) => setEmail(e.target.value)} aria-invalid={!!err.email} aria-describedby={err.email ? "lg-e1" : undefined} placeholder="name@lab.org" />
            {err.email && <em id="lg-e1" className="lg-err">{err.email}</em>}
          </label>

          <label className="lg-f">
            <span>Password</span>
            <div className="lg-pw">
              <input className="input" type={show ? "text" : "password"} autoComplete="current-password" value={password}
                onChange={(e) => setPassword(e.target.value)} onKeyUp={(e: KeyboardEvent) => setCaps(e.getModifierState("CapsLock"))} onBlur={() => setCaps(false)} aria-invalid={!!err.password} aria-describedby={err.password ? "lg-e2" : undefined} />
              <button type="button" className="btn ghost" onClick={() => setShow(!show)} aria-label={show ? "Hide password" : "Show password"} aria-pressed={show}>
                {show ? <EyeOff /> : <Eye />}
              </button>
            </div>
            {caps && <em className="lg-caps" role="status">Caps Lock is on.</em>}
            {err.password && <em id="lg-e2" className="lg-err">{err.password}</em>}
          </label>

          <button className="btn primary lg-go" type="submit" disabled={busy}>
            {busy ? "Opening workspace…" : <>Sign in <ArrowRight /></>}
          </button>

          <p className="lg-note">
            This build keeps your session on this device only. Sign-in does not yet talk to a server.
          </p>
        </form>
        <footer className="lg-foot"><span>MotionProof</span><span>Evidence for mechanical motion</span></footer>
      </main>
    </div>
  );
}
