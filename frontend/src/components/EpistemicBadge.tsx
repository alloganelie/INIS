import React from 'react';
import { EpistemicStatus } from '../types';

interface EpistemicBadgeProps {
  status: EpistemicStatus | string;
  showIcon?: boolean;
}

const statusConfig: Record<string, { label: string; icon: string; className: string; description: string }> = {
  factual: {
    label: 'Factual',
    icon: '✓',
    className: 'epistemic-factual',
    description: 'Verified factual data backed by concrete evidence',
  },
  hypothesis: {
    label: 'Hypothesis',
    icon: '💡',
    className: 'epistemic-hypothesis',
    description: 'Proposed explanation requiring empirical validation',
  },
  assumption: {
    label: 'Assumption',
    icon: '⚠️',
    className: 'epistemic-assumption',
    description: 'Accepted as true without immediate direct proof',
  },
  intention: {
    label: 'Intention',
    icon: '🎯',
    className: 'epistemic-intention',
    description: 'Future planned action or stated intent',
  },
  uncertainty: {
    label: 'Uncertainty',
    icon: '❓',
    className: 'epistemic-uncertainty',
    description: 'Contested or indeterminate truth value',
  },
};

export const EpistemicBadge: React.FC<EpistemicBadgeProps> = ({
  status,
  showIcon = true,
}) => {
  const norm = (status || 'factual').toLowerCase();
  const config = statusConfig[norm] || {
    label: status,
    icon: 'ℹ️',
    className: 'epistemic-neutral',
    description: 'Epistemic state',
  };

  return (
    <span
      className={`epistemic-badge ${config.className}`}
      title={`${config.label}: ${config.description}`}
    >
      {showIcon && <span className="epistemic-icon">{config.icon}</span>}
      <span className="epistemic-text">{config.label}</span>
    </span>
  );
};

export default EpistemicBadge;
