import React from 'react';
import { Conflict } from '../types';

interface ConflictCardProps {
  conflict: Conflict;
  onResolve?: (conflict: Conflict) => void;
}

export const ConflictCard: React.FC<ConflictCardProps> = ({ conflict, onResolve }) => {
  const severityClasses: Record<string, string> = {
    low: 'severity-low',
    medium: 'severity-medium',
    high: 'severity-high',
  };

  const statusClasses: Record<string, string> = {
    open: 'status-badge-warning',
    investigated: 'status-badge-info',
    resolved: 'status-badge-success',
    unresolved: 'status-badge-danger',
  };

  const isResolved = conflict.status === 'resolved' || conflict.resolution_status === 'resolved';

  return (
    <div className={`card conflict-card ${severityClasses[conflict.severity] || ''}`}>
      <div className="card-header">
        <div className="conflict-title-row">
          <span className="conflict-icon">⚡</span>
          <div>
            <h4 className="conflict-id">{conflict.conflict_id}</h4>
            <span className="conflict-diff-type">
              Type: <strong>{conflict.difference_type}</strong>
            </span>
          </div>
        </div>
        <div className="conflict-badges">
          <span className={`severity-badge ${conflict.severity}`}>
            {conflict.severity.toUpperCase()} SEVERITY
          </span>
          <span className={`status-badge ${statusClasses[conflict.status] || ''}`}>
            {conflict.status}
          </span>
        </div>
      </div>

      <div className="card-body">
        <p className="conflict-description">
          {conflict.description || 'Contradiction detected between underlying assertions.'}
        </p>

        <div className="conflicting-entities">
          <div className="entity-box">
            <span className="entity-label">Branch A:</span>
            <code>{conflict.information_a || conflict.information_ids[0] || 'INF_A'}</code>
          </div>
          <span className="vs-divider">VS</span>
          <div className="entity-box">
            <span className="entity-label">Branch B:</span>
            <code>{conflict.information_b || conflict.information_ids[1] || 'INF_B'}</code>
          </div>
        </div>

        {conflict.resolution_evidence && conflict.resolution_evidence.length > 0 && (
          <div className="resolution-evidence-box">
            <span className="evidence-title">Resolution Evidence:</span>
            <ul>
              {conflict.resolution_evidence.map((ev, idx) => (
                <li key={idx}>
                  <code>{ev}</code>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {onResolve && !isResolved && (
        <div className="card-footer">
          <button
            className="btn-secondary btn-sm"
            onClick={() => onResolve(conflict)}
          >
            Mark Resolved
          </button>
        </div>
      )}
    </div>
  );
};

export default ConflictCard;
