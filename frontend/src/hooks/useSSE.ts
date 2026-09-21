import { useState, useEffect } from 'react';

interface UseSSEResult<T> {
  data: T | null;
  events: T[];
  readyState: number;
  error: Event | null;
  close: () => void;
}

export function useSSE<T = unknown>(url: string | null): UseSSEResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [events, setEvents] = useState<T[]>([]);
  const [readyState, setReadyState] = useState<number>(0);
  const [error, setError] = useState<Event | null>(null);
  const [eventSource, setEventSource] = useState<EventSource | null>(null);

  useEffect(() => {
    if (!url) {
      return;
    }

    const es = new EventSource(url);
    setEventSource(es);
    setReadyState(es.readyState);

    es.onopen = () => {
      setReadyState(es.readyState);
      setError(null);
    };

    es.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data);
        setData(parsed);
        setEvents((prev) => [...prev, parsed]);
      } catch {
        setData(event.data as unknown as T);
        setEvents((prev) => [...prev, event.data as unknown as T]);
      }
    };

    es.onerror = (err) => {
      setError(err);
      setReadyState(es.readyState);
    };

    return () => {
      es.close();
    };
  }, [url]);

  const close = () => {
    if (eventSource) {
      eventSource.close();
      setReadyState(EventSource.CLOSED);
    }
  };

  return { data, events, readyState, error, close };
}
