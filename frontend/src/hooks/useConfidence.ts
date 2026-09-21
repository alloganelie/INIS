import { useState, useEffect } from 'react';
import apiClient from '../api/client';
import { ConfidenceScore } from '../types';

export function useConfidence(informationId: string | undefined) {
  const [confidence, setConfidence] = useState<ConfidenceScore | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!informationId) {
      setConfidence(null);
      return;
    }

    setIsLoading(true);
    apiClient
      .get<ConfidenceScore>(`/confidence/${informationId}`)
      .then((res) => {
        setConfidence(res.data);
        setError(null);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : 'Failed to fetch confidence score');
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [informationId]);

  return { confidence, isLoading, error };
}
