"""
One-off check, run locally BEFORE deploying the fastembed change:
confirms the new ONNX embeddings (fastembed) match the original PyTorch
sentence-transformers embeddings that built your Pinecone index.

    pip install -r requirements.txt -r requirements-ingestion.txt
    python verify_embeddings.py

Every line should print a cosine similarity of 0.999 or higher, and the
script ends with "OK". If it prints "MISMATCH", don't deploy - send me
the output.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.append(str(Path(__file__).resolve().parent / "ingestion"))

from embeddings import EMBEDDING_MODEL_NAME, FastEmbedMiniLM  # noqa: E402

SAMPLES = [
    "My MID Server shows Down after a restart. What should I check?",
    "How do I configure Discovery schedules for a specific IP range?",
    "CMDB Health Dashboard is giving max_failure error",
    "Event Management alert rules are not creating incidents",
    "Software Asset Management reconciliation shows no installs",
    # Something long, to exercise the 256-token truncation path too.
    "Discovery " * 400,
]


def main() -> None:
    from sentence_transformers import SentenceTransformer

    original = SentenceTransformer(EMBEDDING_MODEL_NAME)
    new = FastEmbedMiniLM()

    worst = 1.0

    for text in SAMPLES:
        a = original.encode(text, normalize_embeddings=True)
        b = np.asarray(new.embed_query(text))
        cosine = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
        worst = min(worst, cosine)
        print(f"{cosine:.6f}  {text[:60]!r}")

    print()
    if worst >= 0.999:
        print(f"OK - worst cosine {worst:.6f}. Safe to deploy; no re-ingestion needed.")
    else:
        print(f"MISMATCH - worst cosine {worst:.6f}. Do not deploy this change.")
        sys.exit(1)


if __name__ == "__main__":
    main()
