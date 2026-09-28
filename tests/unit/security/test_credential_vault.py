"""Unit tests for the §41.4 credential vault and source credentials."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.security.vault.credential_vault import (
    AUTH_TYPES,
    REDACTED,
    CredentialNotFound,
    CredentialResolver,
    EnvVault,
    FileVault,
    SourceCredential,
    VaultError,
    redact,
)

SRC = "SRC_01ARZ3NDEKTSV4RRFFQ69G5F01"


@pytest.fixture()
def vault(tmp_path: Path) -> FileVault:
    return FileVault(tmp_path / "vault.json", master_key="unit-test-master-key")


def test_auth_types_match_the_spec() -> None:
    assert AUTH_TYPES == ("oauth2", "api_key", "basic", "certificate", "none")


def test_redact_masks_nested_secrets() -> None:
    payload = {
        "user": "alice",
        "password": "hunter2",
        "nested": {"api_key": "k", "safe": 1},
        "items": [{"access_token": "t"}],
    }
    cleaned = redact(payload)
    assert cleaned["password"] == REDACTED
    assert cleaned["nested"]["api_key"] == REDACTED
    assert cleaned["nested"]["safe"] == 1
    assert cleaned["items"][0]["access_token"] == REDACTED
    assert cleaned["user"] == "alice"


def test_redact_keeps_non_secret_payloads_untouched() -> None:
    payload = {"source_id": SRC, "count": 3, "tags": ["a", "b"]}
    assert redact(payload) == payload


def test_env_vault_roundtrip() -> None:
    environ: dict[str, str] = {}
    vault = EnvVault(environ)
    vault.set("src/alpha", {"api_key": "k-1"})
    assert vault.get("src/alpha") == {"api_key": "k-1"}
    # Env var names cannot contain '/', so refs are listed in sanitized form;
    # every accessor re-applies the same sanitization, so they round-trip.
    assert vault.list_refs() == ["src_alpha"]
    assert vault.get("src_alpha") == {"api_key": "k-1"}
    assert json.loads(environ["INIS_CRED_SRC_ALPHA"]) == {"api_key": "k-1"}


def test_env_vault_missing_ref_raises() -> None:
    with pytest.raises(CredentialNotFound):
        EnvVault({}).get("src/unknown")


def test_env_vault_invalid_json_raises_vault_error() -> None:
    with pytest.raises(VaultError, match="not valid JSON"):
        EnvVault({"INIS_CRED_SRC_ALPHA": "{oops"}).get("src/alpha")


def test_env_vault_delete_and_rotate() -> None:
    environ: dict[str, str] = {}
    vault = EnvVault(environ)
    vault.set("a", {"api_key": "1"})
    vault.rotate("a", {"api_key": "2"})
    assert vault.get("a")["api_key"] == "2"
    assert vault.delete("a") is True
    assert vault.delete("a") is False


def test_file_vault_requires_a_master_key(tmp_path: Path) -> None:
    with pytest.raises(VaultError, match="master key"):
        FileVault(tmp_path / "v.json", master_key="")


def test_file_vault_never_writes_the_secret_in_clear(vault: FileVault) -> None:
    vault.set("src/alpha", {"api_key": "SUPER-SECRET"})
    raw = vault._path.read_text(encoding="utf-8")
    assert "SUPER-SECRET" not in raw
    assert vault.is_encrypted is True
    assert "fernet:" in raw


def test_file_vault_roundtrip_and_persistence(vault: FileVault) -> None:
    vault.set("src/alpha", {"api_key": "SUPER-SECRET"})
    assert vault.get("src/alpha") == {"api_key": "SUPER-SECRET"}

    reloaded = FileVault(vault._path, master_key="unit-test-master-key")
    assert reloaded.get("src/alpha")["api_key"] == "SUPER-SECRET"
    assert reloaded.list_refs() == ["src/alpha"]


def test_file_vault_wrong_master_key_is_rejected(vault: FileVault) -> None:
    vault.set("src/alpha", {"api_key": "k"})
    with pytest.raises(Exception):
        FileVault(vault._path, master_key="wrong-key").get("src/alpha")


def test_file_vault_missing_ref_raises(vault: FileVault) -> None:
    with pytest.raises(CredentialNotFound):
        vault.get("src/unknown")


def test_file_vault_delete_and_rotate(vault: FileVault) -> None:
    vault.set("a", {"api_key": "1"})
    vault.rotate("a", {"api_key": "2"})
    assert vault.get("a")["api_key"] == "2"
    assert vault.delete("a") is True
    assert vault.delete("a") is False


def test_file_vault_rejects_corrupt_file(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(VaultError, match="unreadable"):
        FileVault(path, master_key="k")


def test_file_vault_rejects_unknown_scheme(vault: FileVault) -> None:
    vault.set("a", {"api_key": "1"})
    payload = json.loads(vault._path.read_text(encoding="utf-8"))
    payload["entries"]["a"] = "rot13:xxxx"
    vault._path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(VaultError, match="unknown vault encryption scheme"):
        FileVault(vault._path, master_key="unit-test-master-key").get("a")


def test_source_credential_requires_src_prefix() -> None:
    with pytest.raises(ValueError, match=r"SRC_\{ULID\}"):
        SourceCredential(source_id="REQ_01ARZ3NDEKTSV4RRFFQ69G5F01")


def test_source_credential_rejects_unknown_auth_type() -> None:
    with pytest.raises(ValueError, match="auth_type must be one of"):
        SourceCredential(source_id=SRC, auth_type="magic")  # type: ignore[arg-type]


def test_source_credential_requires_a_ref_when_authenticated() -> None:
    with pytest.raises(ValueError, match="requires a credential_ref"):
        SourceCredential(source_id=SRC, auth_type="oauth2")


def test_source_credential_none_needs_no_ref() -> None:
    credential = SourceCredential(source_id=SRC, auth_type="none")
    assert credential.to_dict()["credential_ref"] is None


def test_source_credential_to_dict_has_the_spec_block() -> None:
    credential = SourceCredential(
        source_id=SRC,
        auth_type="oauth2",
        credential_ref="src/alpha",
        token_expiry="2026-01-01T00:00:00Z",
        auto_refresh=True,
    )
    assert credential.to_dict() == {
        "source_id": SRC,
        "auth_type": "oauth2",
        "credential_ref": "src/alpha",
        "token_expiry": "2026-01-01T00:00:00Z",
        "auto_refresh": True,
    }


def test_source_credential_expiry_and_refresh() -> None:
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    fresh = SourceCredential(
        source_id=SRC,
        auth_type="oauth2",
        credential_ref="src/alpha",
        token_expiry=(now + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        auto_refresh=True,
    )
    assert fresh.is_expired(now) is False
    assert fresh.needs_refresh(now) is False

    stale = SourceCredential(
        source_id=SRC,
        auth_type="oauth2",
        credential_ref="src/alpha",
        token_expiry=(now - timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
        auto_refresh=True,
    )
    assert stale.is_expired(now) is True
    assert stale.needs_refresh(now) is True


def test_source_credential_without_expiry_never_expires() -> None:
    credential = SourceCredential(
        source_id=SRC, auth_type="api_key", credential_ref="src/alpha"
    )
    assert credential.is_expired() is False
    assert credential.needs_refresh() is False


def test_source_credential_rejects_malformed_expiry() -> None:
    with pytest.raises(ValueError):
        SourceCredential(
            source_id=SRC,
            auth_type="oauth2",
            credential_ref="src/alpha",
            token_expiry="not-a-date",
        )


def test_resolver_builds_api_key_header(vault: FileVault) -> None:
    vault.set("src/alpha", {"api_key": "K-1", "header": "X-Custom"})
    resolver = CredentialResolver(vault)
    credential = SourceCredential(source_id=SRC, auth_type="api_key", credential_ref="src/alpha")
    assert resolver.auth_headers(credential) == {"X-Custom": "K-1"}


def test_resolver_builds_bearer_header(vault: FileVault) -> None:
    vault.set("src/alpha", {"access_token": "T-1"})
    resolver = CredentialResolver(vault)
    credential = SourceCredential(source_id=SRC, auth_type="oauth2", credential_ref="src/alpha")
    assert resolver.auth_headers(credential) == {"Authorization": "Bearer T-1"}


def test_resolver_builds_basic_header(vault: FileVault) -> None:
    vault.set("src/alpha", {"username": "u", "password": "p"})
    resolver = CredentialResolver(vault)
    credential = SourceCredential(source_id=SRC, auth_type="basic", credential_ref="src/alpha")
    headers = resolver.auth_headers(credential)
    assert headers["Authorization"].startswith("Basic ")


def test_resolver_returns_nothing_for_unauthenticated_source(vault: FileVault) -> None:
    resolver = CredentialResolver(vault)
    credential = SourceCredential(source_id=SRC, auth_type="none")
    assert resolver.resolve(credential) == {}
    assert resolver.auth_headers(credential) == {}


def test_resolver_rotate_updates_the_vault_and_expiry(vault: FileVault) -> None:
    vault.set("src/alpha", {"access_token": "old"})
    resolver = CredentialResolver(vault)
    credential = SourceCredential(source_id=SRC, auth_type="oauth2", credential_ref="src/alpha")
    resolver.rotate(credential, {"access_token": "new", "token_expiry": "2026-06-01T00:00:00Z"})
    assert vault.get("src/alpha")["access_token"] == "new"
    assert credential.token_expiry == "2026-06-01T00:00:00Z"


def test_resolver_rotate_requires_a_ref() -> None:
    resolver = CredentialResolver(EnvVault({}))
    with pytest.raises(ValueError, match="without a credential_ref"):
        resolver.rotate(SourceCredential(source_id=SRC, auth_type="none"), {})


def test_credential_never_appears_in_its_own_repr(vault: FileVault) -> None:
    vault.set("src/alpha", {"api_key": "TOPSECRET"})
    credential = SourceCredential(source_id=SRC, auth_type="api_key", credential_ref="src/alpha")
    assert "TOPSECRET" not in json.dumps(credential.safe_repr())
    assert "TOPSECRET" not in json.dumps(credential.to_dict())
