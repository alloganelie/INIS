import React, { useState, useEffect } from 'react';
import * as infoApi from '../api/information';
import { InformationUnit, DataStage } from '../types';
import EpistemicBadge from '../components/EpistemicBadge';

export const InformationUnits: React.FC = () => {
  const [units, setUnits] = useState<InformationUnit[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [filterStage, setFilterStage] = useState<string>('all');
  const [selectedUnit, setSelectedUnit] = useState<InformationUnit | null>(null);

  const loadUnits = async () => {
    setIsLoading(true);
    try {
      const data = await infoApi.listInformation();
      setUnits(data);
    } catch {
      setUnits([]);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadUnits();
  }, []);

  const filteredUnits = units.filter((u) =>
    filterStage === 'all' ? true : u.data_stage === filterStage
  );

  return (
    <div className="page-container information-units-page">
      <div className="page-header">
        <h1 className="page-title">Information Units (§11 / §12 / §31.1)</h1>
        <p className="page-subtitle">
          Atomic factual representations, epistemic status, and lifecycle stages (RAW → DERIVED).
        </p>
      </div>

      <div className="card filter-bar">
        <span className="filter-label">Filter Data Stage (§12):</span>
        {(['all', 'raw', 'normalized', 'enriched', 'derived'] as (DataStage | 'all')[]).map(
          (stage) => (
            <button
              key={stage}
              className={`filter-btn ${filterStage === stage ? 'active' : ''}`}
              onClick={() => setFilterStage(stage)}
            >
              {stage.toUpperCase()}
            </button>
          )
        )}
      </div>

      {isLoading ? (
        <div className="loading-spinner">Harvesting Information Units...</div>
      ) : filteredUnits.length === 0 ? (
        <div className="card empty-state">
          <p>No Information Units found for stage '{filterStage}'.</p>
        </div>
      ) : (
        <div className="units-layout">
          <div className="units-table-pane card">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Unit ID</th>
                  <th>Source</th>
                  <th>Epistemic Status</th>
                  <th>Stage</th>
                  <th>Type</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {filteredUnits.map((u) => (
                  <tr
                    key={u.information_id}
                    className={selectedUnit?.information_id === u.information_id ? 'row-selected' : ''}
                  >
                    <td>
                      <code className="text-code">{u.information_id}</code>
                    </td>
                    <td>
                      <span className="source-ref">{u.source_id}</span>
                    </td>
                    <td>
                      <EpistemicBadge status={u.epistemic_status} />
                    </td>
                    <td>
                      <span className={`stage-badge stage-${u.data_stage}`}>
                        {u.data_stage}
                      </span>
                    </td>
                    <td>
                      <span className="type-badge">{u.type}</span>
                    </td>
                    <td>
                      <button
                        className="btn-secondary btn-sm"
                        onClick={() => setSelectedUnit(u)}
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {selectedUnit && (
            <div className="unit-detail-pane card">
              <div className="pane-header">
                <h3>Unit Inspector</h3>
                <button className="btn-close" onClick={() => setSelectedUnit(null)}>
                  ✕
                </button>
              </div>

              <div className="detail-item">
                <span className="detail-label">Identifier</span>
                <code className="text-code">{selectedUnit.information_id}</code>
              </div>

              <div className="detail-item">
                <span className="detail-label">Epistemic Status</span>
                <EpistemicBadge status={selectedUnit.epistemic_status} />
              </div>

              <div className="detail-item">
                <span className="detail-label">Lifecycle Stage (§12)</span>
                <span className={`stage-badge stage-${selectedUnit.data_stage}`}>
                  {selectedUnit.data_stage.toUpperCase()}
                </span>
              </div>

              <div className="detail-item">
                <span className="detail-label">Content Payload</span>
                <pre className="json-box">
                  {JSON.stringify(selectedUnit.content, null, 2)}
                </pre>
              </div>

              {selectedUnit.raw_reference && (
                <div className="detail-item">
                  <span className="detail-label">Raw Reference Offsets</span>
                  <pre className="json-box">
                    {JSON.stringify(selectedUnit.raw_reference, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default InformationUnits;
