import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { ApiError, registerAccount } from "../api";
import { useAuth } from "../auth";

export function Register() {
  const { state, setUser } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  if (state.status === "authenticated" && !success) return <Navigate to="/dashboard" replace />;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (password.length < 12 || password.length > 128) {
      setError("Use a password between 12 and 128 characters.");
      return;
    }
    if (password !== confirmPassword) {
      setError("The password and confirmation do not match.");
      return;
    }
    setLoading(true);
    try {
      const result = await registerAccount({
        name: name.trim(),
        email: email.trim(),
        password,
        confirm_password: confirmPassword,
      });
      setUser(result.user);
      setPassword("");
      setConfirmPassword("");
      setSuccess(true);
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? cause.message
          : cause instanceof Error ? cause.message : "Account creation failed. Please retry.",
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
        {success ? (
          <div className="auth-success" role="status">
            <span className="auth-success-icon">✓</span>
            <h1>Account created</h1>
            <p>Your account is ready. You can now open your private PhishShift workspace.</p>
            <button className="button button-primary auth-submit" onClick={() => navigate("/dashboard", { replace: true })}>
              Continue to dashboard <span>↗</span>
            </button>
          </div>
        ) : (
          <>
            <div className="auth-heading">
              <div className="overline">CREATE YOUR WORKSPACE</div>
              <h1>Create an account</h1>
              <p>Set up your private message-risk scanning workspace.</p>
            </div>
            <form className="auth-form" onSubmit={(event) => void submit(event)}>
              <label className="auth-field">Name
                <input autoComplete="name" maxLength={100} required value={name} onChange={(event) => setName(event.target.value)} />
              </label>
              <label className="auth-field">Email
                <input type="email" autoComplete="email" maxLength={254} required value={email} onChange={(event) => setEmail(event.target.value)} />
              </label>
              <label className="auth-field">Password <span>At least 12 characters</span>
                <input type="password" autoComplete="new-password" minLength={12} maxLength={128} required value={password} onChange={(event) => setPassword(event.target.value)} />
              </label>
              <label className="auth-field">Confirm password
                <input type="password" autoComplete="new-password" minLength={12} maxLength={128} required value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} />
              </label>
              {error && <div className="auth-error" role="alert">{error}</div>}
              <button className="button button-primary auth-submit" type="submit" disabled={loading}>
                {loading ? <><span className="loader light" /> Creating account…</> : <>Create account <span>↗</span></>}
              </button>
            </form>
            <p className="auth-switch">Already have an account? <Link to="/login">Login</Link></p>
            <p className="auth-privacy">Passwords are securely hashed and never returned by the API.</p>
          </>
        )}
      </section>
      <Link className="auth-back" to="/">← Back to PhishShift</Link>
    </main>
  );
}
