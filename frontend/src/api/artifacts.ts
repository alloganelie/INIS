import axios from 'axios';
import apiClient from './client';
import { Artifact, ArtifactLineageView, ArtifactVersionList } from '../types';

/**
 * The §24.2 record exactly as the backend exposes it.
 *
 * NAMING.md §3: the backend stays canonical (`file_name`, `mime_type`,
 * `storage_ref`) and the frontend maps explicitly. The mapping lives in this
 * file only, so a backend rename can only break this file.
 */
export interface ApiArtifact {
  artifact_id: string;
  request_id?: string | null;
  artifact_type: string;
  file_name: string;
  mime_type: string;
  version?: string;
  size_bytes?: number | null;
  sha256?: string;
  storage_ref?: string;
  status?: string;
  created_at?: string | null;
}

/** Map one canonical §24.2 record onto the frontend `Artifact` shape. */
export function toArtifact(record: ApiArtifact): Artifact {
  return {
    artifact_id: record.artifact_id,
    request_id: record.request_id ?? null,
    name: record.file_name,
    artifact_type: record.artifact_type,
    size_bytes: record.size_bytes ?? undefined,
    content_type: record.mime_type,
    url: `/v1/artifacts/${record.artifact_id}/download`,
    created_at: record.created_at ?? null,
  };
}

/**
 * List the files INIS delivered for a request (§24.2).
 *
 * Only a 404 is turned into an empty list: it means the request identifier is
 * unknown. Every other failure propagates. The previous
 * `catch { return [] }` hid a missing endpoint behind an empty result
 * (conformance plan, pitfall P10) — the difference between "no artifact" and
 * "cannot ask" has to stay visible.
 */
export async function listArtifacts(requestId?: string): Promise<Artifact[]> {
  try {
    const res = await apiClient.get<{ artifacts: ApiArtifact[] }>('/artifacts', {
      params: { request_id: requestId },
    });
    return (res.data.artifacts ?? []).map(toArtifact);
  } catch (error: unknown) {
    if (axios.isAxiosError(error) && error.response?.status === 404) {
      return [];
    }
    throw error;
  }
}

/** Fetch one delivered artifact, or `null` when no such artifact exists. */
export async function getArtifact(id: string): Promise<Artifact | null> {
  try {
    const res = await apiClient.get<ApiArtifact>(`/artifacts/${id}`);
    return toArtifact(res.data);
  } catch (error: unknown) {
    if (axios.isAxiosError(error) && error.response?.status === 404) {
      return null;
    }
    throw error;
  }
}

/**
 * The version history of one artifact (§18.1).
 *
 * Only a 404 is turned into `null` — the artifact was never delivered. Every
 * other failure propagates, for the same reason as in `listArtifacts`: a
 * refused or broken history must not be rendered as "this artifact has no
 * version".
 */
export async function listArtifactVersions(
  id: string,
): Promise<ArtifactVersionList | null> {
  try {
    const res = await apiClient.get<ArtifactVersionList>(`/artifacts/${id}/versions`);
    return res.data;
  } catch (error: unknown) {
    if (axios.isAxiosError(error) && error.response?.status === 404) {
      return null;
    }
    throw error;
  }
}

/**
 * The lineage and deliveries of one artifact: `source → … → download` (§24.2/§24.3).
 *
 * Same rule as above: a 404 means the artifact does not exist, anything else
 * propagates to the caller, which is what lets the panel say *why* it could not
 * read the chain instead of showing an empty one.
 */
export async function getArtifactLineage(
  id: string,
): Promise<ArtifactLineageView | null> {
  try {
    const res = await apiClient.get<ArtifactLineageView>(`/artifacts/${id}/lineage`);
    return res.data;
  } catch (error: unknown) {
    if (axios.isAxiosError(error) && error.response?.status === 404) {
      return null;
    }
    throw error;
  }
}

/**
 * Download the bytes of one artifact (§24.2, §19.3).
 *
 * Nothing is caught here on purpose: the caller renders the refusal it gets
 * (`describeArtifactError`) instead of receiving an empty file. A `403` must
 * reach the UI — the whole point of §19.3 is that the refusal is visible.
 */
export async function downloadArtifact(id: string): Promise<Blob> {
  const res = await apiClient.get(`/artifacts/${id}/download`, {
    responseType: 'blob',
  });
  return res.data as Blob;
}
