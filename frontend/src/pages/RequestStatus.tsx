import React, { useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { useRequest } from '../hooks/useRequest';
import ProgressStepper from '../components/ProgressStepper';

export const RequestStatus: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const requestId = searchParams.get('id') || '';
  const [inputId, setInputId] = useState(requestId);

  const { request, progress, isLoading, error, refresh } = useRequest(requestId || undefined);

  const handleLookup = (e: React.FormEvent) => {
    e.preventDefault();
    if (inputId.trim()) {
      setSearchParams({ id: inputId.trim() });
    }
  };

  return (
    <div className="page-container request-status-page">
      <div className="page-header">
        <h1 className="page-title">Request Execution Status (§31.1 / §41.1)</h1>
        <p className="page-subtitle">
          Real-time tracking of multi-agent planning, harvesting, and synthesis.
        </p>
      </div>

      {/* Request ID Lookup */}
      <form onSubmit={handleLookup} className="lookup-bar card">
        <label htmlFor="reqIdInput">Lookup Request ID:</label>
        <input
          id="reqIdInput"
          type="text"
          className="input-field"
          placeholder="e.g. REQ_01ARZ3NDEKTSV4RRFFQ69G5F01"
          value={inputId}
          onChange={(e) => setInputId(e.target.value)}
        />
        <button type="submit" className="btn-secondary">
          Track
        </button>
      </form>

      {isLoading && <div className="loading-spinner">Loading execution snapshot...</div>}

      {error && (
        <div className="error-banner">
          {error} — Please verify the Request ID or submit a new query.
        </div>
      )}

      {request && (
        <div className="request-overview-section">
          <div className="card overview-card">
            <div className="overview-header">
              <div>
                <span className="badge-request-type">{request.request_type}</span>
                <h2 className="overview-title">{request.objective}</h2>
                <code className="overview-id">{request.request_id}</code>
              </div>
              <div className="overview-status-pill">
                <span className={`status-pill ${request.status}`}>
                  {request.status.toUpperCase()}
                </span>
                <button className="btn-icon" onClick={refresh} title="Refresh">
                  🔄
                </button>
              </div>
            </div>

            {request.question && (
              <p className="overview-question">
                <strong>Question:</strong> {request.question}
              </p>
            )}

            <div className="overview-meta-grid">
              <div className="meta-card">
                <span className="meta-title">Target Format</span>
                <span className="meta-desc">
                  {request.required_output?.format || 'evidence_package'}
                </span>
              </div>
              <div className="meta-card">
                <span className="meta-title">Min Confidence</span>
                <span className="meta-desc">
                  {request.constraints?.minimum_confidence ?? 0.8}
                </span>
              </div>
              <div className="meta-card">
                <span className="meta-title">Max Time</span>
                <span className="meta-desc">
                  {request.constraints?.maximum_execution_time_seconds ?? 300}s
                </span>
              </div>
            </div>
          </div>

          {progress && <ProgressStepper progress={progress} />}

          <div className="quick-nav-actions">
            <Link
              to={`/confidence?requestId=${request.request_id}`}
              className="btn-secondary"
            >
              📊 Confidence Matrix
            </Link>
            <Link to="/conflicts" className="btn-secondary">
              ⚡ Detected Conflicts
            </Link>
            <Link to="/information" className="btn-secondary">
              📄 Gathered Units
            </Link>
            <Link to="/traceability" className="btn-secondary">
              🔍 Traceability Chain
            </Link>
          </div>
        </div>
      )}

      {!isLoading && !request && !error && (
        <div className="empty-state card">
          <p>No request selected. Enter an ID above or submit a new request.</p>
          <Link to="/" className="btn-primary">
            Submit New Request
          </Link>
        </div>
      )}
    </div>
  );
};

export default RequestStatus;
