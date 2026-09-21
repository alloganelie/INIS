/** Domain contract mirrors for INIS §§11 and 14. */

export type DataStage = 'raw' | 'normalized' | 'enriched' | 'derived';
export type EpistemicStatus = 'fact' | 'factual' | 'hypothesis' | 'assumption' | 'intention' | 'uncertainty';

export interface InformationUnit {
  information_id: string;
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
  versions?: string[];
  data_stage: DataStage;
  epistemic_status: EpistemicStatus;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface Evidence {
  evidence_id: string;
  claim_id?: string | null;
  information_id?: string | null;
  document_id?: string | null;
  source_id?: string | null;
  dataset_id?: string | null;
  transformation_id?: string | null;
  excerpt?: string | null;
  location?: Record<string, unknown>;
  strength: number;
  confidence?: Record<string, unknown>;
  provenance?: Record<string, unknown>;
  epistemic_status?: EpistemicStatus | string;
  created_at?: string | null;
}

export interface Claim {
  claim_id: string;
  statement: string;
  information_ids: string[];
  evidence_ids: string[];
  confidence: number;
  epistemic_status: 'fact' | 'hypothesis' | 'assumption' | 'uncertainty';
}

export interface Conflict {
  conflict_id: string;
  information_a: string | null;
  information_b: string | null;
  information_ids: string[];
  claim_ids: string[];
  difference_type: 'value' | 'definition' | 'date' | 'methodology' | 'scope';
  severity: 'low' | 'medium' | 'high';
  status: 'open' | 'investigated' | 'unresolved' | 'resolved';
  resolution_status: 'open' | 'investigated' | 'unresolved' | 'resolved';
  description: string | null;
  resolution_evidence: string[];
  detected_at: string | null;
}

export interface AccessPolicy {
  policy_id: string;
  subject: Record<string, unknown>;
  resource: Record<string, unknown>;
  action: 'read' | 'write' | 'update' | 'delete' | 'transmit' | 'search';
  effect: 'allow' | 'deny';
  conditions: Record<string, unknown>;
}

export interface SecurityClassification {
  sensitivity: 'low' | 'medium' | 'high' | 'critical';
  pii: boolean;
  categories: string[];
}

/** Source response fields shared by the domain and the HTTP contract. */
export interface Source {
  source_id: string;
  name: string;
  source_type: string;
  url: string | null;
  description: string | null;
  trust_level: number;
  status: string;
  metadata: Record<string, unknown>;
  created_at: string | null;
  updated_at: string | null;
  type?: string;
  reliability_score?: number;
  freshness?: Record<string, unknown>;
}

export interface Document {
  document_id: string;
  source_id: string;
  mime_type: string;
  content_hash: string;
  storage_ref: string;
}

export interface Dataset {
  dataset_id: string;
  source_id: string;
  dataset_schema: Record<string, unknown>;
  row_count: number;
  storage_ref: string;
}

export interface SourceCandidate {
  url: string;
  provider: string;
  score: number;
  source_id?: string;
  location?: string;
  metadata?: Record<string, string>;
}

export interface InformationPackage {
  package_id: string;
  request_id: string;
  units: Record<string, unknown>[];
  confidence: Record<string, unknown>;
  provenance: Record<string, unknown>;
  created_at: string;
  data_stage: DataStage;
}
