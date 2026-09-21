import apiClient from './client';
import { Artifact } from '../types';

export async function listArtifacts(requestId?: string): Promise<Artifact[]> {
  try {
    const res = await apiClient.get<Artifact[] | { artifacts: Artifact[] }>('/artifacts', {
      params: { request_id: requestId },
    });
    if (Array.isArray(res.data)) {
      return res.data;
    }
    return (res.data as { artifacts?: Artifact[] }).artifacts || [];
  } catch {
    // Fallback if artifacts endpoint is not yet mounted
    return [];
  }
}

export async function getArtifact(id: string): Promise<Artifact | null> {
  try {
    const res = await apiClient.get<Artifact>(`/artifacts/${id}`);
    return res.data;
  } catch {
    return null;
  }
}
