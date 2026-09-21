/**
 * MSW request handlers mocking the INIS API v1 for frontend development.
 * Covers the endpoints used by src/api/* with fixture-backed responses.
 */
import { http, HttpResponse } from 'msw';
import type { SourceCreate } from '../types';
import {
  mockConflicts,
  mockConfidenceScores,
  mockInformationUnits,
  mockProgress,
  mockSources,
  mockTokenResponse,
} from './fixtures';

const sources: typeof mockSources = [...mockSources];

export const handlers = [
  // GET /v1/sources — list sources (src/api/sources.ts)
  http.get('/v1/sources', () => {
    return HttpResponse.json(sources);
  }),

  // POST /v1/sources — create a source (echo + generated id)
  http.post('/v1/sources', async ({ request }) => {
    const body = (await request.json()) as SourceCreate;
    const created = {
      source_id: `SRC_mock${String(sources.length + 1).padStart(3, '0')}`,
      name: body.name,
      source_type: body.source_type,
      url: body.url ?? null,
      description: body.description ?? null,
      trust_level: body.trust_level ?? 5,
      status: body.status ?? 'active',
      metadata: body.metadata ?? {},
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    sources.push(created);
    return HttpResponse.json(created, { status: 201 });
  }),

  // GET /v1/information/:id — single InformationUnit (src/api/information.ts)
  http.get('/v1/information/:id', ({ params }) => {
    const unit = mockInformationUnits.find((u) => u.information_id === params.id);
    if (!unit) {
      return HttpResponse.json({ detail: `Information ${params.id} not found` }, { status: 404 });
    }
    return HttpResponse.json(unit);
  }),

  // GET /v1/requests/:id/progress — request progress (src/api/requests.ts)
  http.get('/v1/requests/:id/progress', ({ params }) => {
    return HttpResponse.json({ request_id: params.id, ...mockProgress });
  }),

  // POST /v1/auth/login — mock login (src/api/auth.ts)
  http.post('/v1/auth/login', async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as {
      username?: string;
      password?: string;
    };
    if (!body.username || !body.password) {
      return HttpResponse.json({ detail: 'Missing username or password' }, { status: 422 });
    }
    return HttpResponse.json(mockTokenResponse);
  }),

  // GET /v1/confidence/:id — confidence score by information id (src/api/requests.ts)
  http.get('/v1/confidence/:id', ({ params }) => {
    const score = mockConfidenceScores.find((c) => c.information_id === params.id);
    if (!score) {
      return HttpResponse.json({ detail: `Confidence ${params.id} not found` }, { status: 404 });
    }
    return HttpResponse.json(score);
  }),

  // GET /v1/conflicts — list conflicts (src/api/conflicts.ts)
  http.get('/v1/conflicts', () => {
    return HttpResponse.json(mockConflicts);
  }),
];
