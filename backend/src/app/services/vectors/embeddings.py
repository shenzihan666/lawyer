import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Sequence
from urllib import error, request

from app.core.config import Settings


def tokenize_text(text: str) -> list[str]:
    normalized = text.lower()
    tokens: list[str] = []

    chinese_pattern = re.compile(r"[\u4e00-\u9fff]")
    english_pattern = re.compile(r"[a-zA-Z0-9]+")

    index = 0
    while index < len(normalized):
        char = normalized[index]
        if chinese_pattern.match(char):
            tokens.append(char)
            index += 1
            continue

        match = english_pattern.match(normalized[index:])
        if match:
            token = match.group()
            tokens.append(token)
            index += len(token)
            continue

        index += 1

    return tokens


class ExternalEmbeddingService:
    _provider_max_batch_size = 100

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _embedding_endpoint(self) -> str:
        if not self.settings.embedding_base_url:
            raise RuntimeError(
                "EMBEDDING_BASE_URL (or BASE_URL) is required for external embedding"
            )
        return f"{self.settings.embedding_base_url.rstrip('/')}/embeddings"

    def _embedding_headers(self) -> dict[str, str]:
        if not self.settings.embedding_api_key:
            raise RuntimeError(
                "EMBEDDING_API_KEY (or ARK_API_KEY) is required for external embedding"
            )
        return {
            "Authorization": f"Bearer {self.settings.embedding_api_key}",
            "Content-Type": "application/json",
        }

    def _embedding_payload(self, texts: Sequence[str]) -> bytes:
        if not self.settings.embedding_model:
            raise RuntimeError(
                "EMBEDDING_MODEL (or EMBEDDER) is required for external embedding"
            )
        payload = {
            "model": self.settings.embedding_model,
            "input": list(texts),
            "encoding_format": "float",
        }
        return json.dumps(payload).encode("utf-8")

    @staticmethod
    def _parse_embedding_response(payload: bytes) -> list[list[float]]:
        try:
            parsed = json.loads(payload.decode("utf-8"))
            items = parsed["data"]
            embeddings = [item["embedding"] for item in items]
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("Invalid embedding response payload") from exc

        if not embeddings:
            raise RuntimeError("Embedding API returned no embeddings")
        return embeddings

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def _effective_batch_size(self) -> int:
        configured_batch_size = self.settings.embedding_batch_size
        if configured_batch_size < 1:
            raise RuntimeError("EMBEDDING_BATCH_SIZE must be greater than 0")
        return min(configured_batch_size, self._provider_max_batch_size)

    def _request_embeddings(self, texts: Sequence[str]) -> list[list[float]]:
        req = request.Request(
            self._embedding_endpoint(),
            data=self._embedding_payload(texts),
            headers=self._embedding_headers(),
            method="POST",
        )
        try:
            with request.urlopen(
                req,
                timeout=self.settings.embedding_timeout_seconds,
            ) as response:
                embeddings = self._parse_embedding_response(response.read())
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(
                f"Embedding API returned HTTP {exc.code}: {detail}"
            ) from exc
        except error.URLError as exc:
            raise RuntimeError(f"Embedding API request failed: {exc.reason}") from exc

        if len(embeddings) != len(texts):
            raise RuntimeError(
                "Embedding API returned an unexpected number of embeddings"
            )
        return embeddings

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        batch_size = self._effective_batch_size()
        embeddings: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            embeddings.extend(self._request_embeddings(batch))
        return embeddings


class BM25SparseEmbeddingService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def build_corpus_stats(self, texts: Sequence[str]) -> dict:
        vocab: dict[str, int] = {}
        doc_freq: Counter[str] = Counter()
        total_docs = len(texts)
        total_length = 0

        for text in texts:
            tokens = tokenize_text(text)
            total_length += len(tokens)
            unique_tokens = set(tokens)
            for token in unique_tokens:
                doc_freq[token] += 1
                if token not in vocab:
                    digest = hashlib.blake2b(
                        token.encode("utf-8"), digest_size=8
                    ).digest()
                    vocab[token] = (
                        int.from_bytes(digest, "big")
                        % self.settings.vector_sparse_dimension
                    )

        return {
            "vocab": vocab,
            "doc_freq": dict(doc_freq),
            "total_docs": total_docs,
            "avg_doc_len": (total_length / total_docs) if total_docs else 1.0,
            "k1": 1.5,
            "b": 0.75,
        }

    def sparse_embed_text(self, text: str, corpus_stats: dict) -> dict[int, float]:
        tokens = tokenize_text(text)
        if not tokens:
            return {}

        vocab = corpus_stats.get("vocab", {})
        doc_freq = corpus_stats.get("doc_freq", {})
        total_docs = max(int(corpus_stats.get("total_docs", 0)), 1)
        avg_doc_len = float(corpus_stats.get("avg_doc_len", 1.0)) or 1.0
        k1 = float(corpus_stats.get("k1", 1.5))
        b = float(corpus_stats.get("b", 0.75))

        term_freq = Counter(tokens)
        doc_len = len(tokens)
        sparse_vector: dict[int, float] = {}

        for token, freq in term_freq.items():
            token_index = vocab.get(token)
            if token_index is None:
                digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
                token_index = (
                    int.from_bytes(digest, "big")
                    % self.settings.vector_sparse_dimension
                )

            df = int(doc_freq.get(token, 0))
            if df == 0:
                idf = math.log((total_docs + 1) / 1)
            else:
                idf = math.log((total_docs - df + 0.5) / (df + 0.5) + 1)

            numerator = freq * (k1 + 1)
            denominator = freq + k1 * (1 - b + b * doc_len / avg_doc_len)
            score = idf * numerator / denominator
            if score > 0:
                sparse_vector[token_index] = sparse_vector.get(
                    token_index, 0.0
                ) + float(score)

        return sparse_vector

    def sparse_embed_texts(
        self,
        texts: Sequence[str],
        corpus_stats: dict,
    ) -> list[dict[int, float]]:
        return [self.sparse_embed_text(text, corpus_stats) for text in texts]
