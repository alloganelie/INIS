import { useState, useEffect, useCallback } from 'react';
import { InformationRequest, Progress } from '../types';
import * as requestsApi from '../api/requests';

interface UseRequestReturn {
  request: InformationRequest | null;
  progress: Progress | null;
  isLoading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

export function useRequest(requestId: string | undefined): UseRequestReturn {
  const [request, setRequest] = useState<InformationRequest | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    if (!requestId) {
      setRequest(null);
      setProgress(null);
      setIsLoading(false);
      return;
    }

    try {
      const [reqData, progData] = await Promise.allSettled([
        requestsApi.getRequest(requestId),
        requestsApi.getRequestProgress(requestId),
      ]);

      if (reqData.status === 'fulfilled') {
        setRequest(reqData.value);
        setError(null);
      } else {
        setError('Failed to fetch request details');
      }

      if (progData.status === 'fulfilled') {
        setProgress(progData.value);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setIsLoading(false);
    }
  }, [requestId]);

  useEffect(() => {
    fetchData();

    // Auto-poll progress while request is still running
    const interval = setInterval(() => {
      if (requestId && request && ['received', 'queued', 'processing'].includes(request.status)) {
        requestsApi
          .getRequestProgress(requestId)
          .then(setProgress)
          .catch(() => {});
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [fetchData, requestId, request]);

  return { request, progress, isLoading, error, refresh: fetchData };
}
