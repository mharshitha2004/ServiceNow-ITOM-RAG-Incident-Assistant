"""
Add a new PDF's chunks to the EXISTING Pinecone index, additively -
nothing already in the index is read, modified, or deleted.

This is your existing 4-step pipeline (extract_pdf.py -> chunk_pdf.py ->
remove_duplicates.py -> embed_and_upload.py), rewritten as ONE LangChain
script:

    PyMuPDFLoader -> RecursiveCharacterTextSplitter -> in-file dedupe
    -> PineconeVectorStore.add_texts(..., ids=[...])

Why this can't collide with your existing ~14k vectors:
  - Your existing pipeline used bare integers ("1", "2", ... ~14000ish) as
    Pinecone vector IDs. Pinecone's upsert is "insert or OVERWRITE by ID" -
    upserting a vector with an ID that already exists silently replaces
    it. Re-running the old scripts on a new PDF would start counting from
    1 again and clobber your existing chunks.
  - This script instead IDs every vector as "<source-slug>-000001",
    "<source-slug>-000002", etc. As long as --source-slug is a name you
    haven't used before (it can't collide with a bare integer), every ID
    here is brand new, so add_texts only ever creates vectors, never
    overwrites one.
  - Same index, same embedding model + dimension (see embeddings.py),
    same metadata shape (source, page_start, page_end, character_count,
    estimated_tokens, text) as your existing vectors - so retrieve.py's
    context formatting and rag.py's prompt work on old and new chunks
    identically, with no special-casing.

Usage:
    # Preview chunk counts without touching Pinecone or disk:
    python ingestion/pdf_ingest.py \\
        --pdf "servicenow-australia-servicenow-platform-enus.pdf" \\
        --source-slug platform-guide --dry-run

    # Then for real:
    python ingestion/pdf_ingest.py \\
        --pdf "servicenow-australia-servicenow-platform-enus.pdf" \\
        --source-slug platform-guide

Run from the backend project root (same folder as your .env), or adjust
sys.path below - this script imports embeddings.py from this same
ingestion/ folder.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pinecone import Pinecone
from langchain_pinecone import PineconeVectorStore

sys.path.append(str(Path(__file__).resolve().parent))
from embeddings import get_embeddings  # noqa: E402

load_dotenv()

# Same values as chunk_pdf.py, so chunk boundaries look the same as your
# existing content.
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
BATCH_SIZE = 100


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).casefold()


def load_pages(pdf_path: Path):
    """One LangChain Document per page (PyMuPDFLoader numbers pages from 0
    in metadata["page"], same underlying PyMuPDF library extract_pdf.py uses)."""
    loader = PyMuPDFLoader(str(pdf_path))
    return loader.load()


def chunk_pages(pages, source_name: str) -> list[dict]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    seen_text = set()
    chunks = []

    for page in pages:
        text = (page.page_content or "").strip()
        if not text:
            continue

        page_number = page.metadata.get("page", 0) + 1  # 0-indexed -> 1-indexed

        for piece in splitter.split_text(text):
            key = normalize_text(piece)
            if not key or key in seen_text:
                continue  # drop empty/duplicate chunks up front (like remove_duplicates.py)
            seen_text.add(key)

            chunks.append(
                {
                    "text": piece,
                    "metadata": {
                        "source": source_name,
                        "page_start": page_number,
                        "page_end": page_number,
                        "character_count": len(piece),
                        "estimated_tokens": len(piece.split()),
                    },
                }
            )

    return chunks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, help="Path to the PDF to ingest.")
    parser.add_argument(
        "--source-slug",
        required=True,
        help=(
            "Short unique prefix for this document's vector IDs, e.g. "
            "'platform-guide'. Must not already be used for another "
            "source in this index (check chunks/*.jsonl for slugs "
            "already in use)."
        ),
    )
    parser.add_argument(
        "--chunks-out",
        default=None,
        help=(
            "Where to also save chunks as local JSONL, same schema as "
            "deduplicated_chunks.jsonl - retrieve.py's neighbor "
            "expansion reads every chunks/*.jsonl file, so this makes "
            "the new PDF's neighbor lookups work too. Defaults to "
            "chunks/<source-slug>_chunks.jsonl"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chunk and print counts/a sample only - no Pinecone or disk writes.",
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path.resolve()}")

    print(f"Loading pages from {pdf_path.name}...")
    pages = load_pages(pdf_path)
    print(f"Loaded {len(pages)} pages.")

    print("Chunking (dropping in-file duplicate chunks)...")
    chunks = chunk_pages(pages, source_name=pdf_path.name)
    print(f"Produced {len(chunks)} unique chunks.")

    if not chunks:
        print("Nothing to upload.")
        return

    ids = [f"{args.source_slug}-{i:06d}" for i in range(1, len(chunks) + 1)]
    for chunk, chunk_id in zip(chunks, ids):
        chunk["chunk_id"] = chunk_id

    if args.dry_run:
        print("\n--dry-run: nothing written. Sample chunk:")
        print(json.dumps(chunks[0], ensure_ascii=False, indent=2)[:800])
        return

    chunks_out = Path(args.chunks_out or f"chunks/{args.source_slug}_chunks.jsonl")
    chunks_out.parent.mkdir(parents=True, exist_ok=True)
    with chunks_out.open("w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    print(f"Saved local copy: {chunks_out}")

    api_key = os.getenv("PINECONE_API_KEY")
    index_name = os.getenv("PINECONE_INDEX_NAME", "servicenow-itom-docs")
    if not api_key:
        raise ValueError("PINECONE_API_KEY is missing. Add it to your .env file.")

    print(f"Connecting to Pinecone index '{index_name}'...")
    pc = Pinecone(api_key=api_key)
    index = pc.Index(index_name)

    before = index.describe_index_stats().get("total_vector_count", "unknown")
    print(f"Vector count before upload: {before}")

    vector_store = PineconeVectorStore(
        index=index, embedding=get_embeddings(), text_key="text"
    )

    texts = [c["text"] for c in chunks]
    metadatas = [c["metadata"] for c in chunks]

    print("Embedding and upserting (additive - existing IDs are never touched)...")
    for start in range(0, len(chunks), BATCH_SIZE):
        end = start + BATCH_SIZE
        vector_store.add_texts(
            texts=texts[start:end],
            metadatas=metadatas[start:end],
            ids=ids[start:end],
        )
        print(f"Uploaded {min(end, len(chunks))}/{len(chunks)}")

    after = index.describe_index_stats().get("total_vector_count", "unknown")
    print(f"\nDone. Vector count before: {before}, after: {after}")
    print(f"Expected increase: {len(chunks)} (matches unless this slug was reused).")


if __name__ == "__main__":
    main()