import apiClient from './client';
import {
  InformationRequest,
  InformationRequestCreate,
  Progress,
  ConfidenceMatrix,
} from '../types';

export async function createRequest(
  payload: InformationRequestCreate
): Promise<InformationRequest> {
  const res = await apiClient.post<InformationRequest>('/requests', payload);
  // Also store in localStorage to enable client-side history if desired
  try {
    const existingRaw = localStorage.getItem('inis_requests_history');
    const existing: InformationRequest[] = existingRaw ? JSON.parse(existingRaw) : [];
    existing.unshift(res.data);
    localStorage.setItem('inis_requests_history', JSON.stringify(existing.slice(0, 50)));
  } catch {
    // Ignore storage issues
  }
  return res.data;
}

export async function getRequest(id: string): Promise<InformationRequest> {
  const res = await apiClient.get<InformationRequest>(`/requests/${id}`);
  return res.data;
}

export async function getRequestProgress(id: string): Promise<Progress> {
  const res = await apiClient.get<Progress>(`/requests/${id}/progress`);
  return res.data;
}

export async function getConfidenceMatrix(requestId: string): Promise<ConfidenceMatrix> {
  const res = await apiClient.get<ConfidenceMatrix>(`/confidence/matrix/${requestId}`);
  return res.data;
}

export async function listRequests(): Promise<InformationRequest[]> {
  try {
    const res = await apiClient.get<InformationRequest[] | { items: InformationRequest[] }>('/requests');
    if (Array.isArray(res.data)) {
      return res.data;
    }
    if (res.data && 'items' in res.data) {
      return res.data.items;
    }
  } catch {
    // Fallback to local stored history if backend list is not implemented
  }

  const existingRaw = localStorage.getItem('inis_requests_history');
  return existingRaw ? JSON.parse(existingRaw) : [];
}
