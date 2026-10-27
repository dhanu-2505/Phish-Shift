import { useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, createPrediction, type Prediction } from "../api";
import { ResultBadge } from "./Dashboard";

const MAX_MESSAGE_LENGTH = 20_000;

export function Scan() {
  const [message, setMessage] = useState("");
  const [result, setResult] = useState<Prediction | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const tooLong = message.length > MAX_MESSAGE_LENGTH;
  const empty = !message.trim();

  async function submit() {
    if (loading) return;
    if (empty) { setError("Paste a message before starting the scan."); return; }
    if (tooLong) { setError("Messages must be 20,000 characters or fewer."); return; }
    setLoading(true);
    setError("");
    setResult(null);
    try {
      setResult(await createPrediction(message));
    } catch (cause) {
      const messageText = cause instanceof ApiError && cause.status === 422
        ? cause.message || "The message was rejected. Check that it contains text and is within the length limit."
        : cause instanceof ApiError && cause.status === 503
          ? `${cause.message} Check the database and model health indicators in the header.`
          : cause instanceof Error ? cause.message : "Scan failed. Please try again.";
      setError(messageText);
    } finally {
      setLoading(false);
    }
  }

  const phishing = result?.predicted_label === "Phishing Email";

  return (
    <>
      <div className="page-heading">
        <div><div className="overline">MESSAGE ANALYSIS <span className="overline-line" /></div><h1>Scan a message</h1><p>Paste a suspicious email, text, or chat message for a model-based risk check.</p></div>
        <span className="privacy-chip"><span>⌑</span> Local API · no browser storage</span>
      </div>
      <div className="scan-layout">
        <section className="panel scan-form">
          <div className="panel-heading"><div><h2>Message to analyze</h2><p>Only the text you submit is sent to the backend.</p></div><span className="scan-type">TEXT SCAN</span></div>
          <label className="field-label" htmlFor="scan-message">Message content <span>Email · SMS · chat</span></label>
          <textarea id="scan-message" className="scan-textarea" value={message} maxLength={MAX_MESSAGE_LENGTH + 1} onChange={(event) => { setMessage(event.target.value); setError(""); setResult(null); }} placeholder="Paste the message here… Avoid including sensitive personal information." aria-invalid={Boolean(error || tooLong)} aria-describedby="scan-count scan-hint" />
          <div className="textarea-footer"><span id="scan-hint">Scanned message is saved in backend history. It is not stored in browser localStorage.</span><span id="scan-count" className={tooLong ? "text-danger" : ""}>{message.length.toLocaleString()} / 20,000</span></div>
          {(tooLong || error) && <div className="notice danger-notice" role="alert"><span>!</span><div><strong>{tooLong ? "Message exceeds the limit" : "Scan could not be completed"}</strong><p>{tooLong ? "Shorten the message to 20,000 characters or fewer." : error}</p>{error && !loading && !tooLong && <button className="text-button" onClick={() => void submit()} disabled={empty}>Retry scan →</button>}</div></div>}
          <div className="scan-actions"><button className="button button-primary scan-submit" type="button" onClick={() => void submit()} disabled={loading || tooLong}>{loading ? <><span className="loader light" /> Analyzing message…</> : <>Analyze message <span>↗</span></>}</button><span className="action-note">The model's prediction is advisory, not a guarantee.</span></div>
        </section>
        <aside className="scan-aside">
          <article className="panel tips-panel"><span className="aside-symbol purple-symbol">✳</span><h3>What the model checks</h3><p>A TF-IDF and Logistic Regression classifier analyzes text patterns learned from its documented training dataset.</p><Link to="/about">About the model ↗</Link></article>
          <article className="panel warning-panel"><span className="aside-symbol amber-symbol">!</span><h3>Protect private information</h3><p>Submitted messages are saved in local scan history. Don’t paste passwords, personal data, or confidential messages.</p></article>
        </aside>
      </div>
      {result && <section className={`panel scan-result ${phishing ? "phishing-result" : "safe-result"}`} aria-live="polite">
        <div className="scan-result-heading"><div><span className="overline">SCAN COMPLETE · #{result.scan_id.toString().padStart(5, "0")}</span><h2>{phishing ? "Potential phishing detected" : "Classified as safe"}</h2></div><ResultBadge label={result.predicted_label} /></div>
        <div className="result-metrics"><div className="risk-score-block"><span>PHISHING RISK SCORE</span><strong>{(result.risk_score * 100).toFixed(1)}<small>%</small></strong><div className="risk-track"><i style={{ width: `${Math.max(0, Math.min(100, result.risk_score * 100))}%` }} /></div></div><div className="explanation-block"><span>MODEL EXPLANATION</span><p>{result.explanation}</p></div></div>
        <div className="result-bottom"><span>Risk score is the model’s phishing-class probability. Results are not a security guarantee.</span><Link to={`/scans/${result.scan_id}`}>Open scan details ↗</Link></div>
      </section>}
    </>
  );
}
