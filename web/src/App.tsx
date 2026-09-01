import { FormEvent, useMemo, useState } from "react";
import { approveTool, createIncident, investigateIncident } from "./api";
import type { Investigation, ToolProposal } from "./types";

const toLocalInput = (value: Date) => {
  const offset = value.getTimezoneOffset() * 60_000;
  return new Date(value.getTime() - offset).toISOString().slice(0, 16);
};

function App() {
  const end = useMemo(() => new Date(), []);
  const start = useMemo(() => new Date(end.getTime() - 60 * 60 * 1000), [end]);
  const [form, setForm] = useState({
    service: "checkout-api",
    environment: "production",
    alert: "HTTP 503 spike with connection pool exhausted errors after a deployment",
    windowStart: toLocalInput(start),
    windowEnd: toLocalInput(end),
  });
  const [investigation, setInvestigation] = useState<Investigation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [approved, setApproved] = useState<Set<string>>(new Set());

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setApproved(new Set());
    try {
      const incident = await createIncident({
        service: form.service,
        environment: form.environment,
        alert: form.alert,
        window_start: new Date(form.windowStart).toISOString(),
        window_end: new Date(form.windowEnd).toISOString(),
      });
      setInvestigation(await investigateIncident(incident.id));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Investigation failed");
    } finally {
      setBusy(false);
    }
  }

  async function approve(proposal: ToolProposal) {
    setError(null);
    try {
      await approveTool(proposal.id);
      setApproved((current) => new Set([...current, proposal.id]));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Tool approval failed");
    }
  }

  return (
    <main>
      <header className="topbar">
        <div className="brand-mark" aria-hidden="true">IA</div>
        <div>
          <p className="eyebrow">Production operations / read-only</p>
          <h1>Incident Assistant</h1>
        </div>
        <span className="safety-pill"><i /> Guardrails active</span>
      </header>

      <section className="hero">
        <div>
          <p className="eyebrow accent">Grounded investigation</p>
          <h2>Follow evidence.<br />Keep operators in control.</h2>
        </div>
        <p className="hero-copy">Correlate alerts with versioned runbooks, reviewed postmortems, and approved telemetry. Every conclusion stays traceable to a real evidence ID.</p>
      </section>

      <div className="workspace">
        <form className="panel incident-form" onSubmit={submit}>
          <div className="panel-heading">
            <span className="step">01</span>
            <div><p className="eyebrow">New workspace</p><h3>Incident context</h3></div>
          </div>
          <label>Service<input value={form.service} onChange={(event) => setForm({ ...form, service: event.target.value })} required /></label>
          <label>Environment<select value={form.environment} onChange={(event) => setForm({ ...form, environment: event.target.value })}><option>production</option><option>staging</option><option>development</option></select></label>
          <label>Alert payload<textarea rows={5} value={form.alert} onChange={(event) => setForm({ ...form, alert: event.target.value })} required /></label>
          <div className="time-grid">
            <label>Window start<input type="datetime-local" value={form.windowStart} onChange={(event) => setForm({ ...form, windowStart: event.target.value })} required /></label>
            <label>Window end<input type="datetime-local" value={form.windowEnd} onChange={(event) => setForm({ ...form, windowEnd: event.target.value })} required /></label>
          </div>
          <button className="primary" disabled={busy}>{busy ? "Investigating…" : "Start investigation"}<span aria-hidden="true">→</span></button>
          <p className="boundary"><strong>Boundary:</strong> No deploys, restarts, rollbacks, or data mutations.</p>
        </form>

        <section className="results" aria-live="polite">
          {error && <div className="error" role="alert">{error}</div>}
          {!investigation && !busy && (
            <div className="empty-state"><span>⌁</span><h3>Evidence will appear here</h3><p>Create an incident to run hybrid retrieval and prepare bounded tool queries.</p></div>
          )}
          {busy && <div className="empty-state"><span className="spinner" /><h3>Building an evidence map</h3><p>Filtering sources, fusing rankings, and validating citations.</p></div>}
          {investigation && !busy && <InvestigationView investigation={investigation} approved={approved} onApprove={approve} />}
        </section>
      </div>
    </main>
  );
}

function InvestigationView({ investigation, approved, onApprove }: { investigation: Investigation; approved: Set<string>; onApprove: (proposal: ToolProposal) => void }) {
  return (
    <>
      <section className="panel summary-card">
        <div className="panel-heading"><span className="step">02</span><div><p className="eyebrow">Preliminary assessment</p><h3>Grounded summary</h3></div></div>
        <p className="summary-text">{investigation.summary}</p>
        <div className="metric-row">
          <span><strong>{investigation.evidence.length}</strong> evidence items</span>
          <span><strong>{investigation.metrics.total_ms.toFixed(1)} ms</strong> total</span>
          <span><strong>{investigation.metrics.estimated_tokens}</strong> estimated tokens</span>
          <span><strong>${investigation.metrics.estimated_cost_usd.toFixed(4)}</strong> local cost</span>
        </div>
      </section>

      {investigation.hypotheses.map((hypothesis) => (
        <section className="panel hypothesis" key={hypothesis.cause}>
          <div className="confidence"><span>Leading hypothesis</span><strong>{Math.round(hypothesis.confidence * 100)}%</strong></div>
          <h3>{hypothesis.cause}</h3>
          <p>Supporting evidence: {hypothesis.supporting_evidence.join(", ") || "none"}</p>
          {hypothesis.contradictions.length > 0 && <p>Contradictions to review: {hypothesis.contradictions.join(", ")}</p>}
        </section>
      ))}

      <div className="two-column">
        <section className="panel evidence-list">
          <div className="panel-heading compact"><span className="step">03</span><div><p className="eyebrow">Provenance</p><h3>Evidence</h3></div></div>
          {investigation.evidence.map((item) => (
            <article key={item.id}>
              <div><strong>{item.id}</strong><span className={`trust ${item.trust_level}`}>{item.trust_level}</span></div>
              <h4>{item.source}</h4><p>{item.excerpt}</p>
              <small>Version {item.source_version} · score {item.score.toFixed(4)}</small>
            </article>
          ))}
        </section>

        <section className="panel tools-list">
          <div className="panel-heading compact"><span className="step">04</span><div><p className="eyebrow">Human approval</p><h3>Read-only queries</h3></div></div>
          {investigation.next_queries.map((proposal) => (
            <article key={proposal.id}>
              <code>{proposal.tool}</code><p>{proposal.reason}</p>
              <button className="secondary" disabled={approved.has(proposal.id)} onClick={() => onApprove(proposal)}>{approved.has(proposal.id) ? "Executed" : "Approve and run"}</button>
            </article>
          ))}
        </section>
      </div>

      {investigation.security_events.length > 0 && <section className="security-events"><strong>Security events</strong>{investigation.security_events.map((event) => <p key={event}>{event}</p>)}</section>}
    </>
  );
}

export default App;
