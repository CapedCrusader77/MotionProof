import { useState, type FormEvent, type KeyboardEvent } from "react";
import { ArrowRight, Eye, EyeOff, Moon, Sun } from "lucide-react";
import { useApp } from "../stores/app";
import "./login.css";

function Plate() {
  return (
    <aside className="lg-plate" aria-hidden="true">
      <div className="lg-plate-top">
        <a className="lg-brand" href="#/" style={{ color: "inherit", textDecoration: "none" }}><i className="mark" />MotionProof</a>
      </div>
      <div className="lg-plate-body">
        <h2 className="lg-claim">Tolerances in.<br />Motion out.</h2>
        <p className="lg-sub">MotionProof turns a CAD assembly and its tolerance specification into virtual
          as-manufactured copies, simulates each one and reports which fail, how often and why.</p>
        <ul className="lg-list">
          <li>Import STEP, STL, URDF or MJCF</li>
          <li>Specify limits, distributions and fits</li>
          <li>Simulate thousands of assembly variants</li>
          <li>Find the tolerances that drive failures</li>
        </ul>
      </div>
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
