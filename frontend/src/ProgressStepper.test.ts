import { describe, it, expect } from 'vitest';
import { normalizeStepperStep } from './components/ProgressStepper';

describe('ProgressStepper step normalization (§41.1 vocabulary)', () => {
  it('maps the terminal DELIVERY step to the final DONE milestone', () => {
    expect(normalizeStepperStep('DELIVERY', 4, 22)).toBe('DONE');
  });

  it('maps runner lowercase understanding/planning to the PLAN milestone', () => {
    expect(normalizeStepperStep('understanding', 1, 22)).toBe('PLANNING');
    expect(normalizeStepperStep('planning', 2, 22)).toBe('PLANNING');
    expect(normalizeStepperStep('PLAN_GENERATION', 2, 22)).toBe('PLANNING');
  });

  it('maps DATA_ACQUISITION and extraction steps to the harvest milestone', () => {
    expect(normalizeStepperStep('DATA_ACQUISITION', 3, 22)).toBe('DATA_ACQUISITION');
    expect(normalizeStepperStep('EXTRACTION', 4, 22)).toBe('DATA_ACQUISITION');
  });

  it('falls back to the completion ratio for unknown steps', () => {
    expect(normalizeStepperStep(undefined, 20, 22)).toBe('RECEIVING');
    expect(normalizeStepperStep('CUSTOM_LABEL', 22, 22)).toBe('DONE');
    expect(normalizeStepperStep(null, 0, 22)).toBe('RECEIVING');
  });
});