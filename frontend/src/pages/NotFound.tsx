import { Link } from "react-router-dom";

export function NotFound() {
  return <section className="panel state-box empty-state not-found"><span className="empty-symbol">?</span><strong>Page not found</strong><span>This PhishShift page does not exist.</span><Link to="/">Return to home →</Link></section>;
}
