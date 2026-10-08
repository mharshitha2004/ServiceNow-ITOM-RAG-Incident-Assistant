"""
Pre-downloads the embedding model into this image's build layer, so the
deployed container doesn't need network access to huggingface.co on every
cold start. Render's free tier already has a ~1 minute wake-up delay after
15 minutes idle; this avoids stacking a model download on top of that.

The model is all-MiniLM-L6-v2 as an ONNX export, run by fastembed (see
ingestion/embeddings.py for why it's no longer PyTorch). It's saved to
FASTEMBED_CACHE_PATH, which the Dockerfile sets to a folder inside the
image so the running app finds it there.

Only the embedding model is prefetched here - the reranker runs on
Pinecone's hosted infrastructure (bge-reranker-v2-m3, via
retrieve.py's _rerank_scores()), not loaded locally.

Run automatically during `docker build` (see Dockerfile's RUN step) -
you shouldn't need to run this by hand.
"""

import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent / "ingestion"))

from embeddings import EMBEDDING_MODEL_NAME, FastEmbedMiniLM  # noqa: E402

print(f"Pre-downloading {EMBEDDING_MODEL_NAME} (ONNX) to "
      f"{os.getenv('FASTEMBED_CACHE_PATH', '<fastembed default>')}...")

vector = FastEmbedMiniLM().embed_query("warm-up")
assert len(vector) == 384, f"unexpected embedding size {len(vector)}"

print("Done.")
