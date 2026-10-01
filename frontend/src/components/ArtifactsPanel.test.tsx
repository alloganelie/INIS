import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { AxiosError, AxiosHeaders } from 'axios';
import ArtifactsPanel, { currentVersionOf, formatSize } from './ArtifactsPanel';
import { Artifact, ArtifactVersionList } from '../types';

const listArtifacts = vi.fn();
const listArtifactVersions = vi.fn();
const downloadArtifact = vi.fn();

vi.mock('../api/artifacts', () => ({
  listArtifacts: (...args: unknown[]) => listArtifacts(...args),
  listArtifactVersions: (...args: unknown[]) => listArtifactVersions(...args),
  downloadArtifact: (...args: unknown[]) => downloadArtifact(...args),
}));

/** One artifact as the API returns it after the §24.2 mapping. */
const ARTIFACT: Artifact = {
  artifact_id: 'ART_2026_900001',
  request_id: 'REQ_01M3T0000000000000000000001',
  name: 'colis.csv',
  artifact_type: 'dataset',
  size_bytes: 2048,
  content_type: 'text/csv',
  created_at: '2026-09-30T00:00:00+00:00',
};

const HISTORY: ArtifactVersionList = {
  artifact_id: ARTIFACT.artifact_id,
  current_version: '1.1.0',
  versions: [
    {
      artifact_version_id: 'AV_ART_2026_900001_1.0.0',
      artifact_id: ARTIFACT.artifact_id,
      version: '1.0.0',
      metadata: { information_ids: ['INF_1'] },
    },
    {
      artifact_version_id: 'AV_ART_2026_900001_1.1.0',
      artifact_id: ARTIFACT.artifact_id,
      version: '1.1.0',
      metadata: { information_ids: ['INF_2'], supersedes: 'AV_ART_2026_900001_1.0.0' },
    },
  ],
};

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

describe('ArtifactsPanel (§24.2, §18.1, §19.3)', () => {
  beforeEach(() => {
    listArtifacts.mockReset();
    listArtifactVersions.mockReset();
    downloadArtifact.mockReset();
  });

  it('lists the delivered files with their status, size and current version', async () => {
    listArtifacts.mockResolvedValue([{ ...ARTIFACT, status: 'available' }]);
    listArtifactVersions.mockResolvedValue(HISTORY);

    render(<ArtifactsPanel requestId={ARTIFACT.request_id!} />);

    expect(await screen.findByText('colis.csv')).toBeTruthy();
    expect(screen.getByText('dataset')).toBeTruthy();
    expect(screen.getByText('2.0 Kio')).toBeTruthy();
    expect(screen.getByText('1.1.0')).toBeTruthy();
    expect(listArtifactVersions).toHaveBeenCalledWith(ARTIFACT.artifact_id);
  });

  it('shows a refused download instead of swallowing it', async () => {
    listArtifacts.mockResolvedValue([ARTIFACT]);
    listArtifactVersions.mockResolvedValue(HISTORY);
    downloadArtifact.mockRejectedValue(httpError(403));

    render(<ArtifactsPanel requestId={ARTIFACT.request_id!} />);
    const button = await screen.findByRole('button', { name: 'Télécharger' });
    button.click();

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('Accès refusé');
    expect(alert.textContent).toContain('colis.csv');
  });

  it('states a listing failure instead of rendering an empty list', async () => {
    listArtifacts.mockRejectedValue(httpError(500));

    render(<ArtifactsPanel requestId={ARTIFACT.request_id!} />);

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('Erreur serveur');
    expect(screen.queryByText(/Aucun artefact livré/)).toBeNull();
  });

  it('tells an empty delivery apart from a failure', async () => {
    listArtifacts.mockResolvedValue([]);

    render(<ArtifactsPanel requestId={ARTIFACT.request_id!} />);

    expect(await screen.findByText(/Aucun artefact livré/)).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('reports a failed history without hiding the artifact itself', async () => {
    listArtifacts.mockResolvedValue([ARTIFACT]);
    listArtifactVersions.mockRejectedValue(httpError(503));

    render(<ArtifactsPanel requestId={ARTIFACT.request_id!} />);

    expect(await screen.findByText('colis.csv')).toBeTruthy();
    const notice = screen.getByText(/Historique de colis.csv/);
    expect(notice.textContent).toContain('non disponible');
    expect(screen.getByText('historique indisponible')).toBeTruthy();
  });

  it('downloads the authorized file through the API contract', async () => {
    listArtifacts.mockResolvedValue([ARTIFACT]);
    listArtifactVersions.mockResolvedValue(HISTORY);
    downloadArtifact.mockResolvedValue(new Blob(['a,b\n1,2\n'], { type: 'text/csv' }));
    const createObjectURL = vi.fn(() => 'blob:colis');
    const revokeObjectURL = vi.fn();
    Object.assign(URL, { createObjectURL, revokeObjectURL });
    // jsdom has no navigation: the click is observed, not performed.
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => undefined);

    render(<ArtifactsPanel requestId={ARTIFACT.request_id!} />);
    const button = await screen.findByRole('button', { name: 'Télécharger' });
    button.click();

    await waitFor(() => expect(downloadArtifact).toHaveBeenCalledWith(ARTIFACT.artifact_id));
    await waitFor(() => expect(createObjectURL).toHaveBeenCalled());
    expect(click).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:colis');
    expect(screen.queryByRole('alert')).toBeNull();
    click.mockRestore();
  });
});

describe('ArtifactsPanel helpers', () => {
  it('formats sizes, including the absence of one', () => {
    expect(formatSize(undefined)).toBe('taille non communiquée');
    expect(formatSize(512)).toBe('512 octets');
    expect(formatSize(1024 * 1024 * 3)).toBe('3.0 Mio');
  });

  it('never invents a version', () => {
    expect(currentVersionOf(HISTORY)).toBe('1.1.0');
    expect(currentVersionOf(null)).toBe('historique indisponible');
    expect(currentVersionOf({ artifact_id: 'x', versions: [] })).toBe(
      'aucune version enregistrée',
    );
    expect(currentVersionOf({ artifact_id: 'x', versions: HISTORY.versions })).toBe(
      'version courante non déclarée',
    );
  });
});
