"""Tests for deterministic hashing helpers (§18.1, §20.1)."""

from app.core.hashing import (
    after_hash,
    before_hash,
    canonical_json,
    record_hash,
    sha256_hex,
)


def test_sha256_hex_matches_known_digest_for_text_and_bytes() -> None:
    """The same text and its UTF-8 encoding produce the same digest."""
    expected = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"

    assert sha256_hex("abc") == expected
    assert sha256_hex(b"abc") == expected


def test_sha256_hex_handles_unicode() -> None:
    """Non-ASCII text is hashed as UTF-8, not as an ASCII escape."""
    assert sha256_hex("é") == sha256_hex("é".encode("utf-8"))
    assert len(sha256_hex("é")) == 64


def test_canonical_json_is_key_order_independent() -> None:
    """Two mappings with the same content hash identically."""
    assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})
    assert canonical_json({"a": 2, "b": 1}) == '{"a":2,"b":1}'


def test_record_hash_is_deterministic_and_order_independent() -> None:
    """A record's digest does not depend on key insertion order."""
    first = {"resource_id": "SRC_1", "size_bytes": 12}
    second = {"size_bytes": 12, "resource_id": "SRC_1"}

    assert record_hash(first) == record_hash(second)
    assert record_hash(first) == sha256_hex(canonical_json(first))


def test_record_hash_returns_none_for_absent_record() -> None:
    """An absent record has no digest, rather than a digest of null."""
    assert record_hash(None) is None
    assert before_hash(None) is None
    assert after_hash(None) is None


def test_before_and_after_hash_differ_when_the_record_changed() -> None:
    """A modification yields two distinct digests."""
    before_record = {"status": "active"}
    after_record = {"status": "archived"}

    assert before_hash(before_record) != after_hash(after_record)
    assert before_hash(before_record) == record_hash(before_record)

