import { Link, Outlet } from "react-router-dom";
import { useAuth } from "../auth";

export function PublicLayout() {
  const { state } = useAuth();
  const signedIn = state.status === "authenticated";

  return (
    <div className="public-shell">
      <header className="public-header">
        <Link className="brand" to="/" aria-label="PhishShift home">
          <span className="brand-symbol"><span>p</span></span>
          <span className="brand-copy">phish<span>shift</span><small>MESSAGE SECURITY</small></span>
        </Link>
        <nav aria-label="Public navigation">
          <Link to="/about">About</Link>
          {signedIn ? (
            <Link className="button button-primary" to="/dashboard">Open dashboard <span>↗</span></Link>
          ) : (
            <>
              <Link to="/login">Login</Link>
              <Link className="button button-primary" to="/register">Create account <span>↗</span></Link>
            </>
          )}
        </nav>
      </header>
      <main className="public-content"><Outlet /></main>
      <footer className="public-footer">
        <span>PhishShift · Message Risk Scanner</span>
        <span>Model output is an advisory signal, not a guarantee.</span>
      </footer>
    </div>
  );
}
