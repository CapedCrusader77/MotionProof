// Account settings: change the password, delete the account, and for the administrator (the
// first account) the list of accounts with password reset and deletion.
import { useState, type FormEvent } from "react";
import { auth, type User } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import { useApp } from "../stores/app";
import { Alert, Load, Panel } from "../components/ui";

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
  return (
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
  );
}

export function AccountPanels() {
  const me = useAsync(() => auth.me(), []);
  return (
    <Load state={me}>{({ user }) => (<>
      <Panel title="Account">
        <dl className="kv"><dt>Email</dt><dd>{user.email}</dd><dt>Name</dt><dd>{user.name}</dd><dt>Role</dt><dd>{user.admin ? "Administrator" : "Member"}</dd></dl>
        <h3 className="acct-h">Change password</h3>
        <ChangePassword />
        <h3 className="acct-h">Delete account</h3>
        <DeleteAccount user={user} />
      </Panel>
      {user.admin && <Panel title="Accounts on this server"><Accounts me={user} /></Panel>}
    </>)}</Load>
  );
}
