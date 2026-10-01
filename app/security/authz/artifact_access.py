"""§19.3 — autorisation d'accès aux artefacts livrés (§24.2).

Ce module **n'ajoute pas** de second système d'autorisation : il réutilise les
primitives existantes et se contente de leur donner le domaine « artefact ».

* l'identité est celle du middleware déjà en place
  (:mod:`app.api.middleware.auth_middleware`) : ``request.state.actor_id`` et
  ``request.state.scopes``, posés à partir d'une clé d'API ou d'un JWT — et le
  commutateur d'activation reste ``INIS_AUTH_ENABLED`` via ``is_auth_enabled()`` ;
* la décision est celle du §19.3 : ``PermissionChecker`` + ``PolicyEvaluator``
  (RBAC puis ABAC, refus inconditionnel des ressources ``restricted``), les
  mêmes classes que celles du tool ``check_permission`` (§21) ;
* ce qui est nouveau, et seulement cela, c'est la **table de rôles du domaine
  artefact** et la traduction des périmètres (``scopes``) du middleware en un de
  ces rôles. La table du tool ``check_permission`` reste vide — elle documente
  « refusé tant que l'appelant ne fournit pas de rôles réels » ; la route HTTP,
  elle, doit accepter un appelant autorisé.

Deux niveaux de contrôle, dans cet ordre :

1. **avant toute lecture** (uniquement quand l'authentification est active) :
   l'appelant possède-t-il le rôle requis ? Un refus ici est prononcé *sans*
   regarder la base, donc il ne révèle même pas qu'un artefact existe : c'est ce
   qui interdit le contournement par l'identifiant ou l'URL ;
2. **après lecture** : les règles portées par la ressource (classification
   ``restricted``, conditions ABAC) s'appliquent, y compris quand
   l'authentification est désactivée — un artefact restreint n'est jamais
   téléchargeable, ni en développement ni ailleurs.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.security.authz.abac_engine import ABACEngine
from app.security.authz.permission_checker import PermissionChecker
from app.security.authz.policy_evaluator import PolicyEvaluator
from app.security.authz.rbac_engine import RBACEngine

__all__ = [
    "ANONYMOUS_ACTOR",
    "ARTIFACT_READ_ACTION",
    "ARTIFACT_RESOURCE_TYPE",
    "ARTIFACT_ROLE_PERMISSIONS",
    "AccessDecision",
    "artifact_checker",
    "artifact_resource",
    "authorize_artifact",
    "role_for_scopes",
    "subject_from_identity",
]

#: §19.3 — le type de ressource, tel qu'il apparaît dans la décision et l'audit.
ARTIFACT_RESOURCE_TYPE = "artifact"

#: §19.3 — lire un artefact (le téléchargement est une lecture de ses octets).
ARTIFACT_READ_ACTION = "read"

#: Identité de repli quand l'authentification est désactivée (dev/CI).
#: Elle est explicite : ce n'est pas « un utilisateur », c'est « personne
#: d'identifié », et l'audit le dit tel quel.
ANONYMOUS_ACTOR = "anonymous"

#: §19.3 — rôles du domaine artefact et permissions qu'ils portent.
#: Clé ``<action>:<type_de_ressource>``, la convention de :class:`RBACEngine`.
ARTIFACT_ROLE_PERMISSIONS: Mapping[str, frozenset[str]] = {
    "artifact_reader": frozenset({"read:artifact", "search:artifact"}),
    "artifact_writer": frozenset(
        {"read:artifact", "write:artifact", "update:artifact", "search:artifact"}
    ),
    "artifact_admin": frozenset(
        {
            "read:artifact",
            "write:artifact",
            "update:artifact",
            "delete:artifact",
            "search:artifact",
        }
    ),
}

#: Traduction des périmètres du middleware en rôle du domaine artefact.
#: Le premier périmètre reconnu gagne, du plus large au plus étroit.
SCOPE_ROLES: Sequence[tuple[str, str]] = (
    ("admin", "artifact_admin"),
    ("artifact:admin", "artifact_admin"),
    ("write", "artifact_writer"),
    ("artifact:write", "artifact_writer"),
    ("read", "artifact_reader"),
    ("artifact:read", "artifact_reader"),
)

#: Classification des artefacts non sensibles : la valeur par défaut du §19.3.
DEFAULT_CLASSIFICATION = "public"


def artifact_checker() -> PermissionChecker:
    """Retourner le vérificateur §19.3 du domaine artefact.

    Même composition que le tool ``check_permission`` (§21) — RBAC + ABAC — mais
    avec la **vraie** table de rôles des artefacts. Le tool garde sa table vide
    (il documente l'absence de politique fournie) ; une route HTTP, elle, doit
    pouvoir accorder un accès légitime.
    """
    return PermissionChecker(
        PolicyEvaluator(
            RBACEngine(
                {role: set(permissions) for role, permissions in ARTIFACT_ROLE_PERMISSIONS.items()}
            ),
            ABACEngine(),
        )
    )


def role_for_scopes(scopes: Sequence[str] | None) -> str | None:
    """Traduire les périmètres d'un appelant en rôle artefact, ou ``None``.

    ``None`` n'est pas « accès refusé par la politique » mais « rôle inconnu » :
    l'appelant est identifié, il n'a simplement pas de rôle artefact, et un
    appelant identifié sans rôle est refusé quand l'authentification est active.
    """
    available = {str(scope).strip().lower() for scope in (scopes or []) if str(scope).strip()}
    for scope, role in SCOPE_ROLES:
        if scope in available:
            return role
    return None


def subject_from_identity(
    actor_id: str | None, scopes: Sequence[str] | None
) -> dict[str, Any]:
    """Construire le sujet §19.3 à partir de l'identité posée par le middleware."""
    resolved_actor = str(actor_id).strip() if actor_id else ""
    subject: dict[str, Any] = {
        "agent_id": resolved_actor or ANONYMOUS_ACTOR,
        "actor_id": resolved_actor or ANONYMOUS_ACTOR,
        "scopes": list(scopes or []),
    }
    role = role_for_scopes(scopes)
    if role is not None:
        subject["role"] = role
    return subject


def artifact_resource(record: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Décrire l'artefact comme ressource §19.3 (attributs ABAC compris).

    Aucun attribut n'est inventé : ``classification`` vient de l'enregistrement
    quand il la porte (un artefact classé ``confidential`` hérite du classement
    de sa livraison), sinon il est ``public`` — la valeur du §19.3. Les
    conditions ABAC sont celles que l'enregistrement expose sous ``conditions``,
    ce qui permet d'exprimer « même ``request_id`` » ou « même propriétaire »
    sans écrire une seconde logique d'autorisation.
    """
    resource: dict[str, Any] = {"type": ARTIFACT_RESOURCE_TYPE}
    if record is None:
        return resource
    item = dict(record)
    resource["classification"] = (
        str(item.get("classification") or DEFAULT_CLASSIFICATION).strip().lower()
        or DEFAULT_CLASSIFICATION
    )
    for field in ("artifact_id", "request_id", "artifact_type", "status", "owner_id"):
        value = item.get(field)
        if value not in (None, ""):
            resource[field] = value
    resource["sha256_length"] = len(str(item.get("sha256") or ""))
    conditions = item.get("conditions")
    if isinstance(conditions, Mapping):
        resource["conditions"] = dict(conditions)
    return resource


@dataclass(frozen=True)
class AccessDecision:
    """Décision d'accès : accordée ou refusée, avec la raison §19.3."""

    allowed: bool
    reason: str
    action: str = ARTIFACT_READ_ACTION
    resource_type: str = ARTIFACT_RESOURCE_TYPE

    def to_audit_reason(self) -> str:
        """Return the reason as it must be audited (never sent to the caller)."""
        return self.reason


def authorize_artifact(
    subject: Mapping[str, Any],
    record: Mapping[str, Any] | None = None,
    *,
    action: str = ARTIFACT_READ_ACTION,
    checker: PermissionChecker | None = None,
    require_role: bool = False,
) -> AccessDecision:
    """Décider §19.3 de l'accès d'un sujet à un artefact.

    Args:
        subject: Sujet §19.3 (``agent_id``, ``scopes``, ``role`` éventuel).
        record: Enregistrement de l'artefact, ou ``None`` pour un contrôle
            prononcé **avant** lecture (aucun attribut de ressource n'est alors
            connu, et rien n'est lu : le refus ne peut rien révéler).
        action: Action §19.3 (``read`` pour un téléchargement).
        checker: Vérificateur injecté (tests, politique fournie par le
            déployeur) ; par défaut :meth:`artifact_checker`.
        require_role: Exiger la présence d'un rôle artefact. La route HTTP
            l'active quand l'authentification est configurée : un appelant
            identifié mais sans rôle artefact est alors refusé, au lieu de
            passer par le seul ABAC.
    """
    if require_role and not subject.get("role"):
        scopes = ", ".join(str(scope) for scope in subject.get("scopes") or []) or "aucun"
        return AccessDecision(
            allowed=False,
            reason=(
                f"Subject '{subject.get('agent_id')}' has no artifact role "
                f"(scopes: {scopes}) — §19.3"
            ),
            action=action,
        )

    active = checker if checker is not None else artifact_checker()
    decision, reason = active.check(
        {k: v for k, v in subject.items() if k != "role"},
        artifact_resource(record),
        action,
        subject.get("role"),
    )
    return AccessDecision(allowed=decision == "allow", reason=reason, action=action)
