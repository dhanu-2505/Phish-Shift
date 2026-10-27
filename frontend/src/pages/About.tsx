import { Link } from "react-router-dom";

export function About() {
  return (
    <>
      <section className="public-hero">
        <div className="overline">MESSAGE SECURITY, WITH HUMAN JUDGMENT <span className="overline-line" /></div>
        <h1>PhishShift — Message Risk Scanner</h1>
        <p className="public-lead">
          A practical security tool that helps you pause and assess suspicious
          email, SMS, and chat messages before taking action.
        </p>
        <div className="public-actions">
          <Link className="button button-primary" to="/register">Get started <span>↗</span></Link>
          <Link className="button button-secondary" to="/register">Create account</Link>
          <Link className="button button-quiet" to="/login">Login</Link>
        </div>
        <div className="public-trust"><span>⌑</span> Private accounts · Server-side sessions · No browser message storage</div>
      </section>

      <section className="public-feature-grid" aria-label="About PhishShift">
        <article className="panel about-card">
          <span className="about-card-icon purple-symbol">⌁</span>
          <h2>What PhishShift does</h2>
          <p>
            PhishShift analyzes message text and returns a predicted label,
            phishing-risk probability, and a model-derived explanation. Your
            authenticated workspace also keeps your own scan history.
          </p>
        </article>
        <article className="panel about-card">
          <span className="about-card-icon blue-symbol">✳</span>
          <h2>How the model works</h2>
          <p>
            Its baseline uses word-level TF-IDF features with Logistic
            Regression, trained on a documented labeled email dataset. Open an
            account to review the saved held-out evaluation report and scan
            messages.
          </p>
        </article>
        <article className="panel about-card">
          <span className="about-card-icon amber-symbol">!</span>
          <h2>Know the limitations</h2>
          <ul>
            <li>Training data may not represent current or targeted attacks.</li>
            <li>Risk scores are model probabilities, not guarantees.</li>
            <li>Legitimate messages can be flagged and phishing can be missed.</li>
          </ul>
        </article>
        <article className="panel about-card">
          <span className="about-card-icon green-symbol">✓</span>
          <h2>Scan responsibly</h2>
          <p>
            Submitted message text is stored with the scan in the private
            backend database; history and detail responses do not return that
            text. Do not submit passwords, sensitive personal data, or
            confidential communications. Verify unexpected requests through a
            known, separate channel.
          </p>
        </article>
      </section>
      <p className="public-disclaimer">
        PhishShift is an educational aid, not a substitute for security
        procedures, threat investigation, or professional advice.
      </p>
    </>
  );
}
