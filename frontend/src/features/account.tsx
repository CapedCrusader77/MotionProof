// Account settings: change the password, delete the account, and for the administrator (the
// first account) the list of accounts with password reset and deletion.
import { useEffect, useState, type FormEvent } from "react";
import { api, auth, type User } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import { useApp } from "../stores/app";
import { Alert, Load } from "../components/ui";

const MIN = 8;

function ChangePassword() {
  const notify = useApp((s) => s.notify);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (next.length < MIN) return setErr(`The new password needs at least ${MIN} characters.`);
    if (next !== again) return setErr("The two new passwords are not the same.");
    setBusy(true); setErr(null);
    try {
      await auth.changePassword(current, next);
      setCurrent(""); setNext(""); setAgain("");
      notify("ok", "Password changed. Other sessions of this account are signed out.");
    } catch (x) { setErr((x as Error).message); } finally { setBusy(false); }
  }
  return (
    <form className="acct-form" onSubmit={submit}>
      <label><span>Current password</span><input className="input" type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} /></label>
      <label><span>New password</span><input className="input" type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} /></label>
      <label><span>New password again</span><input className="input" type="password" autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} /></label>
      {err && <p className="neg small" role="alert">{err}</p>}
      <div><button className="btn primary" disabled={busy || !current || !next}>{busy ? "Changing…" : "Change password"}</button></div>
    </form>
  );
}

function DeleteAccount({ user }: { user: User }) {
  const logout = useApp((s) => s.logout);
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  async function submit(e: FormEvent) {
    e.preventDefault();
    try { await auth.deleteAccount(password); logout(); } catch (x) { setErr((x as Error).message); }
  }
  if (!open) return <button className="btn" onClick={() => setOpen(true)}>Delete this account…</button>;
  return (
    <form className="acct-form" onSubmit={submit}>
      <Alert kind="warn">Deletes the account {user.email} and signs it out. Its projects stay on disk in the workspace folder but no account can open them.</Alert>
      <label><span>Password</span><input className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} autoFocus /></label>
      {err && <p className="neg small" role="alert">{err}</p>}
      <div className="row"><button className="btn danger" disabled={!password}>Delete account</button><button type="button" className="btn ghost" onClick={() => setOpen(false)}>Cancel</button></div>
    </form>
  );
}

function AddAccount({ onAdded }: { onAdded: () => void }) {
  const notify = useApp((s) => s.notify);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await auth.createUser(email.trim(), password, name.trim());
      notify("ok", `Account created for ${email.trim()}. Tell them the password; they can change it under Settings.`);
      setEmail(""); setName(""); setPassword(""); onAdded();
    } catch (x) { notify("error", (x as Error).message); } finally { setBusy(false); }
  }
  return (
    <form className="st-inline acct-add" onSubmit={submit}>
      <input className="input" type="email" placeholder="Email" aria-label="New account email" value={email} onChange={(e) => setEmail(e.target.value)} />
      <input className="input" placeholder="Name (optional)" aria-label="New account name" value={name} onChange={(e) => setName(e.target.value)} />
      <input className="input" type="password" autoComplete="new-password" placeholder={`Password, ${MIN}+ characters`} aria-label="New account password" value={password} onChange={(e) => setPassword(e.target.value)} />
      <button className="btn" disabled={busy || !email || password.length < MIN}>Add account</button>
    </form>
  );
}

function Accounts({ me }: { me: User }) {
  const notify = useApp((s) => s.notify);
  const list = useAsync(() => auth.users(), []);
  async function reset(u: User) {
    const next = window.prompt(`New password for ${u.email} (at least ${MIN} characters):`);
    if (!next) return;
    try { await auth.resetPassword(u.id, next); notify("ok", `Password set for ${u.email}; their sessions are signed out.`); }
    catch (x) { notify("error", (x as Error).message); }
  }
  async function remove(u: User) {
    if (!window.confirm(`Delete the account ${u.email}? Its projects stay on disk but no account can open them.`)) return;
    try { await auth.deleteUser(u.id); notify("ok", `Deleted ${u.email}`); list.reload(); }
    catch (x) { notify("error", (x as Error).message); }
  }
  return (<>
    <AddAccount onAdded={list.reload} />
    <Load state={list}>{(users) => (
      <table className="grid">
        <thead><tr><th>Email</th><th>Name</th><th>Role</th><th>Created</th><th /></tr></thead>
        <tbody>{users.map((u) => (
          <tr key={u.id}>
            <td>{u.email}</td><td>{u.name}</td><td>{u.admin ? "Administrator" : "Member"}</td>
            <td className="mono">{new Date(u.created * 1000).toISOString().slice(0, 10)}</td>
            <td className="acct-actions">{u.id !== me.id && <>
              <button className="btn ghost" onClick={() => reset(u)}>Set password</button>
              <button className="btn ghost" onClick={() => remove(u)}>Delete</button></>}</td>
          </tr>))}</tbody>
      </table>)}</Load>
  </>);
}

