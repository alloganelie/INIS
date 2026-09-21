import React, { createContext, useContext, useState, useEffect } from 'react';

interface TraceContextType {
  traceId: string;
  setTraceId: (id: string) => void;
  resetTraceId: () => string;
}

const TraceContext = createContext<TraceContextType | undefined>(undefined);

function generateTraceId(): string {
  const randomPart = Math.random().toString(36).substring(2, 10).toUpperCase();
  const timestampPart = Date.now().toString(36).toUpperCase();
  return `TRC_${timestampPart}${randomPart}`;
}

export const TraceProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [traceId, setTraceState] = useState<string>(() => {
    const existing = sessionStorage.getItem('inis_trace_id');
    if (existing) return existing;
    const newId = generateTraceId();
    sessionStorage.setItem('inis_trace_id', newId);
    return newId;
  });

  const setTraceId = (id: string) => {
    sessionStorage.setItem('inis_trace_id', id);
    setTraceState(id);
  };

  const resetTraceId = () => {
    const newId = generateTraceId();
    setTraceId(newId);
    return newId;
  };

  useEffect(() => {
    sessionStorage.setItem('inis_trace_id', traceId);
  }, [traceId]);

  return (
    <TraceContext.Provider value={{ traceId, setTraceId, resetTraceId }}>
      {children}
    </TraceContext.Provider>
  );
};

export const useTrace = (): TraceContextType => {
  const context = useContext(TraceContext);
  if (!context) {
    throw new Error('useTrace must be used within a TraceProvider');
  }
  return context;
};
