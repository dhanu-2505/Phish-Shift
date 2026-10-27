import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getDashboardSummary, getEvaluation, type DashboardSummary, type Evaluation } from "../api";
import { useSystemHealth } from "./hooks";

export function Dashboard() {
  const [history, setHistory] = useState<DashboardSummary | null>(null);
  const [historyError, setHistoryError] = useState("");
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [evaluationError, setEvaluationError] = useState("");
  const { health } = useSystemHealth();

  useEffect(() => {
    let active = true;
    void getDashboardSummary()
      .then((result) => { if (active) setHistory(result); })
      .catch((error: unknown) => {
        if (active) setHistoryError(error instanceof Error ? error.message : "Could not load scans.");
      });
    void getEvaluation()
      .then((result) => { if (active) setEvaluation(result); })
      .catch((error: unknown) => {
        if (active) setEvaluationError(error instanceof Error ? error.message : "Could not load evaluation.");
      });
    return () => { active = false; };
  }, []);

  const allUp = health?.database.ok && health.model.ok;
  const matrix = evaluation?.confusion_matrix;
  const matrixMax = matrix ? Math.max(1, ...matrix.flat()) : 1;

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="overline">SECURITY OVERVIEW <span className="overline-line" /></div>
          <h1>Good to see you.</h1>
          <p>Your message security workspace at a glance.</p>
        </div>
        <Link className="button button-primary" to="/scan"><span>⌕</span> New scan <b>↗</b></Link>
      </div>

      <section className="metric-grid" aria-label="Dashboard summary">
        <article className="metric-card">
          <div className="metric-top"><span>Total scans</span><span className="metric-icon purple">◷</span></div>
          <strong>{history ? history.total_scans.toLocaleString() : "—"}</strong>
          <small>{history ? "Your saved scans" : historyError || "Loading scan history…"}</small>
        </article>
        <article className="metric-card">
          <div className="metric-top"><span>Model F1-score</span><span className="metric-icon blue">⌁</span></div>
          <strong>{evaluation ? `${(evaluation.f1_score * 100).toFixed(1)}%` : "—"}</strong>
          <small>{evaluation ? "Held-out evaluation · not a guarantee" : evaluationError || "Loading evaluation…"}</small>
        </article>
        <article className="metric-card">
          <div className="metric-top"><span>Database</span><span className="metric-icon green">◉</span></div>
          <strong className={`metric-status ${health?.database.ok ? "status-good" : ""}`}>{health?.database.ok ? "Connected" : health ? "Unavailable" : "Checking"}</strong>
          <small>{health?.database.detail ?? "Checking database health…"}</small>
          <div className="metric-footer"><span className={health?.database.ok ? "mini-dot good" : "mini-dot"} /> Live health check</div>
        </article>
        <article className="metric-card">
          <div className="metric-top"><span>Risk model</span><span className="metric-icon violet">✳</span></div>
          <strong className={`metric-status ${health?.model.ok ? "status-good" : ""}`}>{health?.model.ok ? "Online" : health ? "Unavailable" : "Checking"}</strong>
          <small>{health?.model.detail ?? "Checking model health…"}</small>
          <div className="metric-footer"><span className={health?.model.ok ? "mini-dot good" : "mini-dot"} /> Live health check</div>
        </article>
      </section>

      <section className="panel risk-distribution">
        <div className="panel-heading">
          <div><h2>Your scan distribution</h2><p>Predicted classes from your saved scan history</p></div>
          <Link className="text-link" to="/history">Filter history <span>→</span></Link>
        </div>
        {history ? (
          <div className="distribution-grid">
            <DistributionBar label="Classified safe" count={history.safe_scans} total={history.total_scans} kind="safe" />
            <DistributionBar label="Potential phishing" count={history.phishing_scans} total={history.total_scans} kind="phishing" />
          </div>
        ) : historyError ? (
          <div className="distribution-empty error-state">{historyError}</div>
        ) : (
          <div className="distribution-empty"><span className="loader" />Loading scan distribution…</div>
        )}
      </section>

      <section className="dashboard-grid">
        <article className="panel recent-panel">
          <div className="panel-heading">
            <div><h2>Recent activity</h2><p>Latest saved scan results</p></div>
            <Link className="text-link" to="/history">View all <span>→</span></Link>
          </div>
          {historyError ? (
            <div className="state-box error-state"><strong>Scan history unavailable</strong><span>{historyError}</span><button className="text-button" onClick={() => window.location.reload()}>Retry</button></div>
          ) : !history ? (
            <div className="state-box"><span className="loader" />Loading recent scans…</div>
          ) : history.recent_scans.length === 0 ? (
            <div className="state-box empty-state"><span className="empty-symbol">◷</span><strong>No scans yet</strong><span>Predictions you run will appear here.</span><Link to="/scan">Run your first scan →</Link></div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead><tr><th>SCAN</th><th>RESULT</th><th>RISK</th><th>TYPE</th><th>DATE</th><th /></tr></thead>
                <tbody>
                  {history.recent_scans.map((scan) => (
                    <tr key={scan.scan_id}>
                      <td className="scan-id">#{scan.scan_id.toString().padStart(5, "0")}</td>
                      <td><ResultBadge label={scan.predicted_label} /></td>
                      <td><RiskValue score={scan.risk_score} /></td>
                      <td><span className={`scan-kind-badge scan-kind-${scan.record_kind}`}>{scan.record_kind === "user" ? "User scan" : scan.record_kind === "verification" ? "Verification" : scan.record_kind === "demo" ? "Demo" : "Legacy record"}</span></td>
                      <td className="date-cell">{formatDate(scan.created_at)}</td>
                      <td><Link className="row-link" to={`/scans/${scan.scan_id}`} aria-label={`View scan ${scan.scan_id}`}>↗</Link></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </article>

        <article className="panel matrix-panel">
          <div className="panel-heading">
            <div><h2>Model snapshot</h2><p>Held-out evaluation</p></div>
            <Link className="icon-link" to="/analytics" aria-label="Open model analytics">↗</Link>
          </div>
          {evaluation && matrix ? (
            <>
              <div className="matrix-summary"><span className="matrix-legend"><i className="legend-true" /> Correct</span><span className="matrix-legend"><i className="legend-false" /> Incorrect</span></div>
              <div className="confusion-chart" role="img" aria-label="Confusion matrix values from held-out model evaluation">
                {matrix.map((row, rowIndex) => row.map((value, columnIndex) => {
                  const correct = rowIndex === columnIndex;
                  return <div className={`matrix-cell ${correct ? "correct" : "incorrect"}`} key={`${rowIndex}-${columnIndex}`}>
                    <div className="matrix-bar"><span style={{ width: `${Math.max(3, (value / matrixMax) * 100)}%` }} /></div>
                    <strong>{value.toLocaleString()}</strong>
                    <small>{evaluation.confusion_matrix_labels[rowIndex]} → {evaluation.confusion_matrix_labels[columnIndex]}</small>
                  </div>;
                }))}
              </div>
              <div className="matrix-foot"><span>Test set: {evaluation.test_rows.toLocaleString()} messages</span><Link to="/analytics">Full analysis →</Link></div>
            </>
          ) : evaluationError ? (
            <div className="state-box error-state"><strong>Evaluation unavailable</strong><span>{evaluationError}</span></div>
          ) : <div className="state-box"><span className="loader" />Loading measured evaluation…</div>}
        </article>
      </section>

      <section className={`system-banner ${allUp ? "healthy" : "warning"}`}>
        <span className="system-banner-icon">{allUp ? "✓" : "!"}</span>
        <div><strong>{allUp ? "Your workspace is ready" : "Check service status"}</strong><span>{allUp ? "Database and trained model health checks are responding." : "One or more backend health checks are unavailable. Scan features may be affected."}</span></div>
        <Link to="/about">System info <span>↗</span></Link>
      </section>
    </>
  );
}

function DistributionBar({
  label,
  count,
  total,
  kind,
}: {
  label: string;
  count: number;
  total: number;
  kind: "safe" | "phishing";
}) {
  const percentage = total === 0 ? 0 : (count / total) * 100;
  return (
    <div className={`distribution-item ${kind}`}>
      <div className="distribution-label"><span>{label}</span><strong>{count.toLocaleString()} <small>({percentage.toFixed(1)}%)</small></strong></div>
      <div className="distribution-track" role="img" aria-label={`${label}: ${count} of ${total} scans`}>
        <span style={{ width: `${percentage}%` }} />
      </div>
    </div>
  );
}

export function ResultBadge({ label }: { label: string }) {
  const phishing = label === "Phishing Email";
  return <span className={`result-badge ${phishing ? "badge-phishing" : "badge-safe"}`}><i />{phishing ? "Phishing" : "Safe"}</span>;
}

export function RiskValue({ score }: { score: number }) {
  return <span className={`risk-value ${score >= 0.5 ? "risk-high" : "risk-low"}`}>{(score * 100).toFixed(1)}%</span>;
}

export function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}
