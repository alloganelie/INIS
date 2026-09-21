import React from 'react';

interface ProvenanceNode {
  id: string;
  label: string;
  type: 'source' | 'agent' | 'transformation' | 'information' | 'evidence';
  timestamp?: string;
  details?: Record<string, unknown>;
  children?: ProvenanceNode[];
}

interface ProvenanceTreeProps {
  rootNode?: ProvenanceNode;
  provenanceData?: Record<string, unknown>;
}

export const ProvenanceTree: React.FC<ProvenanceTreeProps> = ({
  rootNode,
  provenanceData,
}) => {
  // Build a synthetic tree if raw provenanceData dict is passed
  const node: ProvenanceNode = rootNode || {
    id: String(provenanceData?.source_id || 'SRC_ORIGIN'),
    label: `Source: ${String(provenanceData?.source_id || 'Primary Ingestion')}`,
    type: 'source',
    timestamp: String(provenanceData?.timestamp || new Date().toISOString()),
    children: [
      {
        id: String(provenanceData?.agent_id || 'AGT_INGEST'),
        label: `Agent: ${String(provenanceData?.agent_id || 'Autonomous Ingestor')}`,
        type: 'agent',
        children: [
          {
            id: 'TRF_NORM',
            label: 'Transformation: RAW → NORMALIZED',
            type: 'transformation',
            children: [
              {
                id: String(provenanceData?.information_id || 'INF_DERIVED'),
                label: `Unit: ${String(provenanceData?.information_id || 'Active Artifact')}`,
                type: 'information',
              },
            ],
          },
        ],
      },
    ],
  };

  const renderNode = (item: ProvenanceNode) => {
    const iconMap = {
      source: '🌐',
      agent: '🤖',
      transformation: '⚙️',
      information: '📄',
      evidence: '🔍',
    };

    return (
      <div key={item.id} className="provenance-node">
        <div className={`node-card node-type-${item.type}`}>
          <span className="node-icon">{iconMap[item.type]}</span>
          <div className="node-content">
            <span className="node-title">{item.label}</span>
            <code className="node-id">{item.id}</code>
            {item.timestamp && (
              <span className="node-time">
                {new Date(item.timestamp).toLocaleTimeString()}
              </span>
            )}
          </div>
        </div>

        {item.children && item.children.length > 0 && (
          <div className="node-children">
            {item.children.map((child) => renderNode(child))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="provenance-tree-container card">
      <div className="card-header">
        <h4 className="card-title">Origin & Provenance Graph (§11 / §20)</h4>
        <span className="provenance-badge">Immutable Chain</span>
      </div>
      <div className="card-body provenance-canvas">
        {renderNode(node)}
      </div>
    </div>
  );
};

export default ProvenanceTree;
