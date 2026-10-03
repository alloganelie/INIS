import { describe, expect, it } from 'vitest';
import { AxiosError, AxiosHeaders } from 'axios';
import { describeArtifactError } from './artifactErrors';

/** Build an axios error the way the client produces one (with a response). */
function httpError(status: number): AxiosError {
  const error = new AxiosError('request failed');
  error.response = {
    status,
    statusText: '',
    headers: {},
    config: { headers: new AxiosHeaders() },
    data: {},
  };
  return error;
}

describe('describeArtifactError (§19.3, §24.2)', () => {
  it('explains a refusal as a refusal, not as a missing file', () => {
    const described = describeArtifactError(httpError(403));
    expect(described.kind).toBe('forbidden');
    expect(described.status).toBe(403);
    expect(described.message).toContain('Accès refusé');
    expect(described.message).toContain('§19.3');
  });

  it('distinguishes "no identity" from "not allowed"', () => {
    expect(describeArtifactError(httpError(401)).kind).toBe('unauthenticated');
  });

  it('says a 404 is an unknown artifact', () => {
    const described = describeArtifactError(httpError(404));
    expect(described.kind).toBe('not_found');
    expect(described.message).toContain('introuvable');
  });

  it('explains a 503 as a missing persistence or object storage', () => {
    const described = describeArtifactError(httpError(503));
    expect(described.kind).toBe('unavailable');
    expect(described.message).toMatch(/persistance|stockage objet/);
  });

  it('names server errors by their status', () => {
    const described = describeArtifactError(httpError(500));
    expect(described.kind).toBe('server');
    expect(described.message).toContain('500');
  });

  it('tells a network failure apart from an HTTP failure', () => {
    const described = describeArtifactError(new AxiosError('Network Error'));
    expect(described.kind).toBe('network');
    expect(described.status).toBeUndefined();
    expect(described.message).toContain('injoignable');
  });

  it('never returns an empty description', () => {
    for (const error of [new Error('boom'), 'boom', undefined, null]) {
      const described = describeArtifactError(error);
      expect(described.message.length).toBeGreaterThan(0);
      expect(described.kind).toBe('unknown');
    }
  });
});
