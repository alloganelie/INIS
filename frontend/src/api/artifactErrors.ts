import axios from 'axios';

/**
 * What a failed artifact call means **for the reader**, not for the machine.
 *
 * The frontend must never turn a refusal into an empty list or an empty file:
 * `§37 signaler > inventer` and the L1 pitfall P10 both say so. This module is
 * therefore the single place that translates a transport failure into a
 * sentence a human can act on, and it never returns an empty value — an error
 * always becomes a described error.
 */
export type ArtifactErrorKind =
  | 'unauthenticated'
  | 'forbidden'
  | 'not_found'
  | 'unavailable'
  | 'server'
  | 'network'
  | 'unknown';

export interface ArtifactViewError {
  kind: ArtifactErrorKind;
  status?: number;
  /** The sentence the UI shows. Explicit, never generic when it can be precise. */
  message: string;
}

/** Describe one failed artifact call for display (and for the UI tests). */
export function describeArtifactError(error: unknown): ArtifactViewError {
  if (axios.isAxiosError(error)) {
    const status = error.response?.status;
    if (status === 401) {
      return {
        kind: 'unauthenticated',
        status,
        message: "Authentification requise : aucune identité valide n'a été fournie (§19.2).",
      };
    }
    if (status === 403) {
      return {
        kind: 'forbidden',
        status,
        message:
          "Accès refusé : votre rôle ne permet pas de lire cet artefact (§19.3). " +
          "Le refus est enregistré dans l'audit.",
      };
    }
    if (status === 404) {
      return {
        kind: 'not_found',
        status,
        message: "Artefact introuvable : cet identifiant n'a jamais été livré.",
      };
    }
    if (status === 503) {
      return {
        kind: 'unavailable',
        status,
        message:
          "Artefact non disponible : sa persistance ou son stockage objet n'est pas " +
          'configuré sur cette instance.',
      };
    }
    if (status !== undefined && status >= 500) {
      return {
        kind: 'server',
        status,
        message: `Erreur serveur (${status}) : la demande n'a pas pu aboutir.`,
      };
    }
    if (status === undefined) {
      return {
        kind: 'network',
        message:
          "Serveur injoignable : la requête n'a pas reçu de réponse. " +
          'Vérifiez la connexion puis réessayez.',
      };
    }
    return {
      kind: 'unknown',
      status,
      message: `Échec de la lecture de l'artefact (HTTP ${status}).`,
    };
  }
  return {
    kind: 'unknown',
    message:
      error instanceof Error
        ? `Échec de la lecture de l'artefact : ${error.message}`
        : "Échec de la lecture de l'artefact pour une raison inconnue.",
  };
}
