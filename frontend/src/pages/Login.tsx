import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { ApiError, loginAccount } from "../api";
import { useAuth } from "../auth";

export function Login() {
  const { state, setUser } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  if (state.status === "authenticated") return <Navigate to="/dashboard" replace />;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      const result = await loginAccount({ email: email.trim(), password });
      setPassword("");
      setUser(result.user);
      navigate("/dashboard", { replace: true });
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? cause.message
          : cause instanceof Error ? cause.message : "Login failed. Please retry.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="panel auth-card">
        <Link className="auth-brand" to="/">
          <span className="brand-symbol"><span>p</span></span>
          <span className="brand-copy">phish<span>shift</span><small>MESSAGE SECURITY</small></span>
        </Link>
        <div className="auth-heading">
          <div className="overline">WELCOME BACK</div>
          <h1>Login to PhishShift</h1>
          <p>Continue to your private scanning workspace.</p>
        </div>
        <form className="auth-form" onSubmit={(event) => void submit(event)}>
          <label className="auth-field">Email
            <input type="email" autoComplete="username" maxLength={254} required value={email} onChange={(event) => setEmail(event.target.value)} />
          </label>
          <label className="auth-field">Password
            <input type="password" autoComplete="current-password" maxLength={128} required value={password} onChange={(event) => setPassword(event.target.value)} />
          </label>
          {error && <div className="auth-error" role="alert">{error}</div>}
          <button className="button button-primary auth-submit" type="submit" disabled={loading}>
            {loading ? <><span className="loader light" /> Signing in…</> : <>Login <span>↗</span></>}
          </button>
        </form>
        <p className="auth-switch">New to PhishShift? <Link to="/register">Create an account</Link></p>
        <p className="auth-privacy">Your session uses a secure HttpOnly cookie. No token is stored in browser storage.</p>
      </section>
      <Link className="auth-back" to="/">← Back to PhishShift</Link>
    </main>
  );
}
