import React, { useState } from 'react';
import { ConfidenceScore } from '../types';

interface ConfidenceBarProps {
  score: number; // 0.0 to 1.0
  dimensions?: ConfidenceScore['dimensions'];
  explanation?: string | null;
  showDetails?: boolean;
}

export const ConfidenceBar: React.FC<ConfidenceBarProps> = ({
  score,
  dimensions,
  explanation,
  showDetails = false,
}) => {
  const [expanded, setExpanded] = useState<boolean>(showDetails);

  // Determine color based on threshold
  const getBarColor = (val: number): string => {
    if (val >= 0.8) return 'var(--color-success, #10b981)';
    if (val >= 0.6) return 'var(--color-warning, #f59e0b)';
    return 'var(--color-danger, #ef4444)';
  };

  const percent = Math.min(100, Math.max(0, Math.round(score * 100)));
  const barColor = getBarColor(score);

  return (
    <div className="confidence-container">
      <div className="confidence-header">
        <div className="confidence-title-group">
          <span className="confidence-title">Confidence</span>
          <span className="confidence-invariant-badge" title="Invariant per §15: Not a probability">
            Non-probabilistic
          </span>
        </div>
        <div className="confidence-value-group">
          <span className="confidence-score-val" style={{ color: barColor }}>
            {(score).toFixed(2)}
          </span>
          <span className="confidence-percent">({percent}%)</span>
        </div>
      </div>

      <div className="confidence-bar-track">
        <div
          className="confidence-bar-fill"
          style={{
            width: `${percent}%`,
            backgroundColor: barColor,
          }}
        />
      </div>

      {dimensions && Object.keys(dimensions).length > 0 && (
        <div className="confidence-expand-section">
          <button
            type="button"
            className="btn-link"
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? '▲ Hide 7 Dimensions' : '▼ View 7 Dimensions'}
          </button>

          {expanded && (
            <div className="confidence-dimensions-grid">
              {Object.entries(dimensions).map(([key, dimScore]) => {
                if (dimScore === undefined) return null;
                const dimPercent = Math.round(dimScore * 100);
                return (
                  <div key={key} className="dimension-row">
                    <span className="dimension-name">
                      {key.replace(/_/g, ' ')}
                    </span>
                    <div className="dimension-bar-track">
                      <div
                        className="dimension-bar-fill"
                        style={{
                          width: `${dimPercent}%`,
                          backgroundColor: getBarColor(dimScore),
                        }}
                      />
                    </div>
                    <span className="dimension-value">{(dimScore).toFixed(2)}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {explanation && expanded && (
        <p className="confidence-explanation">{explanation}</p>
      )}
    </div>
  );
};

export default ConfidenceBar;
