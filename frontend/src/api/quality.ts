import apiClient from './client';
import { QualityReport, QualityCheckResult } from '../types';

export interface QualityCheckResponse {
  target_id: string;
  passed: boolean;
  overall_score: number;
  checks: QualityCheckResult[];
  timestamp?: string;
}

export async function runQualityCheck(
  targetId: string,
  checks?: string[]
): Promise<QualityCheckResponse> {
  const res = await apiClient.post<QualityCheckResponse>('/quality/check', {
    target_id: targetId,
    checks: checks || [],
  });
  return res.data;
}

export async function getQualityReport(targetId: string): Promise<QualityReport> {
  const res = await apiClient.get<QualityReport>(`/quality/report/${targetId}`);
  return res.data;
}
