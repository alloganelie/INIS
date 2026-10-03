import React, { useCallback, useEffect, useState } from 'react';
import { Artifact, ArtifactVersionList } from '../types';
import { ArtifactViewError, describeArtifactError } from '../api/artifactErrors';
import { downloadArtifact, listArtifactVersions, listArtifacts } from '../api/artifacts';

/**
 * §24.2/§18.1/§19.3 — the delivered files of one request, their version, and the
 * refusal when there is one.
 *
 * The panel consumes the existing contracts (`/v1/artifacts`,
 * `/v1/artifacts/{id}/versions`, `/v1/artifacts/{id}/download`) and rebuilds no
 * business rule: the version shown is the one the backend says is current, the
 * filename is the backend one, and the reason a call failed is rendered as it
 * comes back from `describeArtifactError`.
 *
 * Two rules are explicit because they are what this panel exists for:
 *
 * * **no silent catch** — a failure becomes a visible notice, never an empty
 *   list that would read as "this request produced nothing";
 * * a **refusal is information** — a 403 says the caller may not read the file,
 *   a 503 says this instance cannot serve it; both are shown, not hidden.
 */
interface Props {
  requestId: string;
}

export interface ArtifactsPanelState {
  artifacts: Artifact[];
  versions: Record<string, ArtifactVersionList | null>;
  loading: boolean;
  error: ArtifactViewError | null;
  notices: string[];
}

/** Human-readable size, or the fact that the backend did not state one. */
export function formatSize(size?: number): string {
  if (size === undefined || size === null) return 'taille non communiquée';
  if (size < 1024) return `${size} octets`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} Kio`;
  return `${(size / (1024 * 1024)).toFixed(1)} Mio`;
}

/** The version shown for one artifact: the current one, or the honest absence. */
export function currentVersionOf(history: ArtifactVersionList | null): string {
  if (!history) return 'historique indisponible';
  if (history.current_version) return history.current_version;
  return history.versions.length === 0
    ? 'aucune version enregistrée'
    : 'version courante non déclarée';
}

export default function ArtifactsPanel({ requestId }: Props) {
  const [state, setState] = useState<ArtifactsPanelState>({
    artifacts: [],
    versions: {},
    loading: true,
    error: null,
    notices: [],
  });

  const load = useCallback(async () => {
    setState((previous) => ({ ...previous, loading: true, error: null, notices: [] }));
    try {
      const artifacts = await listArtifacts(requestId);
      const histories: Record<string, ArtifactVersionList | null> = {};
      const notices: string[] = [];
      for (const artifact of artifacts) {
        try {
          histories[artifact.artifact_id] = await listArtifactVersions(artifact.artifact_id);
        } catch (versionError: unknown) {
          // L'historique est un second fait : son échec est dit sans masquer
          // l'artefact qui, lui, a bien été listé.
          const described = describeArtifactError(versionError);
          histories[artifact.artifact_id] = null;
          notices.push(`Historique de ${artifact.name} : ${described.message}`);
        }
      }
      setState({ artifacts, versions: histories, loading: false, error: null, notices });
    } catch (error: unknown) {
      setState({
        artifacts: [],
        versions: {},
        loading: false,
        error: describeArtifactError(error),
        notices: [],
      });
    }
  }, [requestId]);

  useEffect(() => {
    void load();
  }, [load]);

  const onDownload = useCallback(async (artifact: Artifact) => {
    try {
      const blob = await downloadArtifact(artifact.artifact_id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = artifact.name;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error: unknown) {
      const described = describeArtifactError(error);
      setState((previous) => ({
        ...previous,
        notices: [
          ...previous.notices,
          `Téléchargement de ${artifact.name} : ${described.message}`,
        ],
      }));
    }
  }, []);

  if (state.loading) {
    return (
      <section className="artifacts-panel" aria-busy="true">
        <h3>Artefacts</h3>
        <p>Chargement des artefacts livrés…</p>
      </section>
    );
  }

  return (
    <section className="artifacts-panel">
      <h3>Artefacts</h3>
      {state.error && (
        <p className="artifact-error" role="alert">
          {state.error.message}
        </p>
      )}
      {state.notices.length > 0 && (
        <ul className="artifact-notices" role="alert">
          {state.notices.map((notice) => (
            <li key={notice}>{notice}</li>
          ))}
        </ul>
      )}
      {!state.error && state.artifacts.length === 0 && (
        <p>
          Aucun artefact livré pour cette demande : la demande a peut-être été refusée, ou son
          exécution n&apos;a produit aucun fichier.
        </p>
      )}
      {state.artifacts.length > 0 && (
        <table className="artifact-table">
          <thead>
            <tr>
              <th>Fichier</th>
              <th>Type</th>
              <th>Statut</th>
              <th>Taille</th>
              <th>Version</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {state.artifacts.map((artifact) => (
              <tr key={artifact.artifact_id}>
                <td>{artifact.name}</td>
                <td>{artifact.artifact_type}</td>
                <td>
                  {(artifact as Artifact & { status?: string }).status ??
                    'statut non communiqué'}
                </td>
                <td>{formatSize(artifact.size_bytes)}</td>
                <td>{currentVersionOf(state.versions[artifact.artifact_id] ?? null)}</td>
                <td>
                  <button type="button" onClick={() => void onDownload(artifact)}>
                    Télécharger
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p>
        <button type="button" onClick={() => void load()}>
          Rafraîchir
        </button>
      </p>
    </section>
  );
}
