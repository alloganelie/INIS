/**
 * Core TypeScript definitions mirroring INIS backend models per §0.3, §6, §7, §9, §11, §13, §14, §15, §19, §32.
 */

// Envelope protocol per §5.1
export interface Envelope<T = unknown> {
  message_id: string; // MSG_...
  conversation_id: string; // CNV_...
  source_agent: string; // AGT_...
  target_agent?: string;
  message_type: string;
  timestamp: string; // ISO 8601
  payload: T;
  correlation_id?: string;
  reply_to?: string;
  trace_context?: Record<string, string>;
  security_context?: {
    actor_id?: string;
    clearance_level?: string;
    delegation_chain?: string[];
  };
}

// Source per §9 and §32
export interface Source {
  source_id: string; // SRC_...
  name: string;
  source_type: string;
  url?: string | null;
  description?: string | null;
  trust_level: number;
  status: 'active' | 'archived' | 'deleted' | 'superseded' | string;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface SourceCreate {
  name: string;
  source_type: string;
  url?: string | null;
  description?: string | null;
  trust_level?: number;
  status?: string;
  metadata?: Record<string, unknown>;
}

// InformationUnit per §11 and §32
export type DataStage = 'raw' | 'normalized' | 'enriched' | 'derived';
export type EpistemicStatus = 'factual' | 'hypothesis' | 'assumption' | 'intention' | 'uncertainty';

export interface InformationUnit {
  information_id: string; // INF_...
  type: 'text' | 'number' | 'table' | 'record' | 'image_region' | 'document_fragment' | string;
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
  data_stage: DataStage;
  epistemic_status: EpistemicStatus;
  versions?: string[];
  created_at?: string | null;
  updated_at?: string | null;
}

export interface InformationUnitCreate {
  type?: string;
  content: Record<string, unknown>;
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
  data_stage?: DataStage;
  epistemic_status?: EpistemicStatus;
}

// Evidence per §14.2 and §32
export interface Evidence {
  evidence_id: string; // EVID_...
  claim_id?: string | null;
  information_id?: string | null;
  source_id?: string | null;
  document_id?: string | null;
  dataset_id?: string | null;
  transformation_id?: string | null;
  excerpt?: string | null;
  location?: Record<string, unknown>;
  strength: number;
  confidence?: Record<string, unknown>;
  provenance?: Record<string, unknown>;
  epistemic_status: string;
  created_at?: string | null;
}

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

// Conflict per §14.3 and §32
export interface Conflict {
  conflict_id: string; // CONFLICT_...
  information_a?: string | null;
  information_b?: string | null;
  information_ids: string[];
  claim_ids: string[];
  difference_type: 'value' | 'definition' | 'date' | 'methodology' | 'scope' | string;
  severity: 'low' | 'medium' | 'high' | string;
  status: 'open' | 'investigated' | 'unresolved' | 'resolved' | string;
  resolution_status: 'open' | 'investigated' | 'unresolved' | 'resolved' | string;
  description?: string | null;
  resolution_evidence: string[];
  detected_at?: string | null;
}

export interface ConflictCreate {
  information_a?: string | null;
  information_b?: string | null;
  information_ids?: string[];
  claim_ids?: string[];
  difference_type?: string;
  severity?: string;
  status?: string;
  resolution_status?: string;
  description?: string | null;
  resolution_evidence?: string[];
}

// Quality per §13
export interface QualityCheckResult {
  check_name: string;
  passed: boolean;
  score: number;
  weight: number;
  details?: Record<string, unknown>;
  message?: string | null;
}

export interface QualityReport {
  target_id: string;
  quality_score: number;
  dimensions: Record<string, number>;
  checks: QualityCheckResult[];
  status: string;
  generated_at?: string | null;
}

// Confidence per §15
export interface ConfidenceScore {
  information_id?: string | null;
  confidence_score: number;
  dimensions: {
    source_reliability?: number;
    source_freshness?: number;
    extraction_confidence?: number;
    data_quality?: number;
    evidence_strength?: number;
    cross_source_agreement?: number;
    methodological_consistency?: number;
    [key: string]: number | undefined;
  };
  explanation?: string | null;
  not_a_probability: boolean;
  status: string;
}

export interface ConfidenceMatrix {
  request_id: string;
  matrix: ConfidenceScore[];
  average_confidence: number;
  total_items: number;
  status: string;
}

// Agent per §6
export interface Agent {
  agent_id: string; // AGT_...
  name: string;
  description: string;
  version: string;
  status: 'available' | 'degraded' | 'unavailable' | 'maintenance' | string;
  capabilities: string[];
  protocols: string[];
  message_types: string[];
  input_schemas?: Record<string, unknown>[];
  output_schemas?: Record<string, unknown>[];
  security_requirements?: string[];
  health?: Record<string, unknown>;
  performance_profile?: Record<string, unknown>;
  learning_profile?: Record<string, unknown>;
  registered_at?: string | null;
  last_seen_at?: string | null;
}

// Request per §7
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
  format: 'evidence_package' | 'json' | 'csv' | 'xlsx' | 'pdf' | 'xml' | string;
  fields?: string[];
}

export interface InformationRequest {
  request_id: string; // REQ_...
  request_type: 'research' | 'source' | 'evidence' | 'data' | 'artifact' | string;
  objective: string;
  question?: string | null;
  context?: Record<string, unknown>;
  required_information?: string[];
  constraints?: RequestConstraints;
  required_output?: RequiredOutput;
  requester?: Record<string, unknown>;
  permissions?: Record<string, unknown>;
  status: string;
  created_at?: string | null;
}

export interface InformationRequestCreate {
  objective: string;
  request_type?: 'research' | 'source' | 'evidence' | 'data' | 'artifact' | string;
  question?: string | null;
  context?: Record<string, unknown>;
  required_information?: string[];
  constraints?: RequestConstraints;
  required_output?: RequiredOutput;
  requester?: Record<string, unknown>;
  permissions?: Record<string, unknown>;
}

// Progress per §41.1
export interface Progress {
  steps_total: number;
  steps_done: number;
  current_step: string;
  estimated_completion?: string | null;
  partial_findings_available: boolean;
}

// Auth per §19
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

// Artifact per §32
export interface Artifact {
  artifact_id: string; // ART_...
  request_id?: string | null;
  name: string;
  artifact_type: string;
  size_bytes?: number;
  content_type?: string;
  url?: string;
  created_at?: string | null;
}
