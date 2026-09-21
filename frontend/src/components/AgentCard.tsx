import React from 'react';
import { Agent } from '../types';

interface AgentCardProps {
  agent: Agent;
  onSelect?: (agent: Agent) => void;
}

export const AgentCard: React.FC<AgentCardProps> = ({ agent, onSelect }) => {
  const statusColors: Record<string, string> = {
    available: 'status-badge-success',
    degraded: 'status-badge-warning',
    unavailable: 'status-badge-danger',
    maintenance: 'status-badge-info',
  };

  const statusClass = statusColors[agent.status.toLowerCase()] || 'status-badge-neutral';

  return (
    <div
      className="card agent-card"
      onClick={() => onSelect && onSelect(agent)}
      style={{ cursor: onSelect ? 'pointer' : 'default' }}
    >
      <div className="card-header">
        <div className="agent-identity">
          <span className="agent-avatar">🤖</span>
          <div>
            <h4 className="agent-name">{agent.name}</h4>
            <code className="agent-id">{agent.agent_id}</code>
          </div>
        </div>
        <div className="agent-badges">
          <span className={`status-badge ${statusClass}`}>{agent.status}</span>
          <span className="version-badge">v{agent.version}</span>
        </div>
      </div>

      <div className="card-body">
        <p className="agent-description">{agent.description || 'No description provided.'}</p>

        {agent.capabilities && agent.capabilities.length > 0 && (
          <div className="agent-section">
            <span className="section-label">Capabilities:</span>
            <div className="tags-list">
              {agent.capabilities.map((cap) => (
                <span key={cap} className="tag-chip">
                  {cap}
                </span>
              ))}
            </div>
          </div>
        )}

        <div className="agent-meta-row">
          {agent.protocols && (
            <div className="meta-item">
              <span className="meta-label">Protocols:</span>
              <span className="meta-value">{agent.protocols.join(', ')}</span>
            </div>
          )}
          {agent.last_seen_at && (
            <div className="meta-item">
              <span className="meta-label">Last seen:</span>
              <span className="meta-value">
                {new Date(agent.last_seen_at).toLocaleTimeString()}
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default AgentCard;
