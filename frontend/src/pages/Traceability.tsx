import React, { useState } from 'react';
import { useTrace } from '../contexts/TraceContext';
import ProvenanceTree from '../components/ProvenanceTree';

export const Traceability: React.FC = () => {
  const { traceId, setTraceId, resetTraceId } = useTrace();
  const [queryTrace, setQueryTrace] = useState(traceId);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (queryTrace.trim()) {
      setTraceId(queryTrace.trim());
    }
  };

  return (
    <div className="page-container traceability-page">
      <div className="page-header">
        <h1 className="page-title">Traceability & Provenance (§20 / §31.1)</h1>
        <p className="page-subtitle">
          Distributed audit trails, execution lineage, and cryptographic origin verification.
        </p>
      </div>

      <form onSubmit={handleSearch} className="card lookup-bar">
        <label htmlFor="traceInput">Inspect Trace ID:</label>
        <input
          id="traceInput"
          type="text"
          className="input-field"
          value={queryTrace}
          onChange={(e) => setQueryTrace(e.target.value)}
          placeholder="e.g. TRC_01ARZ3NDEKTSV4RRFFQ69G5F01"
        />
        <button type="submit" className="btn-secondary">
          Track Lineage
        </button>
        <button
          type="button"
          className="btn-primary"
          onClick={() => {
            const newId = resetTraceId();
            setQueryTrace(newId);
          }}
        >
          Generate New Trace
        </button>
      </form>

      <div className="trace-status-banner card">
        <div>
          <span className="banner-sub">Current Distributed Context</span>
          <h3 className="trace-heading">
            <code className="text-code text-large">{traceId}</code>
          </h3>
        </div>
        <div className="trace-compliance-badge">
          <span className="badge-pill">§20.2 Audit Compliant</span>
        </div>
      </div>

      <ProvenanceTree
        provenanceData={{
          trace_id: traceId,
          source_id: 'SRC_WEB_REGULATORY_FDA',
          agent_id: 'AGT_HARVESTER_01',
          information_id: 'INF_01ARZ3NDEKTSV4RRFFQ69G5F01',
          timestamp: new Date().toISOString(),
        }}
      />

      <div className="card audit-events-card">
        <div className="card-header">
          <h4>Audit Trail Events</h4>
        </div>
        <div className="events-timeline">
          <div className="timeline-item">
            <div className="timeline-marker"></div>
            <div className="timeline-content">
              <span className="timeline-time">{new Date().toLocaleTimeString()}</span>
              <strong>Request Received & Validated</strong>
              <p>Actor cleared under clearance level RESTRICTED (§19.3)</p>
            </div>
          </div>
          <div className="timeline-item">
            <div className="timeline-marker"></div>
            <div className="timeline-content">
              <span className="timeline-time">{new Date().toLocaleTimeString()}</span>
              <strong>Multi-Agent Broadcast</strong>
              <p>Envelope propagated to AGT_HARVESTER_01 and AGT_VALIDATOR_02 (§5.1)</p>
            </div>
          </div>
          <div className="timeline-item">
            <div className="timeline-marker"></div>
            <div className="timeline-content">
              <span className="timeline-time">{new Date().toLocaleTimeString()}</span>
              <strong>Provenance Signature Sealed</strong>
              <p>SHA256 digest appended to audit trail</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Traceability;
