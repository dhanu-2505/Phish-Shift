import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { ApiError, getSystemHealth, logoutAccount, type SystemHealth } from "../api";
import { useAuth } from "../auth";

const navigation = [
  { to: "/dashboard", label: "Dashboard", icon: "⌂", end: true },
  { to: "/scan", label: "Scan Message", icon: "⌕" },
  { to: "/history", label: "Scan History", icon: "◷" },
  { to: "/analytics", label: "Model Analytics", icon: "▥" },
  { to: "/account", label: "Account", icon: "◉" },
];

function HealthIndicator({ health }: { health: SystemHealth | null }) {
  const databaseUp = health?.database.ok ?? false;
  const modelUp = health?.model.ok ?? false;
  const status = health ? (databaseUp && modelUp ? "online" : "degraded") : "checking";
  const label = status === "online" ? "Systems operational" : status === "checking" ? "Checking services" : "Service issue";
  const detail = health
    ? `Database: ${health.database.detail}. Model: ${health.model.detail}.`
    : "Waiting for backend health checks.";

  return (
    <div className={`health-indicator ${status}`} title={detail} aria-live="polite">
      <span className="health-pulse" />
      <span>{label}</span>
    </div>
  );
}

export function Layout() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [logoutError, setLogoutError] = useState("");
  const location = useLocation();
  const navigate = useNavigate();
  const { state, clearUser } = useAuth();
  const user = state.status === "authenticated" ? state.user : null;

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      const result = await getSystemHealth();
      if (active) setHealth(result);
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 30_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [location.pathname]);

  async function signOut() {
    setLogoutError("");
    try {
      await logoutAccount();
      clearUser();
      navigate("/", { replace: true });
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) {
        clearUser();
        navigate("/", { replace: true });
        return;
      }
      setLogoutError(cause instanceof Error ? cause.message : "Logout could not be completed.");
    }
  }

  return (
    <div className="app-frame">
      <aside className="sidebar">
        <NavLink className="brand" to="/" aria-label="PhishShift dashboard">
          <span className="brand-symbol"><span>p</span></span>
          <span className="brand-copy">phish<span>shift</span><small>MESSAGE SECURITY</small></span>
        </NavLink>

        <div className="workspace-label">WORKSPACE</div>
        <nav className="primary-nav" aria-label="Primary navigation">
          {navigation.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              aria-label={item.label}
              className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
            >
              <span className="nav-icon" aria-hidden="true">{item.icon}</span>
              <span>{item.label}</span>
              {item.to === "/scan" && <span className="nav-live">LIVE</span>}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-spacer" />
        <div className="sidebar-security">
          <div className="sidebar-security-icon">✳</div>
          <strong>Stay one step ahead</strong>
          <p>Pause, verify, and think before you click.</p>
          <NavLink to="/about">Safe scanning tips <span aria-hidden="true">↗</span></NavLink>
        </div>
        <div className="sidebar-footer">
          <span className="avatar">{user?.name.slice(0, 2).toUpperCase() ?? "PS"}</span>
          <span className="footer-user">{user?.name ?? "Account"}<small>{user?.email}</small></span>
          <button className="logout-button" type="button" onClick={() => void signOut()} aria-label="Log out" title="Log out">↗</button>
        </div>
      </aside>

      <div className="main-column">
        <header className="topbar">
          <div className="breadcrumbs"><span>PhishShift</span><b>/</b><strong>{navigation.find((item) => item.to === location.pathname)?.label ?? (location.pathname.startsWith("/scans/") ? "Scan Details" : "Workspace")}</strong></div>
          <div className="topbar-actions">
            <span className="environment-badge"><i /> LOCAL ENVIRONMENT</span>
            <HealthIndicator health={health} />
          </div>
        </header>

        <main className="page-content" key={location.pathname}>
          {logoutError && <div className="notice danger-notice logout-error" role="alert"><span>!</span><div><strong>Logout failed</strong><p>{logoutError}</p><button className="text-button" onClick={() => void signOut()}>Retry logout →</button></div></div>}
          <Outlet context={{ health }} />
        </main>

        <footer className="main-footer">
          <span>PhishShift <span className="footer-version">· Message Risk Scanner</span></span>
          <span>Model results are signals, not guarantees.</span>
        </footer>
      </div>

      <nav className="mobile-nav" aria-label="Mobile navigation">
        {navigation.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) => `mobile-nav-link${isActive ? " active" : ""}`}
          >
            <span aria-hidden="true">{item.icon}</span>
            <small>{item.label.replace(" Message", "").replace(" Model", "")}</small>
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
