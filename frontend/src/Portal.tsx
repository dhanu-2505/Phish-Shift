import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import { Layout } from "./components/Layout";
import { PublicLayout } from "./components/PublicLayout";
import { About } from "./pages/About";
import { Account } from "./pages/Account";
import { Analytics } from "./pages/Analytics";
import { Dashboard } from "./pages/Dashboard";
import { History } from "./pages/History";
import { Login } from "./pages/Login";
import { NotFound } from "./pages/NotFound";
import { Register } from "./pages/Register";
import { Scan } from "./pages/Scan";
import { ScanDetails } from "./pages/ScanDetails";

function RequireAuth() {
  const { state, refresh } = useAuth();
  if (state.status === "loading") {
    return <div className="auth-loading"><span className="loader" />Checking your session…</div>;
  }
  if (state.status === "error") {
    return (
      <div className="auth-loading auth-loading-error" role="alert">
        <strong>Could not verify your session</strong>
        <span>{state.error}</span>
        <button className="button button-secondary" onClick={() => void refresh()}>Retry</button>
      </div>
    );
  }
  if (state.status !== "authenticated") return <Navigate to="/login" replace />;
  return <Outlet />;
}

export default function Portal() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<PublicLayout />}>
            <Route index element={<About />} />
            <Route path="about" element={<About />} />
          </Route>
          <Route path="register" element={<Register />} />
          <Route path="login" element={<Login />} />
          <Route element={<RequireAuth />}>
            <Route element={<Layout />}>
              <Route path="dashboard" element={<Dashboard />} />
              <Route path="scan" element={<Scan />} />
              <Route path="history" element={<History />} />
              <Route path="scans/:scanId" element={<ScanDetails />} />
              <Route path="analytics" element={<Analytics />} />
              <Route path="account" element={<Account />} />
            </Route>
          </Route>
          <Route path="not-found" element={<NotFound />} />
          <Route path="*" element={<Navigate to="/not-found" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
