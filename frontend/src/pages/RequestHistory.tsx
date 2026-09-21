import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import * as requestsApi from '../api/requests';
import { InformationRequest } from '../types';

export const RequestHistory: React.FC = () => {
  const [history, setHistory] = useState<InformationRequest[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
    requestsApi
      .listRequests()
      .then(setHistory)
      .catch(() => setHistory([]))
      .finally(() => setIsLoading(false));
  }, []);

  return (
    <div className="page-container request-history-page">
      <div className="page-header">
        <div className="header-left">
          <h1 className="page-title">Request History (§31.1)</h1>
          <p className="page-subtitle">
            Log of dispatched intelligence requests, statuses, and synthesized artifacts.
          </p>
        </div>
        <Link to="/" className="btn-primary">
          + New Request
        </Link>
      </div>

      {isLoading ? (
        <div className="loading-spinner">Retrieving request logs...</div>
      ) : history.length === 0 ? (
        <div className="card empty-state">
          <p>No historical requests found. Submit your first request to see it tracked here.</p>
          <Link to="/" className="btn-primary">
            Submit Request
          </Link>
        </div>
      ) : (
        <div className="card table-card">
          <table className="data-table">
            <thead>
              <tr>
                <th>Request ID</th>
                <th>Objective</th>
                <th>Type</th>
                <th>Status</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {history.map((req) => (
                <tr key={req.request_id}>
                  <td>
                    <code className="text-code">{req.request_id}</code>
                  </td>
                  <td>
                    <strong>{req.objective}</strong>
                  </td>
                  <td>
                    <span className="badge-tag">{req.request_type}</span>
                  </td>
                  <td>
                    <span className={`status-pill ${req.status}`}>{req.status}</span>
                  </td>
                  <td>
                    {req.created_at ? new Date(req.created_at).toLocaleString() : 'Recent'}
                  </td>
                  <td>
                    <div className="action-buttons">
                      <Link
                        to={`/requests/status?id=${req.request_id}`}
                        className="btn-secondary btn-sm"
                      >
                        Status
                      </Link>
                      <Link
                        to={`/confidence?requestId=${req.request_id}`}
                        className="btn-link btn-sm"
                      >
                        Confidence
                      </Link>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default RequestHistory;
