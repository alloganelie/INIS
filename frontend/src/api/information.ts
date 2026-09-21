import apiClient from './client';
import { InformationUnit, InformationUnitCreate } from '../types';

export interface InformationListResponse {
  units: InformationUnit[];
  items: InformationUnit[];
  total: number;
}

export async function listInformation(sourceId?: string): Promise<InformationUnit[]> {
  const res = await apiClient.get<InformationListResponse | InformationUnit[]>('/information', {
    params: { source_id: sourceId },
  });
  if (Array.isArray(res.data)) {
    return res.data;
  }
  return res.data.units || res.data.items || [];
}

export async function getInformation(id: string): Promise<InformationUnit> {
  const res = await apiClient.get<InformationUnit>(`/information/${id}`);
  return res.data;
}

export async function createInformation(payload: InformationUnitCreate): Promise<InformationUnit> {
  const res = await apiClient.post<InformationUnit>('/information', payload);
  return res.data;
}
