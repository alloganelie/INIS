import React, { useState, useEffect } from 'react';
import * as agentsApi from '../api/agents';
import { Agent } from '../types';
import AgentCard from '../components/AgentCard';

export const AgentsSolicited: React.FC = () => {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);

  const loadAgents = async () => {
    setIsLoading(true);
    try {
      const data = await agentsApi.listAgents();
      setAgents(data);
    } catch {
      setAgents([]);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadAgents();
  }, []);

  const filtered = agents.filter((a) =>
    statusFilter === 'all' ? true : a.status.toLowerCase() === statusFilter.toLowerCase()
  );

  const availableCount = agents.filter((a) => a.status === 'available').length;
  const degradedCount = agents.filter((a) => a.status === 'degraded').length;

  return (
    <div className="page-container agents-solicited-page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Agents Registry (§6 / §31.1)</h1>
          <p className="page-subtitle">
            Autonomous agent federation, protocols, capabilities, and health metrics.
          </p>
        </div>
      </div>

      <div className="stats-row">
        <div className="card stat-card">
          <span className="stat-label">Total Registered</span>
          <span className="stat-value">{agents.length}</span>
        </div>
        <div className="card stat-card">
          <span className="stat-label">Available</span>
          <span className="stat-value text-success">{availableCount}</span>
        </div>
        <div className="card stat-card">
          <span className="stat-label">Degraded</span>
          <span className="stat-value text-warning">{degradedCount}</span>
        </div>
      </div>

      <div className="card filter-bar">
        <span className="filter-label">Filter status:</span>
        {['all', 'available', 'degraded', 'unavailable', 'maintenance'].map((st) => (
          <button
            key={st}
            className={`filter-btn ${statusFilter === st ? 'active' : ''}`}
            onClick={() => setStatusFilter(st)}
          >
            {st.toUpperCase()}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="loading-spinner">Polling agent registry...</div>
      ) : filtered.length === 0 ? (
        <div className="card empty-state">
          <p>No agents matching status '{statusFilter}'.</p>
        </div>
      ) : (
        <div className="agents-grid">
          {filtered.map((agent) => (
            <AgentCard
              key={agent.agent_id}
              agent={agent}
              onSelect={(a) => setSelectedAgent(a)}
            />
          ))}
        </div>
      )}

      {selectedAgent && (
        <div className="modal-overlay" onClick={() => setSelectedAgent(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Agent Specification: {selectedAgent.name}</h3>
              <button className="btn-close" onClick={() => setSelectedAgent(null)}>
                ✕
              </button>
            </div>
            <div className="modal-body">
              <div className="form-group">
                <span className="detail-label">Agent ID:</span>
                <code className="text-code">{selectedAgent.agent_id}</code>
              </div>
              <div className="form-group">
                <span className="detail-label">Protocols:</span>
                <span>{selectedAgent.protocols.join(', ')}</span>
              </div>
              <div className="form-group">
                <span className="detail-label">Message Types:</span>
                <span>{selectedAgent.message_types.join(', ') || 'Standard envelopes'}</span>
              </div>
              <div className="form-group">
                <span className="detail-label">Capabilities:</span>
                <ul>
                  {selectedAgent.capabilities.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AgentsSolicited;
