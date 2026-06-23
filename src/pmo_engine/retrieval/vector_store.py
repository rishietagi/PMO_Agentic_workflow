"""ChromaDB wrapper + local BGE embeddings (CLAUDE.md §3).

Embeddings are computed locally with BAAI/bge-base-en-v1.5 (no API, no rate
limits at query time — important for a live demo). The collection is persisted
to data/chroma_db/.
"""
from __future__ import annotations

import logging
from typing import Any

from pmo_engine import config

logger = logging.getLogger(__name__)

# bge models recommend a query instruction prefix for retrieval.
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class _Embedder:
    """Lazy singleton around the sentence-transformers BGE model."""
    _model = None

    @classmethod
    def get(cls):
        if cls._model is None:
            from sentence_transformers import SentenceTransformer
            device = config.resolve_device()
            logger.info("Loading embedding model %s on %s ...",
                        config.EMBEDDING_MODEL, device)
            cls._model = SentenceTransformer(config.EMBEDDING_MODEL, device=device)
        return cls._model

    @classmethod
    def embed_documents(cls, texts: list[str]) -> list[list[float]]:
        model = cls.get()
        embs = model.encode(texts, normalize_embeddings=True,
                            show_progress_bar=len(texts) > 64,
                            batch_size=32)
        return [e.tolist() for e in embs]

    @classmethod
    def embed_query(cls, text: str) -> list[float]:
        model = cls.get()
        emb = model.encode([BGE_QUERY_PREFIX + text],
                          normalize_embeddings=True)[0]
        return emb.tolist()


class VectorStore:
    def __init__(self, persist_dir: str | None = None,
                 collection: str = config.CHROMA_COLLECTION) -> None:
        import chromadb
        self.persist_dir = str(persist_dir or config.CHROMA_DIR)
        self.client = chromadb.PersistentClient(path=self.persist_dir)
        self.collection_name = collection
        self._collection = None

    @property
    def collection(self):
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"})
        return self._collection

    def reset(self) -> None:
        try:
            self.client.delete_collection(self.collection_name)
        except Exception:  # noqa: BLE001
            pass
        self._collection = None

    def count(self) -> int:
        try:
            return self.collection.count()
        except Exception:  # noqa: BLE001
            return 0

    def add(self, ids: list[str], texts: list[str],
            metadatas: list[dict[str, Any]]) -> None:
        embeddings = _Embedder.embed_documents(texts)
        # Chroma rejects None metadata values; coerce.
        clean = [{k: ("" if v is None else v) for k, v in m.items()}
                 for m in metadatas]
        self.collection.add(ids=ids, documents=texts, embeddings=embeddings,
                            metadatas=clean)

    def query(self, text: str, top_k: int,
              where: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        emb = _Embedder.embed_query(text)
        res = self.collection.query(
            query_embeddings=[emb], n_results=top_k,
            where=where or None,
            include=["documents", "metadatas", "distances"])
        out: list[dict[str, Any]] = []
        if not res["ids"] or not res["ids"][0]:
            return out
        for i, cid in enumerate(res["ids"][0]):
            out.append({
                "chunk_id": cid,
                "text": res["documents"][0][i],
                "metadata": res["metadatas"][0][i],
                "distance": res["distances"][0][i],
                "score": 1.0 - res["distances"][0][i],
            })
        return out

    def get_all(self) -> dict[str, Any]:
        return self.collection.get(include=["documents", "metadatas"])
