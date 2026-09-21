import apiClient from './client';
import { Evidence, EvidenceCreate } from '../types';

export interface EvidenceListResponse {
  items: Evidence[];
  evidence: Evidence[];
  total: number;
}

export async function listEvidence(claimId?: string): Promise<Evidence[]> {
  const res = await apiClient.get<EvidenceListResponse | Evidence[]>('/evidence', {
    params: { claim_id: claimId },
  });
  if (Array.isArray(res.data)) {
    return res.data;
  }
  return res.data.items || res.data.evidence || [];
}

export async function getEvidence(id: string): Promise<Evidence> {
  const res = await apiClient.get<Evidence>(`/evidence/${id}`);
  return res.data;
}

export async function createEvidence(payload: EvidenceCreate): Promise<Evidence> {
  const res = await apiClient.post<Evidence>('/evidence', payload);
  return res.data;
}
