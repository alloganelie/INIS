import React from 'react';
import { Progress } from '../types';

interface ProgressStepperProps {
  progress: Progress;
}

const MILESTONES = [
  { id: 'RECEIVING', label: 'Submission' },
  { id: 'PLANNING', label: 'Autonomous Plan' },
  { id: 'DATA_ACQUISITION', label: 'Data Harvesting' },
  { id: 'QUALITY_EVALUATION', label: 'Quality & Evidence' },
  { id: 'CONFIDENCE_SCORING', label: 'Confidence & Synthesis' },
  { id: 'DONE', label: 'Package Delivery' },
];

export const ProgressStepper: React.FC<ProgressStepperProps> = ({ progress }) => {
  const percent = progress.steps_total > 0
    ? Math.min(100, Math.round((progress.steps_done / progress.steps_total) * 100))
    : 0;

  return (
    <div className="progress-stepper-container card">
      <div className="stepper-header">
        <div>
          <h4 className="stepper-title">Execution Progress</h4>
          <span className="stepper-step-label">
            Current Phase: <strong>{progress.current_step.replace(/_/g, ' ')}</strong>
          </span>
        </div>
        <div className="stepper-counts">
          <span className="steps-count">
            {progress.steps_done} / {progress.steps_total} steps
          </span>
          <span className="steps-percent">({percent}%)</span>
        </div>
      </div>

      <div className="stepper-bar-track">
        <div
          className="stepper-bar-fill"
          style={{ width: `${percent}%` }}
        />
      </div>

      <div className="stepper-milestones">
        {MILESTONES.map((m, idx) => {
          const stepWeight = (idx + 1) / MILESTONES.length;
          const isDone = (progress.steps_done / progress.steps_total) >= stepWeight || progress.current_step === 'DONE';
          const isCurrent = progress.current_step === m.id;

          return (
            <div
              key={m.id}
              className={`milestone-step ${isDone ? 'done' : ''} ${isCurrent ? 'current' : ''}`}
            >
              <div className="milestone-dot">{isDone ? '✓' : idx + 1}</div>
              <span className="milestone-label">{m.label}</span>
            </div>
          );
        })}
      </div>

      {progress.partial_findings_available && (
        <div className="partial-findings-banner">
          <span className="banner-icon">💡</span>
          <span>Partial findings are ready and verifiable in real-time.</span>
        </div>
      )}
    </div>
  );
};

export default ProgressStepper;
