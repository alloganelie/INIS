"""Unit tests for the §41.12 prompt hasher."""

import hashlib

import pytest

from app.llm.tracing.prompt_hasher import (
    DEFAULT_PROMPT_HASHER,
    PROMPT_HASH_ALGORITHM,
    PROMPT_HASH_LENGTH,
    PromptHasher,
    hash_prompt,
    is_prompt_hash,
    verify_prompt,
)


def test_hash_prompt_is_sha256_hex() -> None:
    digest = hash_prompt("explique la demande")
    assert digest == hashlib.sha256(b"explique la demande").hexdigest()
    assert len(digest) == 64
    assert digest == digest.lower()


def test_hash_prompt_is_deterministic() -> None:
    assert hash_prompt("plan") == hash_prompt("plan")
    assert hash_prompt("plan") != hash_prompt("Plan")


def test_hash_prompt_empty_string_is_still_hashed() -> None:
    assert hash_prompt("") == hashlib.sha256(b"").hexdigest()


def test_hash_prompt_handles_accents_and_emoji() -> None:
    prompt = "Synthèse §41.12 🛰️"
    assert hash_prompt(prompt) == hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def test_hash_prompt_rejects_non_string() -> None:
    with pytest.raises(TypeError, match="must be a string"):
        hash_prompt(None)  # type: ignore[arg-type]


def test_verify_prompt_round_trip() -> None:
    prompt = "classify this information unit"
    assert verify_prompt(prompt, hash_prompt(prompt)) is True
    assert verify_prompt("other prompt", hash_prompt(prompt)) is False


def test_verify_prompt_rejects_malformed_digest() -> None:
    assert verify_prompt("prompt", "deadbeef") is False
    assert verify_prompt("prompt", "") is False
    assert verify_prompt("prompt", None) is False


def test_is_prompt_hash_detects_sha256_digests() -> None:
    assert is_prompt_hash(hash_prompt("x")) is True
    assert is_prompt_hash("z" * PROMPT_HASH_LENGTH) is False
    assert is_prompt_hash("a" * 63) is False
    assert is_prompt_hash(42) is False


def test_default_hasher_uses_the_mandated_algorithm() -> None:
    assert PROMPT_HASH_ALGORITHM == "sha256"
    assert DEFAULT_PROMPT_HASHER.algorithm == "sha256"
    assert DEFAULT_PROMPT_HASHER("same") == hash_prompt("same")


def test_hasher_supports_alternative_digests() -> None:
    hasher = PromptHasher("sha512")
    digest = hasher.hash_prompt("prompt")
    assert len(digest) == 128
    assert digest == hashlib.sha512(b"prompt").hexdigest()
    assert hasher.verify("prompt", digest) is True


def test_hasher_rejects_weak_or_unknown_algorithm() -> None:
    with pytest.raises(ValueError, match="Unsupported hash algorithm"):
        PromptHasher("md5")
    with pytest.raises(ValueError, match="Unsupported hash algorithm"):
        PromptHasher("")


def test_hash_payload_is_canonical() -> None:
    hasher = PromptHasher()
    left = hasher.hash_payload({"b": 1, "a": [1, 2]})
    right = hasher.hash_payload({"a": [1, 2], "b": 1})
    assert left == right
    assert left != hasher.hash_payload({"a": [2, 1], "b": 1})
