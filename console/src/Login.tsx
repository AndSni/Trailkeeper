import { useState } from "react";
import { login } from "./api";

export function Login({ onDone }: { onDone: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await login(email, password);
      onDone();
    } catch {
      setErr("Invalid email or password");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <h1>Trailkeeper Console</h1>
      <div className="card">
        <h2>Sign in</h2>
        {err && <div className="err">{err}</div>}
        <form onSubmit={submit}>
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          <button style={{ marginTop: 16 }} disabled={busy} type="submit">
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
      <p style={{ color: "var(--muted)" }}>
        No account? Use the <a href="/register">registration page</a>.
      </p>
    </div>
  );
}
