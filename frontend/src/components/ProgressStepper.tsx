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

const TERMINAL_STEPS: ReadonlySet<string> = new Set([
  'DONE',
  'DELIVERY',
  'COMPLETED',
  'SUCCESS',
  'PARTIAL_SUCCESS',
  'CANCELLED',
  'FAILED',
  'ERROR',
]);

/**
 * Map the backend step vocabulary (§28 lifecycle uses RECEIVING/PLAN_GENERATION/
 * DATA_ACQUISITION/…, while the runner emits lowercase understanding/planning/
 * synthesis and completes to DELIVERY) onto the six milestone buckets rendered
 * by the stepper. Unknown steps fall back to the completion ratio.
 */
export function normalizeStepperStep(
  currentStep: string | null | undefined,
  stepsDone: number,
  stepsTotal: number,
): string {
  if (!currentStep) {
    return stepsTotal > 0 && stepsDone >= stepsTotal ? 'DONE' : 'RECEIVING';
  }
  const key = currentStep.toUpperCase().replace(/[^A-Z]/g, '_');
  if (TERMINAL_STEPS.has(key)) {
    return 'DONE';
  }
  if (key === 'RECEIVING' || key.includes('RECEIV')) {
    return 'RECEIVING';
  }
  if (key.includes('PLAN') || key.includes('UNDERSTAND') || key.includes('AUTH') || key.includes('GUIDE')) {
    return 'PLANNING';
  }
  if (
    key.includes('ACQUISITION') ||
    key.includes('HARVEST') ||
    key.includes('EXTRACT') ||
    key.includes('SEARCH') ||
    key.includes('SOURCE') ||
    key.includes('FETCH')
  ) {
    return 'DATA_ACQUISITION';
  }
  if (
    key.includes('QUALITY') ||
    key.includes('EVALUATION') ||
    key.includes('VALID') ||
    key.includes('EVIDENCE') ||
    key.includes('RELIAB') ||
    key.includes('VERIF')
  ) {
    return 'QUALITY_EVALUATION';
  }
  if (
    key.includes('CONFIDENCE') ||
    key.includes('SYNTHES') ||
    key.includes('SCORE') ||
    key.includes('MERGE') ||
    key.includes('PACKAG')
  ) {
    return 'CONFIDENCE_SCORING';
  }
  return stepsTotal > 0 && stepsDone >= stepsTotal ? 'DONE' : 'RECEIVING';
}

export const ProgressStepper: React.FC<ProgressStepperProps> = ({ progress }) => {
  const milestoneStep = normalizeStepperStep(progress.current_step, progress.steps_done, progress.steps_total);
  const isTerminal = TERMINAL_STEPS.has(progress.current_step?.toUpperCase() ?? '') || (
    progress.steps_total > 0 && progress.steps_done >= progress.steps_total
  );
  const percent = progress.steps_total > 0
    ? Math.min(100, Math.round((progress.steps_done / progress.steps_total) * 100))
    : 0;
  const displayPercent = isTerminal ? 100 : percent;
  const currentMilestone = MILESTONES.find((m) => m.id === milestoneStep) ?? MILESTONES[0];

  return (
    <div className="progress-stepper-container card">
      <div className="stepper-header">
        <div>
          <h4 className="stepper-title">Execution Progress</h4>
          <span className="stepper-step-label">
            Current Phase: <strong>{currentMilestone.label}</strong>
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
          style={{ width: `${displayPercent}%` }}
        />
      </div>

      <div className="stepper-milestones">
        {MILESTONES.map((m, idx) => {
          const stepWeight = (idx + 1) / MILESTONES.length;
          const isDone = displayPercent >= 100 || (progress.steps_done / progress.steps_total) >= stepWeight;
          const isCurrent = milestoneStep === m.id;

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

      {progress.partial_findings_available && !isTerminal && (
        <div className="partial-findings-banner">
          <span className="banner-icon">💡</span>
          <span>Partial findings are ready and verifiable in real-time.</span>
        </div>
      )}
    </div>
  );
};

export default ProgressStepper;
