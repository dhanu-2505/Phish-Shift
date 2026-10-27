import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, getScanHistory, type ScanPage } from "../api";
import { formatDate, ResultBadge, RiskValue } from "./Dashboard";

export function History() {
  const [page, setPage] = useState(1);
  const [data, setData] = useState<ScanPage | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [label, setLabel] = useState<"" | "Safe Email" | "Phishing Email">("");
  const [sortBy, setSortBy] = useState<"created_at" | "risk_score">("created_at");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try { setData(await getScanHistory(page, 10, label || undefined, sortBy, sortOrder)); }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : "Scan history could not be loaded."); }
    finally { setLoading(false); }
  }, [page, label, sortBy, sortOrder]);

  useEffect(() => { void load(); }, [load]);

  return (
    <>
      <div className="page-heading"><div><div className="overline">YOUR ACTIVITY <span className="overline-line" /></div><h1>Scan history</h1><p>Recent prediction records saved by the local backend.</p></div><Link className="button button-primary" to="/scan">New scan <b>↗</b></Link></div>
      <section className="panel history-panel">
        <div className="panel-heading"><div><h2>All scans</h2><p>{data ? `${data.total.toLocaleString()} saved ${data.total === 1 ? "scan" : "scans"}` : "Database-backed scan records"}</p></div><button className="button button-secondary button-small" onClick={() => void load()} disabled={loading}>↻ Refresh</button></div>
        <p className="privacy-inline"><span>⌑</span> Message content is excluded from this list and API response.</p>
        <div className="history-controls" aria-label="Filter and sort scans">
          <label>Prediction
            <select value={label} onChange={(event) => {
              const value = event.target.value;
              if (value === "" || value === "Safe Email" || value === "Phishing Email") {
                setLabel(value);
                setPage(1);
              }
            }}>
              <option value="">All predictions</option>
              <option value="Phishing Email">Potential phishing</option>
              <option value="Safe Email">Classified safe</option>
            </select>
          </label>
          <label>Sort by
            <select value={sortBy} onChange={(event) => {
              const value = event.target.value;
              if (value === "created_at" || value === "risk_score") {
                setSortBy(value);
                setPage(1);
              }
            }}>
              <option value="created_at">Scan date</option>
              <option value="risk_score">Risk score</option>
            </select>
          </label>
          <label>Order
            <select value={sortOrder} onChange={(event) => {
              const value = event.target.value;
              if (value === "asc" || value === "desc") {
                setSortOrder(value);
                setPage(1);
              }
            }}>
              <option value="desc">Newest / highest first</option>
              <option value="asc">Oldest / lowest first</option>
            </select>
          </label>
        </div>
        {loading ? <div className="state-box"><span className="loader" />Loading scan records…</div>
          : error ? <div className="state-box error-state"><strong>History unavailable</strong><span>{error}</span><button className="button button-secondary button-small" onClick={() => void load()}>Retry</button></div>
            : !data || data.items.length === 0 ? <div className="state-box empty-state"><span className="empty-symbol">◷</span><strong>No saved scans</strong><span>Run a message scan and its result will appear here.</span><Link to="/scan">Start a scan →</Link></div>
              : <><div className="table-wrap history-table-wrap"><table><thead><tr><th>SCAN ID</th><th>MODEL RESULT</th><th>PHISHING RISK</th><th>TYPE</th><th>CREATED</th><th /></tr></thead><tbody>{data.items.map((item) => <tr key={item.scan_id}><td className="scan-id">#{item.scan_id.toString().padStart(5, "0")}</td><td><ResultBadge label={item.predicted_label} /></td><td><RiskValue score={item.risk_score} /></td><td><RecordKindBadge kind={item.record_kind} /></td><td className="date-cell">{formatDate(item.created_at)}</td><td><Link className="row-link" to={`/scans/${item.scan_id}`} aria-label={`View scan ${item.scan_id}`}>↗</Link></td></tr>)}</tbody></table></div>
                <div className="pagination"><span>Page {data.page} of {Math.max(data.total_pages, 1)}</span><div><button className="button button-secondary button-small" onClick={() => setPage((current) => current - 1)} disabled={data.page <= 1 || loading}>← Previous</button><button className="button button-secondary button-small" onClick={() => setPage((current) => current + 1)} disabled={data.page >= data.total_pages || loading}>Next →</button></div></div></>}
      </section>
    </>
  );
}

function RecordKindBadge({ kind }: { kind: "user" | "verification" | "demo" | "legacy" }) {
  const labels = {
    user: "User scan",
    verification: "Verification",
    demo: "Demo",
    legacy: "Legacy record",
  };
  return <span className={`scan-kind-badge scan-kind-${kind}`}>{labels[kind]}</span>;
}
