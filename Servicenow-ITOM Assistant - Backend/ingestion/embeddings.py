"""
Shared embedding model - used by every ingestion script AND by retrieve.py,
so every vector in the Pinecone index (old and new) lives in the same
embedding space.

IMPORTANT: the MODEL must never change without re-embedding the entire
index. Your existing chunks were embedded with sentence-transformers
"all-MiniLM-L6-v2", mean-pooled, normalized, 384 dimensions (see
embed_and_upload.py).

What changed (Oct 2026): the default backend is now fastembed, which runs
the SAME all-MiniLM-L6-v2 model exported to ONNX (Qdrant/all-MiniLM-L6-v2-onnx,
same mean pooling + L2 normalization + 256-token truncation) on ONNX
Runtime instead of PyTorch. The vectors match the sentence-transformers
ones to within float rounding (cosine > 0.999), so the existing Pinecone
index keeps working with no re-ingestion - run verify_embeddings.py once
locally to confirm that on your own machine.

Why: PyTorch + transformers + sentence-transformers alone take roughly
300-400 MB of RAM once imported. fastembed + onnxruntime take ~90 MB.
That difference is what keeps the backend under Render's 512 MB free-tier
limit.

Set EMBEDDING_BACKEND=huggingface to go back to the old PyTorch path
(needs sentence-transformers + langchain-huggingface installed - see
requirements-ingestion.txt). Not recommended on Render.
"""

import os
from typing import List

from langchain_core.embeddings import Embeddings

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# Where fastembed keeps the downloaded ONNX model. The Dockerfile sets this
# to a folder inside the image and prefetch_models.py fills it at build
# time, so a cold start never downloads anything.
FASTEMBED_CACHE_PATH = os.getenv("FASTEMBED_CACHE_PATH") or None


class FastEmbedMiniLM(Embeddings):
    """LangChain Embeddings wrapper around fastembed's ONNX all-MiniLM-L6-v2.

    Same interface as HuggingFaceEmbeddings (embed_query / embed_documents
    returning plain lists of floats), so nothing that calls get_embeddings()
    needs to change.
    """

    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME, threads: int = 1):
        from fastembed import TextEmbedding

        # threads=1: Render's free tier is a fraction of one CPU anyway,
        # and fewer ONNX Runtime threads means fewer per-thread memory
        # arenas.
        self._model = TextEmbedding(
            model_name=model_name,
            cache_dir=FASTEMBED_CACHE_PATH,
            threads=threads,
        )

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [vector.tolist() for vector in self._model.embed(list(texts), batch_size=32)]

    def embed_query(self, text: str) -> List[float]:
        return next(iter(self._model.embed([text]))).tolist()


def get_embeddings() -> Embeddings:
    backend = os.getenv("EMBEDDING_BACKEND", "fastembed").strip().lower()

    if backend == "huggingface":
        # Imported lazily so the deployed app never needs torch installed.
        from langchain_huggingface import HuggingFaceEmbeddings

        return HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL_NAME,
            encode_kwargs={"normalize_embeddings": True},
        )

    return FastEmbedMiniLM()
