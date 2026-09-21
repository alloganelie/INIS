import apiClient from './client';
import { Source, SourceCreate } from '../types';

export interface SourceListResponse {
  sources: Source[];
  items: Source[];
  total: number;
}

export async function listSources(sourceType?: string): Promise<Source[]> {
  const res = await apiClient.get<SourceListResponse | Source[]>('/sources', {
    params: { source_type: sourceType },
  });
  if (Array.isArray(res.data)) {
    return res.data;
  }
  return res.data.sources || res.data.items || [];
}

export async function getSource(id: string): Promise<Source> {
  const res = await apiClient.get<Source>(`/sources/${id}`);
  return res.data;
}

export async function createSource(payload: SourceCreate): Promise<Source> {
  const res = await apiClient.post<Source>('/sources', payload);
  return res.data;
}
