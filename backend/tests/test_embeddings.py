import json

from app.core.config import Settings
from app.services.vectors.embeddings import ExternalEmbeddingService


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def read(self) -> bytes:
        return self.payload


def test_embed_texts_sends_multiple_requests_with_configured_batch_size(
    monkeypatch,
) -> None:
    requested_batches: list[list[str]] = []

    def fake_urlopen(req, timeout):
        assert timeout == 30
        payload = json.loads(req.data.decode("utf-8"))
        batch = payload["input"]
        requested_batches.append(batch)
        return _FakeResponse(
            json.dumps(
                {
                    "data": [
                        {"embedding": [float(text.removeprefix("text-"))]}
                        for text in batch
                    ]
                }
            ).encode("utf-8")
        )

    monkeypatch.setattr("app.services.vectors.embeddings.request.urlopen", fake_urlopen)
    monkeypatch.setenv("EMBEDDING_BASE_URL", "https://emb.example/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-test")
    monkeypatch.setenv("EMBEDDING_API_KEY", "secret")

    service = ExternalEmbeddingService(
        Settings(
            _env_file=None,
            embedding_batch_size=2,
        )
    )

    embeddings = service.embed_texts(
        ["text-0", "text-1", "text-2", "text-3", "text-4"]
    )

    assert requested_batches == [
        ["text-0", "text-1"],
        ["text-2", "text-3"],
        ["text-4"],
    ]
    assert embeddings == [[0.0], [1.0], [2.0], [3.0], [4.0]]


def test_embed_texts_caps_batch_size_at_provider_limit(monkeypatch) -> None:
    requested_batch_sizes: list[int] = []

    def fake_urlopen(req, timeout):
        payload = json.loads(req.data.decode("utf-8"))
        batch = payload["input"]
        requested_batch_sizes.append(len(batch))
        return _FakeResponse(
            json.dumps(
                {"data": [{"embedding": [float(index)]} for index, _ in enumerate(batch)]}
            ).encode("utf-8")
        )

    monkeypatch.setattr("app.services.vectors.embeddings.request.urlopen", fake_urlopen)
    monkeypatch.setenv("EMBEDDING_BASE_URL", "https://emb.example/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-test")
    monkeypatch.setenv("EMBEDDING_API_KEY", "secret")

    service = ExternalEmbeddingService(
        Settings(
            _env_file=None,
            embedding_batch_size=500,
        )
    )

    service.embed_texts([f"text-{index}" for index in range(101)])

    assert requested_batch_sizes == [100, 1]