// ---------------------------------------------------------------------------------- settings page

const SECTIONS = [
  ["account", "Account"], ["security", "Security"], ["appearance", "Appearance"], ["workspace", "Workspace"],
  ["system", "System"], ["admin", "Administration"], ["danger", "Danger zone"],
] as const;

function Row(props: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="st-row">
      <div className="st-label"><span>{props.label}</span>{props.hint && <small>{props.hint}</small>}</div>
      <div className="st-value">{props.children}</div>
    </div>
  );
}

function Section(props: { id: string; title: string; children: React.ReactNode; tone?: "danger" }) {
  return (
    <section id={`st-${props.id}`} className={`st-sec ${props.tone ?? ""}`} aria-labelledby={`st-h-${props.id}`}>
      <h2 id={`st-h-${props.id}`}>{props.title}</h2>
      {props.children}
    </section>
  );
}

function NameEditor({ name, onSaved }: { name: string; onSaved: () => void }) {
  const notify = useApp((s) => s.notify);
  const [v, setV] = useState(name);
  const dirty = v.trim() !== name && v.trim().length > 0;
  return (
    <form className="st-inline" onSubmit={async (e) => { e.preventDefault(); try { await auth.rename(v.trim()); notify("ok", "Name saved"); onSaved(); } catch (x) { notify("error", (x as Error).message); } }}>
      <input className="input" value={v} onChange={(e) => setV(e.target.value)} aria-label="Name" maxLength={120} />
      <button className="btn" disabled={!dirty}>Save</button>
    </form>
  );
}

