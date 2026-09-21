/** HTTP API contract mirrors for INIS §32. */

import type { Conflict, Evidence, InformationUnit, Source } from './domain';

export interface RequestConstraints {
  date_range?: Record<string, unknown> | null;
  source_preferences?: string[];
  minimum_confidence?: number;
  maximum_cost?: number | null;
  maximum_execution_time_seconds?: number;
  maximum_iterations?: number;
  maximum_web_depth?: number;
}

export interface RequiredOutput {
  format?: 'evidence_package' | 'json' | 'csv' | 'xlsx' | 'pdf' | 'xml';
  fields?: string[];
}

export interface InformationRequestCreate {
  objective: string;
  request_type?: 'research' | 'source' | 'evidence' | 'data' | 'artifact';
  question?: string | null;
  context?: Record<string, unknown>;
  required_information?: string[];
  constraints?: RequestConstraints;
  required_output?: RequiredOutput;
  requester?: Record<string, unknown>;
  permissions?: Record<string, unknown>;
}

export interface InformationRequestResponse {
  request_id: string;
  request_type: 'research' | 'source' | 'evidence' | 'data' | 'artifact';
  objective: string;
  question: string | null;
  context: Record<string, unknown>;
  required_information: string[];
  constraints: RequestConstraints;
  required_output: RequiredOutput;
  requester: Record<string, unknown>;
  permissions: Record<string, unknown>;
  status: string;
  created_at: string | null;
}

export type InformationRequest = InformationRequestResponse;

export interface SourceCreate {
  name: string;
  source_type: string;
  url?: string | null;
  description?: string | null;
  trust_level?: number;
  status?: string;
  metadata?: Record<string, unknown>;
}

export type SourceResponse = Source;

export interface InformationUnitCreate {
  type?: InformationUnit['type'];
  content: Record<string, unknown>;
  raw_reference?: Record<string, unknown>;
  source_id: string;
  document_id?: string | null;
  dataset_id?: string | null;
  location?: Record<string, unknown>;
  context?: Record<string, unknown>;
  language?: string | null;
  unit?: string | null;
  time?: Record<string, unknown>;
  classification?: Record<string, unknown>;
  quality?: Record<string, unknown>;
  confidence?: Record<string, unknown>;
  provenance?: Record<string, unknown>;
  data_stage?: InformationUnit['data_stage'];
  epistemic_status?: InformationUnit['epistemic_status'];
}

export type InformationUnitResponse = InformationUnit;

export interface EvidenceCreate {
  claim_id?: string | null;
  information_id?: string | null;
  source_id?: string | null;
  document_id?: string | null;
  dataset_id?: string | null;
  transformation_id?: string | null;
  excerpt?: string | null;
  location?: Record<string, unknown>;
  strength?: number;
  confidence?: Record<string, unknown>;
  provenance?: Record<string, unknown>;
  epistemic_status?: string;
}

export type EvidenceResponse = Evidence;

export interface ConflictCreate {
  information_a?: string | null;
  information_b?: string | null;
  information_ids?: string[];
  claim_ids?: string[];
  difference_type?: Conflict['difference_type'] | string;
  severity?: Conflict['severity'] | string;
  status?: Conflict['status'];
  resolution_status?: Conflict['resolution_status'];
  description?: string | null;
  resolution_evidence?: string[];
}

export type ConflictResponse = Conflict;

export interface QualityCheckRequest {
  target_id: string;
  target_type?: string;
  checks?: string[];
}

export interface QualityCheckResult {
  check_name: string;
  passed: boolean;
  score: number;
  weight: number;
  details: Record<string, unknown>;
  message: string | null;
}

export interface QualityCheckResponse {
  target_id: string;
  passed: boolean;
  overall_score: number;
  checks: QualityCheckResult[];
  timestamp: string | null;
}

export interface QualityReport {
  target_id: string;
  quality_score: number;
  dimensions: Record<string, number>;
  checks: QualityCheckResult[];
  status: string;
  generated_at: string | null;
}

export interface ConfidenceScoreResponse {
  information_id: string | null;
  confidence_score: number;
  dimensions: Record<string, number>;
  explanation: string | null;
  not_a_probability: boolean;
  status: string;
}

export type ConfidenceScore = ConfidenceScoreResponse;

export interface ConfidenceMatrix {
  request_id: string;
  matrix: ConfidenceScoreResponse[];
  average_confidence: number;
  total_items: number;
  status: string;
}

export interface AgentIdentity {
  agent_id: string;
  name: string;
  description: string;
  version: string;
  status: 'available' | 'degraded' | 'unavailable' | 'maintenance';
  capabilities: string[];
  protocols: string[];
  message_types: string[];
  input_schemas: Record<string, unknown>[];
  output_schemas: Record<string, unknown>[];
  security_requirements: string[];
  health: Record<string, unknown>;
  performance_profile: Record<string, unknown>;
  learning_profile: Record<string, unknown>;
  registered_at: string | null;
  last_seen_at: string | null;
}

export type Agent = AgentIdentity;

export interface ProgressResponse {
  steps_total: number;
  steps_done: number;
  current_step: string;
  estimated_completion: string | null;
  partial_findings_available: boolean;
}

export type Progress = ProgressResponse;

export interface UserSession {
  actor_id: string;
  scopes: string[];
  token?: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  refresh_token?: string | null;
}

export interface Artifact {
  artifact_id: string;
  request_id?: string | null;
  name: string;
  artifact_type: string;
  size_bytes?: number;
  content_type?: string;
  url?: string;
  created_at?: string | null;
}
