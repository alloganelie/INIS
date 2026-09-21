/** Inter-agent protocol contract mirrors for INIS §5.1. */

export type MessageType =
  | 'AGENT_REGISTER'
  | 'AGENT_UPDATE'
  | 'AGENT_HEARTBEAT'
  | 'CAPABILITY_QUERY'
  | 'INFORMATION_REQUEST'
  | 'INFORMATION_RESPONSE'
  | 'SOURCE_REQUEST'
  | 'EVIDENCE_REQUEST'
  | 'DATA_REQUEST'
  | 'RESEARCH_REQUEST'
  | 'RESEARCH_PROGRESS'
  | 'RESEARCH_COMPLETED'
  | 'AGENT_DELEGATION_REQUEST'
  | 'AGENT_DELEGATION_RESPONSE'
  | 'CLARIFICATION_REQUEST'
  | 'CONFLICT_REPORT'
  | 'LOW_CONFIDENCE_REPORT'
  | 'ACCESS_DENIED'
  | 'VALIDATION_ERROR'
  | 'EXECUTION_ERROR'
  | 'CANCEL_REQUEST'
  | 'CANCELLED'
  | 'AUDIT_EVENT';

export interface Sender {
  agent_id: string;
  agent_instance_id: string | null;
  agent_version: string;
}

export interface Recipient {
  agent_id: string;
  agent_instance_id: string | null;
}

export interface Security {
  auth_method: 'mtls' | 'jwt' | 'api_key';
  token_id: string | null;
  scopes: string[];
}

export interface Trace {
  trace_id: string;
  span_id: string;
  correlation_id: string;
  causation_id: string | null;
}

export interface Envelope<T = Record<string, unknown>> {
  protocol_version: '1.0';
  message_id: string;
  correlation_id: string;
  causation_id: string | null;
  timestamp: string;
  sender: Sender;
  recipient: Recipient;
  message_type: MessageType;
  priority: 'low' | 'normal' | 'high' | 'critical';
  reply_to: string | null;
  ttl_seconds: number;
  payload: T;
  security: Security;
  trace: Trace;
}
