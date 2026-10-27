import { useEffect, useState } from "react";
import { ApiError, getEvaluation, type Evaluation } from "../api";
import { formatDate } from "./Dashboard";

export function Analytics() {
  const [data, setData] = useState<Evaluation | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    void getEvaluation().then((report) => { if (active) setData(report); })
      .catch((cause: unknown) => { if (active) setError(cause instanceof ApiError ? cause.message : "Evaluation report could not be loaded."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  return <>
    <div className="page-heading"><div><div className="overline">MEASURED PERFORMANCE <span className="overline-line" /></div><h1>Model analytics</h1><p>Evaluation results from the saved held-out test report.</p></div><span className="report-badge"><i /> SOURCE: TRAINING REPORT</span></div>
    {loading ? <section className="panel state-box"><span className="loader" />Loading evaluation report…</section>
      : error ? <section className="panel state-box error-state"><strong>Evaluation unavailable</strong><span>{error}</span><p>Metrics are shown only when the backend provides its saved evaluation report.</p></section>
        : data ? <>
          <div className="report-callout"><span>i</span><div><strong>Held-out evaluation — not guaranteed real-world accuracy</strong><p>These metrics come from a stratified test split of the documented dataset. They do not predict performance on every message or replace security review.</p></div></div>
          <section className="metric-grid analytics-metrics">
            <Metric label="Precision" value={`${(data.precision * 100).toFixed(2)}%`} note="Positive predictions that were phishing" />
            <Metric label="Recall" value={`${(data.recall * 100).toFixed(2)}%`} note="Phishing messages found in test set" />
            <Metric label="F1-score" value={`${(data.f1_score * 100).toFixed(2)}%`} note="Harmonic mean of precision and recall" />
            <Metric label="False-positive rate" value={`${(data.false_positive_rate * 100).toFixed(2)}%`} note={`${data.false_positive_analysis.false_positives} false positives among ${data.test_rows.toLocaleString()} test records`} />
          </section>
          <section className="analytics-grid">
            <article className="panel confusion-panel"><div className="panel-heading"><div><h2>Confusion matrix</h2><p>Actual classes by predicted classes</p></div></div><div className="matrix-table-wrap"><table className="matrix-table"><thead><tr><th>ACTUAL ↓ / PREDICTED →</th>{data.confusion_matrix_labels.map((label) => <th key={label}>{label}</th>)}</tr></thead><tbody>{data.confusion_matrix.map((row, rowIndex) => <tr key={data.confusion_matrix_labels[rowIndex]}><th>{data.confusion_matrix_labels[rowIndex]}</th>{row.map((value, columnIndex) => <td className={rowIndex === columnIndex ? "correct-cell" : "incorrect-cell"} key={columnIndex}><strong>{value.toLocaleString()}</strong><small>{rowIndex === columnIndex ? "Correct" : "Incorrect"}</small></td>)}</tr>)}</tbody></table></div><p className="matrix-explainer">False-positive analysis: {data.false_positive_analysis.false_positives.toLocaleString()} legitimate messages were classified as phishing. FPR = FP / (FP + TN).</p></article>
            <article className="panel model-info-panel"><div className="panel-heading"><div><h2>Evaluation details</h2><p>Provenance from saved report</p></div></div><Info label="Model" value={`${data.model_name} · ${data.model_version}`} /><Info label="Dataset" value={data.dataset_name} /><Info label="Dataset license" value={data.dataset_license} /><Info label="Source rows" value={data.dataset_counts.source_rows.toLocaleString()} /><Info label="Usable unique rows" value={data.dataset_counts.usable_unique_rows.toLocaleString()} /><Info label="Safe / phishing" value={`${data.class_counts_after_deduplication["Safe Email"].toLocaleString()} / ${data.class_counts_after_deduplication["Phishing Email"].toLocaleString()}`} /><Info label="Exact duplicates collapsed" value={data.dataset_counts.duplicate_rows_collapsed.toLocaleString()} /><Info label="Conflicting groups excluded" value={data.dataset_counts.conflicting_duplicate_groups.toLocaleString()} /><Info label="Test split" value={`${(data.test_size_fraction * 100).toFixed(0)}% stratified · random seed ${data.random_state}`} /><Info label="Test samples" value={data.test_rows.toLocaleString()} /><Info label="Trained" value={formatDate(data.trained_at_utc)} /><a className="source-link" href={data.dataset_source} target="_blank" rel="noreferrer">Open dataset source ↗</a></article>
          </section>
        </> : null}
  </>;
}

function Metric({ label, value, note }: { label: string; value: string; note: string }) {
  return <article className="metric-card analytics-metric"><div className="metric-top"><span>{label}</span><span className="metric-icon blue">⌁</span></div><strong>{value}</strong><small>{note}</small></article>;
}

function Info({ label, value }: { label: string; value: string }) {
  return <div className="info-row"><span>{label}</span><strong>{value}</strong></div>;
}
