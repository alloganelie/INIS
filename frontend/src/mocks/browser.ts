/// <reference types="vite/client" />
/**
 * MSW browser worker setup for local frontend development.
 * Only started when VITE_USE_MOCKS=true (see README.md).
 */
import { setupWorker } from 'msw/browser';
import { handlers } from './server';

export const worker = setupWorker(...handlers);

export async function enableMocks(): Promise<void> {
  if (import.meta.env.DEV) {
    await worker.start({ onUnhandledRequest: 'bypass' });
    console.info('[msw] Mock Service Worker enabled (VITE_USE_MOCKS=true).');
  }
}
