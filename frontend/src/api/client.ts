import axios from 'axios';

/**
 * Axios client for INIS API v1.
 * Default baseURL is /v1 which proxies to the backend in development.
 */
export const apiClient = axios.create({
  baseURL: '/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Interceptor to inject Auth token, API Key, and Trace ID
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('inis_token');
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  const apiKey = localStorage.getItem('inis_api_key');
  if (apiKey && config.headers) {
    config.headers['X-API-Key'] = apiKey;
  }

  const traceId = sessionStorage.getItem('inis_trace_id');
  if (traceId && config.headers) {
    config.headers['X-Trace-Id'] = traceId;
  }

  return config;
});

export default apiClient;
