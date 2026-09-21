import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import * as requestsApi from '../api/requests';
import { InformationRequestCreate } from '../types';

export const SubmitRequest: React.FC = () => {
  const navigate = useNavigate();
  const [objective, setObjective] = useState('');
  const [requestType, setRequestType] = useState<InformationRequestCreate['request_type']>('research');
  const [question, setQuestion] = useState('');
  const [minConfidence, setMinConfidence] = useState(0.8);
  const [maxIterations, setMaxIterations] = useState(12);
  const [maxTimeSeconds, setMaxTimeSeconds] = useState(300);
  const [outputFormat, setOutputFormat] = useState<'evidence_package' | 'json' | 'csv' | 'pdf'>('evidence_package');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!objective.trim()) {
      setErrorMessage('Please specify an objective.');
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);

    const payload: InformationRequestCreate = {
      objective: objective.trim(),
      request_type: requestType,
      question: question.trim() || undefined,
      constraints: {
        minimum_confidence: Number(minConfidence),
        maximum_iterations: Number(maxIterations),
        maximum_execution_time_seconds: Number(maxTimeSeconds),
      },
      required_output: {
        format: outputFormat,
      },
    };

    try {
      const created = await requestsApi.createRequest(payload);
      navigate(`/requests/status?id=${created.request_id}`);
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : 'Submission failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="page-container submit-request-page">
      <div className="page-header">
        <h1 className="page-title">Submit Information Request (§7)</h1>
        <p className="page-subtitle">
          Initiate autonomous intelligence gathering, multi-source extraction, and synthesis.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="card form-card">
        {errorMessage && <div className="error-banner">{errorMessage}</div>}

        <div className="form-group">
          <label htmlFor="objective">
            Primary Research Objective <span className="required">*</span>
          </label>
          <input
            id="objective"
            type="text"
            className="input-field"
            placeholder="e.g. Map all regulatory approvals and safety signals for Compound-X"
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
            required
          />
        </div>

        <div className="form-row">
          <div className="form-group flex-1">
            <label htmlFor="requestType">Request Modality</label>
            <select
              id="requestType"
              className="select-field"
              value={requestType}
              onChange={(e) => setRequestType(e.target.value as InformationRequestCreate['request_type'])}
            >
              <option value="research">Research & Synthesis</option>
              <option value="source">Source Discovery</option>
              <option value="evidence">Evidence Formulation</option>
              <option value="data">Structured Data Extraction</option>
              <option value="artifact">Artifact Verification</option>
            </select>
          </div>

          <div className="form-group flex-1">
            <label htmlFor="outputFormat">Delivery Output Format (§24)</label>
            <select
              id="outputFormat"
              className="select-field"
              value={outputFormat}
              onChange={(e) => setOutputFormat(e.target.value as 'evidence_package' | 'json' | 'csv' | 'pdf')}
            >
              <option value="evidence_package">Evidence Package (ZIP/JSON)</option>
              <option value="json">Structured JSON</option>
              <option value="csv">Tabular CSV</option>
              <option value="pdf">Audited PDF Report</option>
            </select>
          </div>
        </div>

        <div className="form-group">
          <label htmlFor="question">Specific Guiding Question (Optional)</label>
          <textarea
            id="question"
            className="textarea-field"
            rows={3}
            placeholder="e.g. What are the key discrepancies between trial phase II and phase III outcomes?"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
          />
        </div>

        <div className="form-section-title">
          <h3>Autonomy & Execution Constraints (§8)</h3>
        </div>

        <div className="form-row">
          <div className="form-group flex-1">
            <label htmlFor="minConfidence">
              Minimum Confidence Threshold: <strong>{minConfidence}</strong>
            </label>
            <input
              id="minConfidence"
              type="range"
              min="0.5"
              max="1.0"
              step="0.05"
              value={minConfidence}
              onChange={(e) => setMinConfidence(parseFloat(e.target.value))}
            />
            <span className="field-hint">Enforces strict validation per §15</span>
          </div>

          <div className="form-group flex-1">
            <label htmlFor="maxIterations">Max Autonomous Iterations</label>
            <input
              id="maxIterations"
              type="number"
              className="input-field"
              min="1"
              max="50"
              value={maxIterations}
              onChange={(e) => setMaxIterations(parseInt(e.target.value, 10) || 12)}
            />
          </div>

          <div className="form-group flex-1">
            <label htmlFor="maxTime">Max Execution Time (seconds)</label>
            <input
              id="maxTime"
              type="number"
              className="input-field"
              min="30"
              max="3600"
              value={maxTimeSeconds}
              onChange={(e) => setMaxTimeSeconds(parseInt(e.target.value, 10) || 300)}
            />
          </div>
        </div>

        <div className="form-actions">
          <button
            type="submit"
            className="btn-primary btn-large"
            disabled={isSubmitting}
          >
            {isSubmitting ? 'Dispatching to Agents...' : '🚀 Submit Request'}
          </button>
        </div>
      </form>
    </div>
  );
};

export default SubmitRequest;
