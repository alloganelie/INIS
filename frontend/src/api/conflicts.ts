import apiClient from './client';
import { Conflict, ConflictCreate } from '../types';

export interface ConflictListResponse {
  items: Conflict[];
  conflicts: Conflict[];
  total: number;
}

export async function listConflicts(status?: string): Promise<Conflict[]> {
  const res = await apiClient.get<ConflictListResponse | Conflict[]>('/conflicts', {
    params: { status },
  });
  if (Array.isArray(res.data)) {
    return res.data;
  }
  return res.data.items || res.data.conflicts || [];
}

export async function getConflict(id: string): Promise<Conflict> {
  const res = await apiClient.get<Conflict>(`/conflicts/${id}`);
  return res.data;
}

export async function createConflict(payload: ConflictCreate): Promise<Conflict> {
  const res = await apiClient.post<Conflict>('/conflicts', payload);
  return res.data;
}
