"""§41.13 — un objet est streamé, et refusé **avant** d'être chargé.

``S3Client.download()`` rend l'objet entier en mémoire : refuser un objet de 10 GiB
coûtait 10 GiB de RAM, et le refus arrivait après coup. ``stream_to_file`` écrit
chunk par chunk et interrompt le transfert dès que le plafond est franchi — sur la
taille déclarée d'abord, puis sur les octets réellement lus si le stockage ment.

Aucun boto3, aucun conteneur : le client S3 est doublé.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.errors import InfrastructureError, ValidationError
from app.storage.object_storage.object_downloader import (
    download_limit,
    download_object_to_temp,
)
from app.storage.object_storage.s3_client import S3Client

PAYLOAD = b"city,population\nParis,2145906\nBerlin,3645000\n"


class _FakeBody:
    """A streaming body that records how it was consumed."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload
        self.reads = 0
        self.closed = False

    def read(self, size: int = -1) -> bytes:
        self.reads += 1
        chunk = self._payload if size < 0 else self._payload[:size]
        self._payload = self._payload[len(chunk) :]
        return chunk

    def close(self) -> None:
        self.closed = True


class _FakeS3:
    """A boto3-shaped double: ``head_object`` and ``get_object`` only."""

    def __init__(
        self, payload: bytes = PAYLOAD, *, declared_size: int | None = None
    ) -> None:
        self.payload = payload
        self.declared_size = declared_size if declared_size is not None else len(payload)
        self.body = _FakeBody(payload)
        self.heads = 0
        self.gets = 0

    def head_object(self, Bucket: str, Key: str) -> dict:
        self.heads += 1
        return {
            "ContentLength": self.declared_size,
            "ContentType": "text/csv",
            "ETag": '"abc"',
        }

    def get_object(self, Bucket: str, Key: str) -> dict:
        self.gets += 1
        return {"Body": self.body}


def _client(fake: _FakeS3, bucket: str = "inis-artifacts") -> S3Client:
    """Return an ``S3Client`` bound to the double, without touching boto3."""
    client = S3Client.__new__(S3Client)
    client._bucket_name = bucket
    client._s3_client = fake
    return client


class TestHead:
    def test_head_reports_size_type_and_etag(self) -> None:
        client = _client(_FakeS3())

        header = client.head("documents/REQ_1/a.csv")

        assert header["size_bytes"] == len(PAYLOAD)
        assert header["content_type"] == "text/csv"
        assert header["etag"] == '"abc"'


class TestStreamToFile:
    def test_the_object_is_written_and_its_size_returned(self, tmp_path: Path) -> None:
        fake = _FakeS3()
        destination = tmp_path / "copie" / "a.csv"

        written = _client(fake).stream_to_file("documents/a.csv", destination)

        assert written == len(PAYLOAD)
        assert destination.read_bytes() == PAYLOAD
        assert fake.body.closed is True

    def test_the_copy_is_chunked_not_read_whole(self, tmp_path: Path) -> None:
        fake = _FakeS3()

        _client(fake).stream_to_file("documents/a.csv", tmp_path / "a.csv", chunk_size=8)

        assert fake.body.reads > 1, "le corps doit être lu par morceaux"

    def test_a_declared_size_over_the_ceiling_is_refused_before_reading(
        self, tmp_path: Path
    ) -> None:
        fake = _FakeS3()
        destination = tmp_path / "a.csv"

        with pytest.raises(ValidationError) as refusal:
            _client(fake).stream_to_file(
                "documents/a.csv",
                destination,
                max_bytes=10,
                known_size=len(PAYLOAD),
            )

        assert "limite autorisée de 10 octets" in str(refusal.value)
        assert fake.gets == 0, "l'objet ne doit pas être demandé pour être refusé"
        assert not destination.exists()

    def test_the_ceiling_is_also_checked_while_streaming(self, tmp_path: Path) -> None:
        """Un stockage qui sous-déclare la taille ne contourne pas la borne."""
        fake = _FakeS3(declared_size=1)
        destination = tmp_path / "a.csv"

        with pytest.raises(ValidationError):
            _client(fake).stream_to_file(
                "documents/a.csv", destination, max_bytes=10, chunk_size=4
            )

        assert not destination.exists(), "aucun fichier partiel ne doit rester"

    def test_a_failed_transfer_leaves_no_partial_file(self, tmp_path: Path) -> None:
        fake = _FakeS3()

        def _boom(size: int = -1) -> bytes:
            raise OSError("coupure du flux")

        fake.body.read = _boom
        destination = tmp_path / "a.csv"

        with pytest.raises(OSError):
            _client(fake).stream_to_file("documents/a.csv", destination)

        assert not destination.exists()


class TestDownloadLimit:
    def test_the_ceiling_is_the_platform_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("INIS_MAX_UPLOAD_BYTES", "1234")

        assert download_limit() == 1234



class TestDownloadObjectToTemp:
    def test_a_foreign_bucket_is_refused(self) -> None:
        with pytest.raises(ValidationError) as refusal, download_object_to_temp(
            "s3://autre-bucket/a.csv", client=_client(_FakeS3())
        ):
            pass

        assert "autre-bucket" in str(refusal.value)
        assert "inis-artifacts" in str(refusal.value)

    def test_a_non_s3_target_is_refused(self) -> None:
        with pytest.raises(ValidationError), download_object_to_temp(
            "/tmp/a.csv", client=_client(_FakeS3())
        ):
            pass

    def test_without_storage_the_refusal_is_explicit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for name in ("S3_ENDPOINT", "S3_ACCESS_KEY", "S3_SECRET_KEY", "S3_BUCKET"):
            monkeypatch.delenv(name, raising=False)

        with pytest.raises(InfrastructureError) as refusal, download_object_to_temp(
            "s3://inis-artifacts/a.csv"
        ):
            pass

        assert "S3_BUCKET" in str(refusal.value)

    def test_the_object_is_downloaded_then_removed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeS3()
        seen: list[Path] = []

        with download_object_to_temp(
            "s3://inis-artifacts/documents/a.csv",
            client=_client(fake),
            workdir=tmp_path,
        ) as downloaded:
            assert downloaded.bucket == "inis-artifacts"
            assert downloaded.key == "documents/a.csv"
            assert downloaded.size_bytes == len(PAYLOAD)
            assert downloaded.content_type == "text/csv"
            assert downloaded.path.read_bytes() == PAYLOAD
            seen.append(downloaded.path)

        assert not seen[0].exists(), "le fichier temporaire est nettoyé"
        assert fake.body.closed is True

    def test_the_temporary_name_comes_from_the_key(self, tmp_path: Path) -> None:
        with download_object_to_temp(
            "s3://inis-artifacts/documents/REQ_1/villes.csv",
            client=_client(_FakeS3()),
            workdir=tmp_path,
        ) as downloaded:
            assert downloaded.path.name == "villes.csv"

    def test_the_ceiling_of_the_call_is_applied(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("INIS_MAX_UPLOAD_BYTES", "8")
        fake = _FakeS3()

        with pytest.raises(ValidationError) as refusal, download_object_to_temp(
            "s3://inis-artifacts/documents/a.csv", client=_client(fake)
        ):
            pass

        assert "limite autorisée de 8 octets" in str(refusal.value)
        assert fake.gets == 0