export function SettingsPage() {
  const s = useApp();
  const acct = useAsync(() => auth.account(), []);
  const sys = useAsync(() => api.health(), []);
  const projects = useAsync(() => api.projects(), []);
  const [active, setActive] = useState("account");
  const count = (k: "models" | "experiments") => (projects.data ?? []).reduce((n, p) => n + (typeof p[k] === "number" ? (p[k] as number) : Array.isArray(p[k]) ? (p[k] as unknown[]).length : 0), 0);

  useEffect(() => {
    const els = SECTIONS.map(([id]) => document.getElementById(`st-${id}`)).filter(Boolean) as HTMLElement[];
    const io = new IntersectionObserver((es) => { const v = es.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0]; if (v) setActive(v.target.id.slice(3)); },
      { rootMargin: "-20% 0px -60% 0px" });
    els.forEach((e) => io.observe(e));
    return () => io.disconnect();
  }, [acct.data]);

  const user = acct.data;
  const jump = (id: string) => document.getElementById(`st-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });

  async function endOthers() {
    try { const r = await auth.endOtherSessions(); s.notify("ok", r.ended ? `Signed out ${r.ended} other session${r.ended > 1 ? "s" : ""}` : "No other sessions"); acct.reload(); }
    catch (x) { s.notify("error", (x as Error).message); }
  }

  return (
    <div className="page st">
      <div className="page-head"><h1>Settings</h1>{user && <span className="sub">{user.email}</span>}</div>
      <div className="st-layout">
        <nav className="st-index" aria-label="Settings sections">
          {SECTIONS.filter(([id]) => id !== "admin" || user?.admin).map(([id, label], n) => (
            <button key={id} className={active === id ? "on" : ""} onClick={() => jump(id)} aria-current={active === id}>
              <i>{String(n + 1).padStart(2, "0")}</i>{label}</button>))}
        </nav>
        <div className="st-body">
          <Section id="account" title="Account">
            {!user ? <p className="muted small">Loading…</p> : <>
              <Row label="Email"><span className="mono">{user.email}</span></Row>
              <Row label="Name" hint="Shown in the top bar and in the account list."><NameEditor name={user.name} onSaved={acct.reload} /></Row>
              <Row label="Role"><span>{user.admin ? "Administrator" : "Member"}</span></Row>
            </>}
          </Section>

          <Section id="security" title="Security">
            <Row label="Password" hint="Changing it signs out your other sessions."><ChangePassword /></Row>
            <Row label="Sessions" hint="Each browser that is signed in. Sessions last 14 days.">
              <div className="st-inline"><span>{user ? `${user.sessions} active` : "…"}</span>
                <button className="btn" onClick={endOthers} disabled={!user || user.sessions < 2}>Sign out other sessions</button></div>
            </Row>
          </Section>

          <Section id="appearance" title="Appearance">
            <Row label="Theme" hint="The sign-in page is always dark.">
              <div className="st-seg" role="radiogroup" aria-label="Theme">
                {(["dark", "light"] as const).map((t) => <button key={t} role="radio" aria-checked={s.theme === t} className={s.theme === t ? "on" : ""} onClick={() => s.theme !== t && s.toggleTheme()}>{t === "dark" ? "Dark" : "Light"}</button>)}
              </div>
            </Row>
            <Row label="Navigation" hint="Collapse the side navigation to icons.">
              <div className="st-seg" role="radiogroup" aria-label="Navigation width">
                {([false, true] as const).map((c) => <button key={String(c)} role="radio" aria-checked={s.navCollapsed === c} className={s.navCollapsed === c ? "on" : ""} onClick={() => s.navCollapsed !== c && s.toggleNav()}>{c ? "Icons" : "Full"}</button>)}
              </div>
            </Row>
          </Section>

          <Section id="workspace" title="Workspace">
            <div className="st-stats">
              <div><b>{projects.data ? projects.data.length : "…"}</b><span>projects</span></div>
              <div><b>{projects.data ? count("models") : "…"}</b><span>models</span></div>
              <div><b>{projects.data ? count("experiments") : "…"}</b><span>experiments</span></div>
              <div><b>{sys.data ? sys.data.active_jobs : "…"}</b><span>jobs running</span></div>
            </div>
            <Row label="Folder" hint="Only your account can see this workspace."><span className="mono st-path">{sys.data?.workspace ?? "…"}</span></Row>
          </Section>

          <Section id="system" title="System">
            <Row label="Backend"><span>{sys.error ? <span className="neg">{sys.error}</span> : sys.data ? "running" : "…"}</span></Row>
            {sys.data && Object.entries(sys.data.versions).map(([k, v]) => <Row key={k} label={k}><span className="mono">{v}</span></Row>)}
            <Row label="Optional AI" hint="Local Ollama by default. For a cloud provider the server needs MOTIONPROOF_AI_PROVIDER (anthropic or openai), MOTIONPROOF_AI_KEY and, for openai, MOTIONPROOF_AI_MODEL; the key stays on the server. Disable with MOTIONPROOF_AI=off.">
              {!sys.data ? <span>…</span> : !sys.data.ai.available ? <span>Off: {sys.data.ai.reason}</span>
                : sys.data.ai.cloud ? <span>Cloud ({sys.data.ai.provider}, {sys.data.ai.model}). Questions and result summaries are sent to <span className="mono">{sys.data.ai.host}</span>. {sys.data.ai.used_today ?? 0} of {sys.data.ai.daily_limit} questions used today.</span>
                : <span>Local ({sys.data.ai.model}). Nothing leaves this machine.</span>}</Row>
            <Row label="Execution" hint="Set MOTIONPROOF_WORKERS to change the number of worker processes.">
              <span>Runs of 100 scenarios or more use several worker processes; results are identical to a one-process run. Interrupted runs resume.</span></Row>
            <Row label="Scope of results"><span className="muted">Model predictions conditional on the supplied geometry, tolerances and drive-train values. Not a certification of strength, fatigue life, thermal behaviour or real-world reliability.</span></Row>
          </Section>

          {user?.admin && <Section id="admin" title="Administration"><Accounts me={user} /></Section>}

          <Section id="danger" title="Danger zone" tone="danger">
            {user && <Row label="Delete account" hint="Your projects stay on disk, but no account can open them."><DeleteAccount user={user} /></Row>}
          </Section>
        </div>
      </div>
    </div>
  );
}
