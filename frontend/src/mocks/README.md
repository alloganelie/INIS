# Frontend mocks (MSW)

Mock Service Worker handlers + fixtures for local frontend development without a backend.

## Files

- `fixtures.ts` — test data: 3 sources, 5 information units, 2 conflicts,
  3 evidence items, 3 agents, 2 requests, 2 confidence scores.
- `server.ts` — MSW `handlers` for the API v1 endpoints.
- `browser.ts` — `setupWorker` + `enableMocks()` for dev.

## Mocked endpoints

- `GET /v1/sources`, `POST /v1/sources`
- `GET /v1/information/:id`
- `GET /v1/requests/:id/progress`
- `POST /v1/auth/login`
- `GET /v1/confidence/:id`
- `GET /v1/conflicts`

## Enable mocks

1. Install dependencies (includes the `msw` devDependency):

   ```powershell
   cd frontend
   npm install
   ```

2. Generate the service-worker script (once, after installing `msw`):

   ```powershell
   npx msw init public/ --save
   ```

3. Start the dev server with mocks enabled:

   ```powershell
   $env:VITE_USE_MOCKS = "true"; npm run dev
   ```

   On Linux/macOS:

   ```sh
   VITE_USE_MOCKS=true npm run dev
   ```

4. Wire the worker in `src/main.tsx` (before rendering):

   ```tsx
   async function bootstrap() {
     if (import.meta.env.VITE_USE_MOCKS === 'true') {
       const { enableMocks } = await import('./mocks/browser');
       await enableMocks();
     }
     const { default: App } = await import('./App');
     // ... render <App />
   }
   void bootstrap();
   ```

## Disable mocks

Unset the flag (or set it to anything other than `"true"`) and restart Vite —
requests to `/v1/*` then go through `vite.config.ts` proxy to the backend again.
