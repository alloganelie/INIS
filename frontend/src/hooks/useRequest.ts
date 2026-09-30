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

const RUNNING_STATUSES: ReadonlySet<string> = new Set(['received', 'queued', 'processing']);

function clearState(
  setRequest: (value: InformationRequest | null) => void,
  setProgress: (value: Progress | null) => void,
): void {
  setRequest(null);
  setProgress(null);
}

export function useRequest(requestId: string | undefined): UseRequestReturn {
  const [request, setRequest] = useState<InformationRequest | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    if (!requestId) {
      clearState(setRequest, setProgress);
      setError(null);
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
        // Never leave a stale request panel under an error banner: the ID does
        // not resolve, so any previously loaded details must not stay visible.
        clearState(setRequest, setProgress);
        setError('Failed to fetch request details');
      }

      if (progData.status === 'fulfilled') {
        setProgress(progData.value);
      }
    } catch (err: unknown) {
      clearState(setRequest, setProgress);
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setIsLoading(false);
    }
  }, [requestId]);

  useEffect(() => {
    void fetchData();

    // Poll while the request is still running. Both the request details AND
    // the progress are refreshed so the status pill flips PROCESSING →
    // COMPLETED automatically as soon as the pipeline delivers (§41.1).
    const interval = setInterval(async () => {
      if (!requestId) {
        return;
      }
      const running = request ? RUNNING_STATUSES.has(request.status) : false;
      const [reqData, progData] = await Promise.allSettled([
        running ? requestsApi.getRequest(requestId) : Promise.resolve(null),
        requestsApi.getRequestProgress(requestId),
      ]);

      if (reqData.status === 'fulfilled' && reqData.value !== null) {
        setRequest(reqData.value);
      }
      if (progData.status === 'fulfilled') {
        setProgress(progData.value);
      }

      // Stop polling once the request reached a terminal state.
      const latest = reqData.status === 'fulfilled' && reqData.value !== null
        ? reqData.value
        : request;
      if (!latest || !RUNNING_STATUSES.has(latest.status)) {
        clearInterval(interval);
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [fetchData, requestId, request]);

  return { request, progress, isLoading, error, refresh: fetchData };
}
