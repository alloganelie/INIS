import React, { useState, useEffect } from 'react';
import * as conflictsApi from '../api/conflicts';
import { Conflict, ConflictCreate } from '../types';
import ConflictCard from '../components/ConflictCard';

export const Conflicts: React.FC = () => {
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [showCreateModal, setShowCreateModal] = useState(false);

  // New conflict state
  const [infoA, setInfoA] = useState('');
  const [infoB, setInfoB] = useState('');
  const [diffType, setDiffType] = useState('value');
  const [severity, setSeverity] = useState('medium');
  const [description, setDescription] = useState('');

  const loadConflicts = async () => {
    setIsLoading(true);
    try {
      const data = await conflictsApi.listConflicts(
        filterStatus === 'all' ? undefined : filterStatus
      );
      setConflicts(data);
    } catch {
      setConflicts([]);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadConflicts();
  }, [filterStatus]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const payload: ConflictCreate = {
      information_a: infoA.trim() || undefined,
      information_b: infoB.trim() || undefined,
      information_ids: [infoA.trim(), infoB.trim()].filter(Boolean),
      difference_type: diffType,
      severity,
      status: 'open',
      description: description.trim() || undefined,
    };

    await conflictsApi.createConflict(payload);
    setShowCreateModal(false);
    setInfoA('');
    setInfoB('');
    setDescription('');
    loadConflicts();
  };

  const handleResolve = (conflict: Conflict) => {
    // Optimistic resolution
    setConflicts((prev) =>
      prev.map((c) =>
        c.conflict_id === conflict.conflict_id
          ? { ...c, status: 'resolved', resolution_status: 'resolved' }
          : c
      )
    );
  };

  return (
    <div className="page-container conflicts-page">
      <div className="page-header">
        <div className="header-left">
          <h1 className="page-title">Contradictions & Conflicts (§14.3 / §31.1)</h1>
          <p className="page-subtitle">
            Epistemic conflict detection, severity classification, and dialectical resolution.
          </p>
        </div>
        <button
          className="btn-primary"
          onClick={() => setShowCreateModal(!showCreateModal)}
        >
          {showCreateModal ? '✕ Cancel' : '+ Report Contradiction'}
        </button>
      </div>

      {showCreateModal && (
        <form onSubmit={handleCreate} className="card form-card mb-4">
          <h3>Record Inconsistent Findings</h3>
          <div className="form-row">
            <div className="form-group flex-1">
              <label htmlFor="infoA">Information Unit A (INF_...)</label>
              <input
                id="infoA"
                type="text"
                className="input-field"
                placeholder="INF_01ARZ3NDEKTSV4RRFFQ69G5F01"
                value={infoA}
                onChange={(e) => setInfoA(e.target.value)}
                required
              />
            </div>
            <div className="form-group flex-1">
              <label htmlFor="infoB">Information Unit B (INF_...)</label>
              <input
                id="infoB"
                type="text"
                className="input-field"
                placeholder="INF_01ARZ3NDEKTSV4RRFFQ69G5F02"
                value={infoB}
                onChange={(e) => setInfoB(e.target.value)}
                required
              />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group flex-1">
              <label htmlFor="diffType">Difference Type</label>
              <select
                id="diffType"
                className="select-field"
                value={diffType}
                onChange={(e) => setDiffType(e.target.value)}
              >
                <option value="value">Value Discrepancy</option>
                <option value="definition">Semantic / Definition</option>
                <option value="date">Temporal / Date</option>
                <option value="methodology">Methodological Incompatibility</option>
                <option value="scope">Scope Boundary</option>
              </select>
            </div>

            <div className="form-group flex-1">
              <label htmlFor="severity">Severity Level</label>
              <select
                id="severity"
                className="select-field"
                value={severity}
                onChange={(e) => setSeverity(e.target.value)}
              >
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="desc">Conflict Description</label>
            <textarea
              id="desc"
              className="textarea-field"
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Explain the contradictory statements or divergence in data..."
            />
          </div>

          <div className="form-actions">
            <button type="submit" className="btn-primary">
              Save Contradiction
            </button>
          </div>
        </form>
      )}

      <div className="card filter-bar">
        <span className="filter-label">Filter status:</span>
        {['all', 'open', 'investigated', 'resolved'].map((st) => (
          <button
            key={st}
            className={`filter-btn ${filterStatus === st ? 'active' : ''}`}
            onClick={() => setFilterStatus(st)}
          >
            {st.toUpperCase()}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="loading-spinner">Auditing conflicts...</div>
      ) : conflicts.length === 0 ? (
        <div className="card empty-state">
          <p>No conflicts recorded under filter '{filterStatus}'.</p>
        </div>
      ) : (
        <div className="conflicts-grid">
          {conflicts.map((conflict) => (
            <ConflictCard
              key={conflict.conflict_id}
              conflict={conflict}
              onResolve={handleResolve}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export default Conflicts;
