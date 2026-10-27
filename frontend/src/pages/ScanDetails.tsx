import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, getScanDetails, type ScanDetails as ScanRecord } from "../api";
import { formatDate, ResultBadge } from "./Dashboard";

export function ScanDetails() {
  const { scanId } = useParams();
  const id = Number(scanId);
  const [record, setRecord] = useState<ScanRecord | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    if (!Number.isSafeInteger(id) || id <= 0) {
      setError("The scan ID is invalid.");
      setLoading(false);
      return () => { active = false; };
    }
    void getScanDetails(id).then((value) => { if (active) setRecord(value); })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof ApiError && cause.status === 404 ? "This scan does not exist or is no longer available." : cause instanceof Error ? cause.message : "Scan details could not be loaded.");
      }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [id]);

  return <>
    <div className="page-heading"><div><div className="overline">SCAN RECORD <span className="overline-line" /></div><h1>Scan details</h1><p>Review the saved model output for this scan.</p></div><Link className="button button-secondary" to="/history">← Back to history</Link></div>
    <section className="panel detail-panel">
      {loading ? <div className="state-box"><span className="loader" />Loading saved scan…</div>
        : error ? <div className="state-box error-state"><strong>Scan details unavailable</strong><span>{error}</span><Link to="/history">Return to scan history →</Link></div>
          : record ? <><div className="detail-header"><div><span className="overline">SCAN #{record.scan_id.toString().padStart(5, "0")}</span><h2>Prediction result</h2></div><div className="detail-badges"><ResultBadge label={record.predicted_label} /><span className={`scan-kind-badge scan-kind-${record.record_kind}`}>{record.record_kind === "user" ? "User scan" : record.record_kind === "verification" ? "Verification" : record.record_kind === "demo" ? "Demo" : "Legacy record"}</span></div></div><div className="detail-grid"><div><span className="detail-label">PREDICTED LABEL</span><strong>{record.predicted_label}</strong></div><div><span className="detail-label">PHISHING RISK SCORE</span><strong className={record.risk_score >= 0.5 ? "text-danger" : "text-good"}>{(record.risk_score * 100).toFixed(2)}%</strong></div><div><span className="detail-label">CREATED</span><strong>{formatDate(record.created_at)}</strong></div></div><div className="detail-explanation"><span className="detail-label">MODEL EXPLANATION</span><p>{record.explanation}</p></div><p className="privacy-inline"><span>⌑</span> Original message text is not returned by the scan details API.</p></> : null}
    </section>
  </>;
}
