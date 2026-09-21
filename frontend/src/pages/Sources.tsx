import React, { useState, useEffect } from 'react';
import * as sourcesApi from '../api/sources';
import { Source, SourceCreate } from '../types';

export const Sources: React.FC = () => {
  const [sources, setSources] = useState<Source[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [filterType, setFilterType] = useState<string>('all');
  const [showAddForm, setShowAddForm] = useState<boolean>(false);

  // New source form state
  const [newName, setNewName] = useState('');
  const [newType, setNewType] = useState('rest_api');
  const [newUrl, setNewUrl] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [newTrust, setNewTrust] = useState(1.0);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const loadSources = async () => {
    setIsLoading(true);
    try {
      const data = await sourcesApi.listSources(filterType === 'all' ? undefined : filterType);
      setSources(data);
    } catch {
      setSources([]);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadSources();
  }, [filterType]);

  const handleCreateSource = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;

    setIsSubmitting(true);
    const payload: SourceCreate = {
      name: newName.trim(),
      source_type: newType,
      url: newUrl.trim() || null,
      description: newDesc.trim() || null,
      trust_level: Number(newTrust),
      status: 'active',
    };

    try {
      await sourcesApi.createSource(payload);
      setShowAddForm(false);
      setNewName('');
      setNewUrl('');
      setNewDesc('');
      loadSources();
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="page-container sources-page">
      <div className="page-header">
        <div className="header-left">
          <h1 className="page-title">Registered Sources (§9 / §32)</h1>
          <p className="page-subtitle">
            External connectors, documents, databases, and continuous stream feeds.
          </p>
        </div>
        <button
          className="btn-primary"
          onClick={() => setShowAddForm(!showAddForm)}
        >
          {showAddForm ? '✕ Close Form' : '+ Register Source'}
        </button>
      </div>

      {showAddForm && (
        <form onSubmit={handleCreateSource} className="card form-card mb-4">
          <h3>Register New Data Source</h3>
          <div className="form-row">
            <div className="form-group flex-1">
              <label htmlFor="sourceName">Source Name *</label>
              <input
                id="sourceName"
                type="text"
                className="input-field"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                required
              />
            </div>
            <div className="form-group flex-1">
              <label htmlFor="sourceType">Source Type</label>
              <select
                id="sourceType"
                className="select-field"
                value={newType}
                onChange={(e) => setNewType(e.target.value)}
              >
                <option value="rest_api">REST API</option>
                <option value="web_page">Web Page / Scraper</option>
                <option value="postgres">PostgreSQL Database</option>
                <option value="document">Document / PDF</option>
                <option value="file_system">File System Feed</option>
              </select>
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="sourceUrl">Endpoint URL / Connection String</label>
            <input
              id="sourceUrl"
              type="text"
              className="input-field"
              value={newUrl}
              onChange={(e) => setNewUrl(e.target.value)}
              placeholder="https://api.example.org/v1/data"
            />
          </div>

          <div className="form-group">
            <label htmlFor="sourceDesc">Functional Summary</label>
            <textarea
              id="sourceDesc"
              className="textarea-field"
              rows={2}
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label htmlFor="sourceTrust">Base Trustworthiness: {newTrust}</label>
            <input
              id="sourceTrust"
              type="range"
              min="0.1"
              max="1.0"
              step="0.05"
              value={newTrust}
              onChange={(e) => setNewTrust(parseFloat(e.target.value))}
            />
          </div>

          <div className="form-actions">
            <button
              type="submit"
              className="btn-primary"
              disabled={isSubmitting}
            >
              {isSubmitting ? 'Registering...' : 'Save Source'}
            </button>
          </div>
        </form>
      )}

      {/* Filter Toolbar */}
      <div className="card filter-bar">
        <span className="filter-label">Filter by type:</span>
        {['all', 'rest_api', 'web_page', 'postgres', 'document'].map((t) => (
          <button
            key={t}
            className={`filter-btn ${filterType === t ? 'active' : ''}`}
            onClick={() => setFilterType(t)}
          >
            {t.replace('_', ' ').toUpperCase()}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="loading-spinner">Loading sources...</div>
      ) : sources.length === 0 ? (
        <div className="card empty-state">
          <p>No sources registered under this criteria.</p>
        </div>
      ) : (
        <div className="sources-table-container card">
          <table className="data-table">
            <thead>
              <tr>
                <th>Source ID</th>
                <th>Name</th>
                <th>Type</th>
                <th>Trust Level</th>
                <th>Status</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((src) => (
                <tr key={src.source_id}>
                  <td>
                    <code className="text-code">{src.source_id}</code>
                  </td>
                  <td>
                    <strong>{src.name}</strong>
                    {src.description && <div className="text-muted">{src.description}</div>}
                  </td>
                  <td>
                    <span className="badge-tag">{src.source_type}</span>
                  </td>
                  <td>
                    <div className="trust-meter">
                      <div
                        className="trust-meter-fill"
                        style={{ width: `${Math.round(src.trust_level * 100)}%` }}
                      />
                      <span>{(src.trust_level).toFixed(2)}</span>
                    </div>
                  </td>
                  <td>
                    <span className={`status-pill ${src.status}`}>{src.status}</span>
                  </td>
                  <td>
                    {src.created_at ? new Date(src.created_at).toLocaleDateString() : '—'}
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

export default Sources;
