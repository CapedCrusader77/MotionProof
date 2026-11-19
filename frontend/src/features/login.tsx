import { useState, type FormEvent, type KeyboardEvent } from "react";
import { ArrowRight, Eye, EyeOff, Moon, Sun } from "lucide-react";
import { useApp } from "../stores/app";
import { ApiError, auth } from "../lib/api";
import "./login.css";
import { LongExposure } from "./LongExposure";

function Plate() {
  return (
    <aside className="lg-plate">
      {/* live long exposure of the reference gearbox planets; still: scripts/make_signin_art.py */}
      <LongExposure className="lg-photo" />
      <div className="lg-plate-top">
        <a className="lg-brand" href="#/" style={{ color: "inherit", textDecoration: "none" }}><i className="mark" />MotionProof</a>
      </div>
      <div className="lg-plate-body">
        <h2 className="lg-claim">Tolerances in.<br />Motion out.</h2>
        <p className="lg-sub">MotionProof turns a CAD assembly and its tolerance specification into virtual
          as-manufactured copies, simulates each one and reports which fail, how often and why.</p>
      </div>
    </aside>
  );
}

export function LoginScreen() {
  const login = useApp((s) => s.login);
  const theme = useApp((s) => s.theme);
  const toggleTheme = useApp((s) => s.toggleTheme);
  const [mode, setMode] = useState<"signin" | "register">("signin");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [caps, setCaps] = useState(false);
  const [err, setErr] = useState<{ email?: string; password?: string; form?: string }>({});
  const register = mode === "register";

  async function submit(e: FormEvent) {
    e.preventDefault();
    const next: typeof err = {};
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) next.email = "Enter an email address, like name@lab.org.";
    if (register && password.length < 8) next.password = "Use at least 8 characters.";
    else if (password.length < 1) next.password = "Enter your password.";
    setErr(next);
    if (next.email || next.password) return;
    setBusy(true);
    try {
      const { user } = register
        ? await auth.register(email.trim(), password, name.trim())
        : await auth.login(email.trim(), password);
      login(user.email);
    } catch (x) {
      setErr({ form: x instanceof ApiError && x.status === 0 ? x.message : (x as Error).message.replace(/^./, (c) => c.toUpperCase()) + "." });
      setBusy(false);
    }
  }

  function switchMode() {
    setMode(register ? "signin" : "register");
    setErr({});
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
          <h1>{register ? "Create an account" : "Sign in"}</h1>
          <p className="lg-lede">{register
            ? "Accounts are kept by this MotionProof server. Passwords are stored only as salted hashes."
            : "Open your workspace and pick up where the last run stopped."}</p>

          {err.form && <p className="lg-err lg-form-err" role="alert">{err.form}</p>}

          {register && (
            <label className="lg-f">
              <span>Name <em className="lg-opt">optional</em></span>
              <input className="input" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Ada Lovelace" />
            </label>
          )}

          <label className="lg-f">
            <span>Email</span>
            <input className="input" type="email" autoComplete="username" inputMode="email" value={email} autoFocus
              onChange={(e) => setEmail(e.target.value)} aria-invalid={!!err.email} aria-describedby={err.email ? "lg-e1" : undefined} placeholder="name@lab.org" />
            {err.email && <em id="lg-e1" className="lg-err">{err.email}</em>}
          </label>

          <label className="lg-f">
            <span>Password{register && <em className="lg-opt">at least 8 characters</em>}</span>
            <div className="lg-pw">
              <input className="input" type={show ? "text" : "password"} autoComplete={register ? "new-password" : "current-password"} value={password}
                onChange={(e) => setPassword(e.target.value)} onKeyUp={(e: KeyboardEvent) => setCaps(e.getModifierState("CapsLock"))} onBlur={() => setCaps(false)} aria-invalid={!!err.password} aria-describedby={err.password ? "lg-e2" : undefined} />
              <button type="button" className="btn ghost" onClick={() => setShow(!show)} aria-label={show ? "Hide password" : "Show password"} aria-pressed={show}>
                {show ? <EyeOff /> : <Eye />}
              </button>
            </div>
            {caps && <em className="lg-caps" role="status">Caps Lock is on.</em>}
            {err.password && <em id="lg-e2" className="lg-err">{err.password}</em>}
          </label>

          <button className="btn primary lg-go" type="submit" disabled={busy}>
            {busy ? (register ? "Creating account…" : "Signing in…") : <>{register ? "Create account" : "Sign in"} <ArrowRight /></>}
          </button>

          <p className="lg-note">
            {register ? "Already have an account? " : "New to this server? "}
            <button type="button" className="lg-link" onClick={switchMode}>{register ? "Sign in" : "Create an account"}</button>
          </p>
        </form>
        <footer className="lg-foot"><span>MotionProof</span><span>Evidence for mechanical motion</span></footer>
      </main>
    </div>
  );
}
