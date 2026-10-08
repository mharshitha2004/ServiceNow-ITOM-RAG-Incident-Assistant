"""Retrieval module for the ServiceNow ITOM documentation RAG assistant.

Compatible with rag.py imports:
    from retrieve import retrieve_candidates, rerank_candidates

This version deliberately does NOT add neighboring chunks to the returned
reranked results. Neighbor expansion was adding unrelated text to the LLM
context. Use get_context_chunks() only when you explicitly want safe,
source-local page context for debugging or experiments.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
import re
from collections import Counter


from dotenv import load_dotenv
from pinecone import Pinecone

# LangChain: same embedding model as before (now run on ONNX Runtime via
# fastembed rather than PyTorch - see ingestion/embeddings.py), shared with
# the ingestion scripts (see ingestion/embeddings.py) - guarantees every
# vector in Pinecone, old or newly ingested, lives in the same embedding
# space. Reranking uses Pinecone's own hosted bge-reranker-v2-m3 model
# (see _rerank_scores() below) instead of a locally-loaded cross-encoder -
# this keeps only ONE model (the embedder) in this process's memory,
# not two, which is what a 512 MB host actually needs.
import sys as _sys
from pathlib import Path as _Path
_sys.path.append(str(_Path(__file__).resolve().parent / "ingestion"))
from embeddings import get_embeddings  # noqa: E402

# ---------------------------------------------------------------------------
# I. Configuration
# ---------------------------------------------------------------------------
load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "servicenow-itom-docs")

RERANK_MODEL = "bge-reranker-v2-m3"  # Pinecone-hosted - see _rerank_scores()
RERANK_MAX_DOCUMENTS = 100  # bge-reranker-v2-m3's own documented limit per call

# Retrieve enough candidates for the cross-encoder to compare, then return
# only the most relevant passages to the RAG generation step.
RETRIEVAL_TOP_K = 30
FINAL_TOP_K = 6

# Optional local files used only by get_context_chunks() /
# get_adjacent_context_chunks() for same-source neighbor lookup. Not
# needed for Pinecone retrieval or reranking itself. Every ingestion
# script (pdf_ingest.py, scrape_servicenow_sources.py) writes its own
# chunks/*.jsonl file in this same schema, so neighbor expansion picks
# up new sources automatically without editing this list by hand.
CHUNKS_FILE = Path("deduplicated_chunks.jsonl")
CHUNKS_DIR = Path("chunks")


def _all_chunks_files() -> List[Path]:
    files = [CHUNKS_FILE] if CHUNKS_FILE.exists() else []
    if CHUNKS_DIR.exists():
        files.extend(sorted(CHUNKS_DIR.glob("*.jsonl")))
    return files

if not PINECONE_API_KEY:
    raise ValueError("PINECONE_API_KEY is missing. Add it to your .env file.")

# ---------------------------------------------------------------------------
# II. Load models and connect - LAZY, deferred until first real use
# ---------------------------------------------------------------------------
# Deliberately NOT loaded here at import time. main.py imports this module
# (via rag.py) before uvicorn ever binds to a port - on a RAM-constrained
# host (e.g. Render's free tier), loading the embedding + reranker models
# here would block that port binding long enough to fail the platform's
# port-scan/health check, on top of however much RAM they use. Each is
# loaded once, on its first actual call, via the three accessors below -
# every other function in this file goes through them instead of touching
# a module-level embedding_model/reranker/index variable directly.

_embedding_model = None
_pinecone_client = None
_pinecone_index = None


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        print("Loading embedding model...")
        _embedding_model = get_embeddings()
    return _embedding_model


def _get_pinecone_client() -> Pinecone:
    global _pinecone_client
    if _pinecone_client is None:
        _pinecone_client = Pinecone(api_key=PINECONE_API_KEY)
    return _pinecone_client


def _get_index():
    global _pinecone_index
    if _pinecone_index is None:
        print("Connecting to Pinecone...")
        _pinecone_index = _get_pinecone_client().Index(INDEX_NAME)
        print(f"Connected to Pinecone index: {INDEX_NAME}")
    return _pinecone_index


def _rerank_scores(question: str, texts: List[str]) -> List[float]:
    """Relevance score for each of `texts` against `question`, in the SAME
    ORDER as `texts` (not sorted) - matches the interface the old local
    reranker's .score(pairs) had, so both call sites below keep doing
    their own sorting unchanged.

    Uses Pinecone's hosted bge-reranker-v2-m3 (free: 500 requests/month
    on the Starter plan) instead of a locally-loaded cross-encoder
    model. This is what actually fixes the Render free-tier OOM: it
    removes an entire model's memory footprint from this process,
    rather than just deferring when it loads (which a prior fix
    attempted and didn't solve - both models still ended up loaded
    simultaneously at peak, just later in the request's lifecycle).
    """

    if not texts:
        return []

    # bge-reranker-v2-m3 caps requests at 100 documents; nothing in this
    # app sends anywhere near that many today (RETRIEVAL_TOP_K=30 for the
    # main rerank call, and neighbor-expansion candidate sets are smaller
    # still), but cap defensively rather than let an API call hard-fail
    # if that ever changes.
    capped = texts[:RERANK_MAX_DOCUMENTS]

    documents = [{"id": str(i), "text": t} for i, t in enumerate(capped)]

    result = _get_pinecone_client().inference.rerank(
        model=RERANK_MODEL,
        query=question,
        documents=documents,
        top_n=len(capped),
        return_documents=False,
        parameters={"truncate": "END"},
    )

    scores = [0.0] * len(texts)

    for item in _get(result, "data", []):
        index = _get(item, "index")
        score = _get(item, "score")
        if index is not None and 0 <= index < len(scores):
            scores[index] = float(score)

    return scores

# ---------------------------------------------------------------------------
# III. Helpers: Pinecone SDK objects can expose fields as attributes or mappings.
# ---------------------------------------------------------------------------
def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _metadata(match: Any) -> Dict[str, Any]:
    value = _get(match, "metadata", {}) or {}
    return value if isinstance(value, dict) else {}


def _match_id(match: Any) -> str:
    return str(_get(match, "id", ""))


def _match_text(match: Any) -> str:
    return str(_metadata(match).get("text", "") or "").strip()

# ---------------------------------------------------------------------------
# 1. Semantic retrieval from Pinecone
# ---------------------------------------------------------------------------
def retrieve_candidates(
    question: str,
    top_k: int = RETRIEVAL_TOP_K,
) -> List[Any]:
    """Embed the question and return Pinecone's semantic-search matches."""
    question = question.strip()
    if not question:
        return []
    if top_k < 1:
        raise ValueError("top_k must be at least 1")

    # LangChain embeddings interface: embed_query() returns a plain list
    # of floats already (normalize_embeddings=True is baked into
    # embeddings.py, matching how the index was originally built).
    query_vector = _get_embedding_model().embed_query(question)

    response = _get_index().query(
        vector=query_vector,
        top_k=top_k,
        include_metadata=True,
    )
    return list(_get(response, "matches", []) or [])

# ---------------------------------------------------------------------------
# 2. Cross-encoder reranking
# ---------------------------------------------------------------------------
def rerank_candidates(
    question: str,
    matches: Iterable[Any],
    top_k: int = FINAL_TOP_K,
    debug: bool = False,
) -> List[Dict[str, Any]]:
    """Rerank Pinecone matches by question/text relevance.

    Returns dictionaries with keys: match, reranker_score, final_score.
    No arbitrary keyword boost is applied; the cross-encoder score determines
    the ordering. `debug=True` prints scores and passage snippets.
    """
    matches = list(matches)
    if not matches or not question.strip():
        return []
    if top_k < 1:
        raise ValueError("top_k must be at least 1")

    # Empty text cannot meaningfully be reranked; omit it.
    usable = [m for m in matches if _match_text(m)]
    if not usable:
        return []

    texts = [_match_text(match) for match in usable]
    scores = _rerank_scores(question, texts)

    ranked: List[Dict[str, Any]] = []
    for match, score in zip(usable, scores):
        score = float(score)
        ranked.append({
            "match": match,
            "reranker_score": score,
            "final_score": score,
        })

    ranked.sort(key=lambda item: item["final_score"], reverse=True)
    ranked = ranked[:top_k]

    if debug:
        for rank, item in enumerate(ranked, start=1):
            match = item["match"]
            meta = _metadata(match)
            pinecone_score = _get(match, "score", None)
            print("\n" + "=" * 72)
            print(f"RERANKED RESULT {rank}")
            print("=" * 72)
            print("Chunk ID:", _match_id(match))
            print("Pinecone similarity:", pinecone_score)
            print("Reranker score:", round(item["reranker_score"], 4))
            print("Source:", meta.get("source", "Unknown"))
            print("Page:", meta.get("page_start", meta.get("page", "Unknown")))
            print("Text:\n", _match_text(match))

    return ranked

# ---------------------------------------------------------------------------
# 3. Optional safe context lookup (NOT automatically used by RAG)
# ---------------------------------------------------------------------------
def _load_local_chunks(paths: List[Path] | Path = None) -> List[Dict[str, Any]]:
    """Load every chunk from one or more local JSONL files (same schema
    as deduplicated_chunks.jsonl). Missing files are skipped rather than
    raising, since not every source (e.g. a freshly ingested PDF) will
    exist until its ingestion script has been run at least once."""

    if paths is None:
        paths = _all_chunks_files()
    elif isinstance(paths, Path):
        paths = [paths]

    chunks: List[Dict[str, Any]] = []

    for path in paths:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON on line {line_number} of {path}") from exc
                chunks.append(item)

    return chunks


def get_context_chunks(
    reranked_results: List[Dict[str, Any]],
    neighbor_radius: int = 0,
    chunks_file: List[Path] | Path | None = None,
) -> List[Dict[str, Any]]:
    """Return ranked seed chunks, optionally with source/page-local neighbors.

    Default radius 0 returns only the reranked hits (recommended for RAG).
    With radius > 0, neighbors are included only when they have the same source
    and are within the requested page distance. This avoids blindly adding
    adjacent JSONL rows from another document/source. Results are deduplicated
    by chunk_id and sorted by source/page/chunk id for readability.
    """
    if neighbor_radius < 0:
        raise ValueError("neighbor_radius cannot be negative")
    if not reranked_results:
        return []

    seed_chunks: List[Dict[str, Any]] = []
    for result in reranked_results:
        match = result.get("match")
        meta = _metadata(match) if match is not None else {}
        text = _match_text(match) if match is not None else ""
        if not text:
            continue
        seed_chunks.append({
            "chunk_id": _match_id(match),
            "text": text,
            "metadata": meta,
        })

    if neighbor_radius == 0:
        return seed_chunks

    all_chunks = _load_local_chunks(chunks_file)
    by_source: Dict[str, List[Dict[str, Any]]] = {}
    for chunk in all_chunks:
        metadata = chunk.get("metadata", {}) or {}
        source = str(metadata.get("source", ""))
        by_source.setdefault(source, []).append(chunk)

    # Preserve all seed results first; then add only plausible nearby pages.
    selected: Dict[str, Dict[str, Any]] = {
        str(chunk.get("chunk_id")): chunk for chunk in seed_chunks
    }

    for seed in seed_chunks:
        seed_meta = seed.get("metadata", {}) or {}
        source = str(seed_meta.get("source", ""))
        try:
            seed_page = int(seed_meta.get("page_start", seed_meta.get("page", -1)))
        except (TypeError, ValueError):
            continue
        if seed_page < 0:
            continue

        for candidate in by_source.get(source, []):
            candidate_meta = candidate.get("metadata", {}) or {}
            try:
                candidate_page = int(candidate_meta.get(
                    "page_start", candidate_meta.get("page", -1)
                ))
            except (TypeError, ValueError):
                continue
            if candidate_page < 0 or abs(candidate_page - seed_page) > neighbor_radius:
                continue
            candidate_id = str(candidate.get("chunk_id", ""))
            if candidate_id:
                selected.setdefault(candidate_id, candidate)

    def sort_key(chunk: Dict[str, Any]):
        meta = chunk.get("metadata", {}) or {}
        try:
            page = int(meta.get("page_start", meta.get("page", 0)))
        except (TypeError, ValueError):
            page = 0
        return (str(meta.get("source", "")), page, str(chunk.get("chunk_id", "")))

    return sorted(selected.values(), key=sort_key)

#Includes helper functions as well

_TRAILING_NUMBER = re.compile(r"^(?P<prefix>.*?)(?P<num>\d+)$")


def _neighbor_id(seed_id: str, offset: int) -> Optional[str]:
    """ID of the chunk `offset` positions away from `seed_id`.

    Original vectors use bare integer IDs ("42"); newer ones end in a
    zero-padded counter ("platform-guide-000042", "community-...-a1b2c3d4-0003").
    Returns None if the ID has no trailing number or the result would be < 0.
    """
    match = _TRAILING_NUMBER.match(str(seed_id))
    if not match:
        return None
    digits = match.group("num")
    number = int(digits) + offset
    if number < 0:
        return None
    padded = len(digits) > 1 and digits.startswith("0")
    rendered = f"{number:0{len(digits)}d}" if padded else str(number)
    return f"{match.group('prefix')}{rendered}"


class _LazyChunkIndex:
    """Chunk lookup by ID that does NOT hold the chunk text in memory.

    The old version parsed every chunks/*.jsonl file (~22k chunks, ~26 MB
    of JSON) into Python dicts and kept them for the life of the process -
    about 60+ MB of RAM on a 512 MB host, just so get_adjacent_context_chunks
    could look up a few dozen neighbors per question. This keeps only
    chunk_id -> (file, byte offset) and reads the one line it needs from
    disk on each .get(). Same results, a few MB instead of 60+.

    Exposes the only method callers use: .get(chunk_id) -> dict | None,
    returning the same {"chunk_id", "text", "metadata"} shape as before.
    """

    def __init__(self, paths: List[Path]):
        self._paths = [p for p in paths if p.exists()]
        self._offsets: Dict[str, tuple] = {}  # chunk_id -> (path index, byte offset)

        for path_index, path in enumerate(self._paths):
            with path.open("rb") as file:
                offset = file.tell()
                for raw_line in iter(file.readline, b""):
                    line_offset, offset = offset, offset + len(raw_line)
                    if not raw_line.strip():
                        continue
                    try:
                        item = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue
                    chunk_id = item.get("chunk_id", item.get("id"))
                    if chunk_id is not None:
                        # Later files win on duplicate IDs, same as the old
                        # dict-overwrite behavior.
                        self._offsets[str(chunk_id)] = (path_index, line_offset)

    def __len__(self) -> int:
        return len(self._offsets)

    def get(self, chunk_id, default=None) -> Optional[Dict[str, Any]]:
        location = self._offsets.get(str(chunk_id))
        if location is None:
            return default

        path_index, line_offset = location
        try:
            with self._paths[path_index].open("rb") as file:
                file.seek(line_offset)
                item = json.loads(file.readline())
        except (OSError, json.JSONDecodeError):
            return default

        return {
            "chunk_id": str(chunk_id),
            "text": str(item.get("text", "") or ""),
            "metadata": item.get("metadata", {}) or {},
        }


_CHUNK_INDEX_CACHE: Dict[Any, _LazyChunkIndex] = {}


def _chunks_by_id(chunks_file=None) -> _LazyChunkIndex:
    """Chunk lookup by ID, cached until a chunks file changes on disk, so the
    JSONL files aren't re-scanned on every question."""
    if chunks_file is None:
        paths = _all_chunks_files()
    elif isinstance(chunks_file, Path):
        paths = [chunks_file]
    else:
        paths = list(chunks_file)

    key = tuple((str(p), p.stat().st_mtime_ns if p.exists() else 0) for p in paths)
    cached = _CHUNK_INDEX_CACHE.get(key)
    if cached is not None:
        return cached

    index = _LazyChunkIndex(paths)

    _CHUNK_INDEX_CACHE.clear()
    _CHUNK_INDEX_CACHE[key] = index
    return index


def _get_chunk_text(chunk):
    """Get text from a chunk, supporting common field names."""
    return (
        chunk.get("text")
        or chunk.get("content")
        or chunk.get("chunk_text")
        or ""
    )


def _get_chunk_id(chunk):
    """Get the chunk ID, supporting common field names."""
    return chunk.get("chunk_id", chunk.get("id"))


def _get_page_number(chunk):
    """Get the page number, supporting common field names."""
    return chunk.get("page_number", chunk.get("page"))


def _get_source(chunk):
    """Get the source/document identifier if available."""
    return (
        chunk.get("source")
        or chunk.get("source_file")
        or chunk.get("document")
        or ""
    )


def _tokenize(text):
    """Convert text into lowercase words."""
    return set(re.findall(r"\b[a-zA-Z0-9_]+\b", text.lower()))


def _similarity_score(text_a, text_b):
    """
    Calculate Jaccard similarity between two texts.
    Returns a value between 0 and 1.
    """
    words_a = _tokenize(text_a)
    words_b = _tokenize(text_b)

    if not words_a or not words_b:
        return 0.0

    return len(words_a & words_b) / len(words_a | words_b)


def get_adjacent_context_chunks(
    reranked_results,
    question,
    chunks_file=None,
    neighbors_per_seed=2,
    max_context_chunks=24,
    continuation_chunks=6,
    continuation_seeds=3,
):
    """
    Preserve reranked seed chunks and include adjacent chunks.

    - If a seed ends mid-sentence, its next chunk is prioritized.
    - The top `continuation_seeds` seeds also pull in up to
      `continuation_chunks` FOLLOWING chunks. Documentation is mostly
      procedures ("1. ... 2. ... 3. ..."), and 1000-character chunks split
      them into pieces, so the best hit is often only the start of the answer.
    - The result is returned in reading order (document order), grouped by
      source with the most relevant source first, so numbered steps read
      continuously instead of seeds-first-then-neighbors.
    """
    if not reranked_results:
        return []

    if not question or not question.strip():
        return get_context_chunks(reranked_results)

    if neighbors_per_seed < 0:
        raise ValueError("neighbors_per_seed cannot be negative")

    if max_context_chunks < 1:
        raise ValueError("max_context_chunks must be at least 1")

    # 1. Convert reranked results into seed chunks.
    seed_chunks = get_context_chunks(
        reranked_results,
        neighbor_radius=0,
    )

    if not seed_chunks:
        return []

    # Always preserve all seed chunks.
    selected = list(seed_chunks)

    selected_ids = {
        str(chunk["chunk_id"])
        for chunk in selected
        if chunk.get("chunk_id") is not None
    }

    if neighbors_per_seed == 0:
        return selected

    # 2. Load the original JSONL chunks (cached between questions).
    chunks_by_id = _chunks_by_id(chunks_file)

    # 3. Detect seeds that appear to end mid-sentence.
    def ends_incomplete(text):
        text = text.rstrip()

        if not text:
            return False

        # Common signs of a chunk ending before its thought is complete.
        return (
            text.endswith((
                "you must",
                "must",
                "such as",
                "including",
                "for example",
                "because",
                "and",
                "or",
                "with",
                "to",
                "the",
                "of",
                "in",
                "by",
                "that",
                "which",
                "however,",
                ",",
                ":",
                ";",
                "-",
            ))
            or not text.endswith((".", "!", "?", ":", ";", ")"))
        )

    # 4. Collect adjacent chunks from the same source.
    neighbor_candidates = {}

    for rank, seed in enumerate(seed_chunks):
        seed_id = str(seed.get("chunk_id", ""))
        seed_metadata = seed.get("metadata", {}) or {}
        seed_source = str(seed_metadata.get("source", ""))
        seed_text = seed.get("text", "")

        if _neighbor_id(seed_id, 1) is None:
            continue  # ID has no trailing number, so it has no neighbors

        incomplete = ends_incomplete(seed_text)

        forward = neighbors_per_seed
        if rank < continuation_seeds:
            forward = max(forward, continuation_chunks)

        for offset in range(-neighbors_per_seed, forward + 1):
            if offset == 0:
                continue

            neighbor_id = _neighbor_id(seed_id, offset)
            if neighbor_id is None:
                continue

            if neighbor_id in selected_ids:
                continue

            neighbor = chunks_by_id.get(neighbor_id)

            if not neighbor:
                continue

            neighbor_metadata = neighbor.get("metadata", {}) or {}
            neighbor_source = str(
                neighbor_metadata.get("source", "")
            )

            # Do not mix documents.
            if (
                seed_source
                and neighbor_source
                and seed_source != neighbor_source
            ):
                continue

            if not neighbor.get("text", "").strip():
                continue

            # Prioritize the next chunk if the seed is incomplete.
            priority = 0

            if incomplete and offset == 1:
                priority = 100

            # Otherwise prefer immediate neighbors.
            priority += 10 - abs(offset)

            # Following chunks of the best-ranked seeds come before generic
            # neighbors (best seed first, nearest chunk first).
            if offset > 0 and rank < continuation_seeds:
                priority = max(priority, 60 - 10 * rank - offset)

            candidate = dict(neighbor)
            candidate["_priority"] = priority

            existing = neighbor_candidates.get(neighbor_id)

            if (
                existing is None
                or priority > existing["_priority"]
            ):
                neighbor_candidates[neighbor_id] = candidate

    if not neighbor_candidates:
        return selected

    # 5. Reranker scores help order the remaining neighbors.
    candidates = list(neighbor_candidates.values())

    texts = [item["text"] for item in candidates]
    scores = _rerank_scores(question, texts)

    for item, score in zip(candidates, scores):
        item["_reranker_score"] = float(score)

    # Priority first; reranker score breaks ties.
    candidates.sort(
        key=lambda item: (
            item["_priority"],
            item["_reranker_score"],
        ),
        reverse=True,
    )

    # 6. Add neighbors without dropping the seed chunks.
    for neighbor in candidates:
        if len(selected) >= max_context_chunks:
            break

        neighbor_id = str(neighbor["chunk_id"])

        if neighbor_id in selected_ids:
            continue

        # Remove internal ranking fields before returning.
        neighbor.pop("_priority", None)
        neighbor.pop("_reranker_score", None)

        selected.append(neighbor)
        selected_ids.add(neighbor_id)

    return _in_reading_order(selected, seed_chunks)


def _in_reading_order(chunks, seed_chunks):
    """Sort chunks into document order. Groups (same source + ID prefix) are
    ordered by their best-ranked seed, so the most relevant document is first
    but each group still reads top to bottom."""

    def parts(chunk):
        meta = chunk.get("metadata", {}) or {}
        source = str(meta.get("source", ""))
        match = _TRAILING_NUMBER.match(str(chunk.get("chunk_id", "")))
        if not match:
            return None
        return (source, match.group("prefix")), int(match.group("num"))

    group_rank: Dict[Any, int] = {}
    for rank, seed in enumerate(seed_chunks):
        found = parts(seed)
        if found and found[0] not in group_rank:
            group_rank[found[0]] = rank

    def sort_key(chunk):
        found = parts(chunk)
        if not found:
            return (1, 0, "", 0)  # no numeric ID: keep at the end
        group, number = found
        return (0, group_rank.get(group, 10**6), str(group), number)

    return sorted(chunks, key=sort_key)  # stable: ties keep original order

# ---------------------------------------------------------------------------
# 4. Small terminal test helper
# ---------------------------------------------------------------------------
def display_results(reranked: List[Dict[str, Any]]) -> None:
    if not reranked:
        print("No matching documents found.")
        return
    for rank, item in enumerate(reranked, start=1):
        match = item["match"]
        meta = _metadata(match)
        print("\n" + "=" * 72)
        print(f"RESULT {rank}")
        print("=" * 72)
        print("Chunk ID:", _match_id(match))
        print("Pinecone similarity:", _get(match, "score", "N/A"))
        print("Reranker score:", round(item["reranker_score"], 4))
        print("Page:", meta.get("page_start", meta.get("page", "N/A")))
        print("Text:\n", _match_text(match))


if __name__ == "__main__":
    print("\nServiceNow ITOM Documentation Search")
    print("Type 'exit' to stop.")
    while True:
        question = input("\nEnter your question: ").strip()
        if question.lower() in {"exit", "quit"}:
            break
        if not question:
            print("Please enter a question.")
            continue
        try:
            candidates = retrieve_candidates(question)
            print(f"\nRetrieved {len(candidates)} candidates from Pinecone.")
            reranked = rerank_candidates(question, candidates, debug=True)
            display_results(reranked)
        except Exception as error:
            print("Search failed:", error)