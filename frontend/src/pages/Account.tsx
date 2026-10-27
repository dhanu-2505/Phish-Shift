import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, logoutAccount } from "../api";
import { useAuth } from "../auth";

export function Account() {
  const { state, clearUser } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const user = state.status === "authenticated" ? state.user : null;

  async function logout() {
    setError("");
    setLoading(true);
    try {
      await logoutAccount();
      clearUser();
      navigate("/", { replace: true });
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) {
        clearUser();
        navigate("/", { replace: true });
      } else {
        setError(cause instanceof Error ? cause.message : "Logout could not be completed.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <div className="page-heading">
        <div><div className="overline">PROFILE & SESSION <span className="overline-line" /></div><h1>Account</h1><p>Manage your signed-in PhishShift session.</p></div>
      </div>
      <section className="panel account-panel">
        <div className="account-avatar">{user?.name.slice(0, 2).toUpperCase() ?? "PS"}</div>
        <div className="account-details">
          <div><span className="detail-label">NAME</span><strong>{user?.name}</strong></div>
          <div><span className="detail-label">EMAIL</span><strong>{user?.email}</strong></div>
          <div><span className="detail-label">SESSION</span><strong className="text-good">Authenticated · server-managed</strong></div>
        </div>
        <p className="privacy-inline"><span>⌑</span> Your session token is held in a HttpOnly cookie and is not accessible to page scripts.</p>
        {error && <div className="auth-error" role="alert">{error}</div>}
        <div className="account-actions">
          <button className="button button-secondary" onClick={() => void logout()} disabled={loading}>
            {loading ? "Signing out…" : "Log out"}
          </button>
          <Link className="button button-quiet" to="/dashboard">Back to dashboard</Link>
        </div>
      </section>
    </>
  );
}
