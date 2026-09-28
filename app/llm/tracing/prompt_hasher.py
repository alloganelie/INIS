"""Prompt hashing per INIS spec §41.12.

``prompt_hash`` lets an auditor confirm *which* prompt produced a decision
without storing the prompt in clear text (storage cost and confidentiality).
Hashing is centralised here so every component computes the same digest.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

#: Algorithm mandated by §41.12 ("<sha256 du prompt>").
PROMPT_HASH_ALGORITHM = "sha256"

#: Digests we accept, deliberately excluding broken algorithms (md5, sha1).
SUPPORTED_ALGORITHMS: frozenset[str] = frozenset(
    {"sha256", "sha384", "sha512", "blake2b", "blake2s"}
)

#: Hex length of the mandated algorithm (used by trace validation).
PROMPT_HASH_LENGTH = hashlib.new(PROMPT_HASH_ALGORITHM).digest_size * 2


class PromptHasher:
    """Compute reproducible, non-reversible digests of LLM prompts."""

    def __init__(self, algorithm: str = PROMPT_HASH_ALGORITHM) -> None:
        """Select the digest algorithm.

        Raises:
            ValueError: If *algorithm* is not in ``SUPPORTED_ALGORITHMS``.
        """
        normalized = (algorithm or "").strip().lower()
        if normalized not in SUPPORTED_ALGORITHMS:
            raise ValueError(
                f"Unsupported hash algorithm {algorithm!r}; "
                f"choose one of {sorted(SUPPORTED_ALGORITHMS)}"
            )
        self.algorithm = normalized
        self.hex_length = hashlib.new(normalized).digest_size * 2

    def hash_text(self, text: str) -> str:
        """Return the lowercase hex digest of a UTF-8 encoded string.

        Raises:
            TypeError: If *text* is not a string.
        """
        if not isinstance(text, str):
            raise TypeError(f"prompt to hash must be a string, got {type(text).__name__}")
        return hashlib.new(self.algorithm, text.encode("utf-8")).hexdigest()

    def hash_prompt(self, prompt: str) -> str:
        """Return the §41.12 digest of a prompt (empty prompts hash too)."""
        return self.hash_text(prompt)

    def hash_payload(self, payload: Any) -> str:
        """Digest a structured payload through a canonical JSON projection."""
        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        )
        return self.hash_text(canonical)

    def verify(self, prompt: str, prompt_hash: str) -> bool:
        """Constant-time check that *prompt* matches a stored digest."""
        if not isinstance(prompt_hash, str) or len(prompt_hash) != self.hex_length:
            return False
        return hmac.compare_digest(self.hash_prompt(prompt), prompt_hash.lower())

    def __call__(self, prompt: str) -> str:
        """Allow the hasher to be injected as a plain callable."""
        return self.hash_prompt(prompt)


#: Shared instance using the mandated sha256 algorithm.
DEFAULT_PROMPT_HASHER = PromptHasher()


def hash_prompt(prompt: str) -> str:
    """Return the canonical sha256 hex digest of *prompt*."""
    return DEFAULT_PROMPT_HASHER.hash_prompt(prompt)


def verify_prompt(prompt: str, prompt_hash: str) -> bool:
    """Check a prompt against a stored ``prompt_hash`` value."""
    return DEFAULT_PROMPT_HASHER.verify(prompt, prompt_hash)


def is_prompt_hash(value: Any) -> bool:
    """Return True when *value* looks like a sha256 hex digest."""
    if not isinstance(value, str) or len(value) != PROMPT_HASH_LENGTH:
        return False
    return all(char in "0123456789abcdefABCDEF" for char in value)
