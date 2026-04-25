"""Vector store for unstructured context.

Used for semantic retrieval over:
  - Mechanism descriptions (from DrugBank full release, when available)
  - WebMD patient reviews

NOT used for the interaction records themselves — those use structured lookup.
This separation is deliberate: for exact-pair queries, structured retrieval is
strictly better than semantic search.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Dict

import pandas as pd

from src.config import Config, config as default_config


class VectorStore:
    """Thin wrapper over ChromaDB. Silently no-ops if chromadb isn't available."""

    def __init__(self, collection_name: str = "pharmguard_context", cfg: Optional[Config] = None):
        self.cfg = cfg or default_config
        self.collection_name = collection_name
        self._client = None
        self._collection = None

    def _ensure_client(self):
        if self._client is not None:
            return
        try:
            import chromadb
        except ImportError:
            raise ImportError(
                "chromadb not installed. Run `pip install chromadb` or skip vector features."
            )
        self.cfg.paths.vector_db_path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(self.cfg.paths.vector_db_path))
        self._collection = self._client.get_or_create_collection(self.collection_name)

    # ---------- write ----------

    def add_documents(self, docs: List[Dict]) -> None:
        """Add documents. Each dict needs: id, text, metadata (dict)."""
        if not docs:
            return
        self._ensure_client()
        self._collection.add(
            ids=[d["id"] for d in docs],
            documents=[d["text"] for d in docs],
            metadatas=[d.get("metadata", {}) for d in docs],
        )

    def ingest_reviews(self, df: pd.DataFrame, text_col: str = "review_text") -> int:
        """Ingest a reviews DataFrame into the vector store."""
        if df.empty or text_col not in df.columns:
            return 0
        docs = []
        for _, r in df.iterrows():
            text = str(r.get(text_col) or "")
            if len(text) < 20:
                continue
            meta = {
                "drug_name": str(r.get("drug_name") or "").lower(),
                "source": str(r.get("source") or "WebMD"),
                "record_id": str(r.get("record_id") or ""),
            }
            docs.append({"id": meta["record_id"], "text": text, "metadata": meta})
        self.add_documents(docs)
        return len(docs)

    # ---------- read ----------

    def search(self, query: str, top_k: int = 5, where: Optional[dict] = None) -> List[Dict]:
        self._ensure_client()
        res = self._collection.query(
            query_texts=[query],
            n_results=top_k,
            where=where,
        )
        out = []
        for i, doc in enumerate(res["documents"][0]):
            out.append({
                "text": doc,
                "metadata": res["metadatas"][0][i],
                "distance": res["distances"][0][i] if "distances" in res else None,
            })
        return out
