"""
Ingest a hand-picked list of specific URLs into the existing Pinecone index.

This is deliberately separate from scrape_servicenow_sources.py. That script
discovers pages by following links, which is great for breadth but can't
reliably surface a specific, high-value page (e.g. an old forum thread with
no links pointing to it from anywhere the crawler currently starts). This
script skips discovery entirely - you give it exact URLs, it fetches,
chunks, embeds, and upserts just those.

Usage:
    python ingestion/ingest_specific_urls.py --dry-run
    python ingestion/ingest_specific_urls.py
    python ingestion/ingest_specific_urls.py --urls-file my_urls.txt

--urls-file is optional: one URL per line, '#' for comments. Without it,
the CURATED_URLS list below is used. Either way, already-ingested URLs
(tracked in ingested_urls.json, separate from the crawler's
scraped_urls.json) are skipped on a later run unless you pass --force.

Embeddings come from ingestion/embeddings.py's get_embeddings() - the
exact same model/config (all-MiniLM-L6-v2, normalized) that pdf_ingest.py,
scrape_servicenow_sources.py, and retrieve.py all share, so every vector
in Pinecone - old and new - lives in the same embedding space.
"""

import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from langchain_pinecone import PineconeVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pinecone import Pinecone

from embeddings import get_embeddings

load_dotenv()

# ---------------------------------------------------------------------------
# Curated URLs - real, verified pages (checked via web search, not guessed),
# grouped by the topics asked for: MID Server down, Discovery issues, CMDB
# issues, Event Management. All are public (no login wall) - ServiceNow's
# numbered Support KB (support.servicenow.com) is deliberately excluded,
# same reasoning as in scrape_servicenow_sources.py: a plain scraper can't
# reach it. Add more URLs here (or in a --urls-file) any time you find a
# specific thread worth having, like the CMDB Health Dashboard one that
# prompted this script.
# ---------------------------------------------------------------------------

CURATED_URLS = [
    # --- MID Server down / not responding ---
    "https://www.servicenow.com/community/itom-forum/midserver-often-goes-down/m-p/903686",
    "https://www.servicenow.com/community/virtual-agent-forum/issue-with-mid-server/td-p/3489514",
    "https://www.servicenow.com/community/developer-forum/how-to-restart-a-mid-server-that-is-in-down-status/td-p/2991693",
    "https://www.servicenow.com/community/developer-forum/why-mid-server-status-is-showing-as-down-even-all-the-mid-server/td-p/2618879",
    "https://www.servicenow.com/community/itom-forum/why-mid-server-showing-down-while-service-is-still-running/m-p/931482",
    "https://www.servicenow.com/community/developer-forum/mid-server-unable-to-start-service/m-p/2827296",

    # --- Discovery issues ---
    "https://www.servicenow.com/community/itom-articles/servicenow-discovery-overview/ta-p/2321453",
    "https://www.servicenow.com/community/developer-forum/how-to-troubleshoot-discovery/m-p/3166045",
    "https://www.servicenow.com/community/itom-forum/cis-not-getting-discovered-via-quick-discovery-but-not-via/m-p/2763872",
    "https://www.servicenow.com/community/cmdb-articles/troubleshooting-discovery/ta-p/3474474",
    "https://www.servicenow.com/community/itom-forum/servicenow-discovery-not-identifying-all-expected-cis/m-p/3103344",
    "https://www.servicenow.com/community/itom-articles/service-mapping-troubleshooting-tips-and-tricks/ta-p/2321133",

    # --- CMDB issues (duplicates, identification/reconciliation) ---
    "https://www.servicenow.com/community/itom-articles/servicenow-duplicate-cis-solution-script-report/ta-p/2319039",
    "https://www.servicenow.com/community/cmdb-articles/cmdb-identification-reconciliation/ta-p/2301712",
    "https://www.servicenow.com/community/itsm-forum/how-to-restrict-duplicate-ci-creation-on-cmdb-ci-server/td-p/3449634",
    # NOT included: .../configuration-management-database-cmdb/ire.html
    # (the official IRE docs page). Confirmed via two real dry runs that
    # it's client-side-rendered - a plain HTTP fetch gets an empty JS-app
    # shell (22 chars) even with an Accept: text/markdown hint, not the
    # real content. Fixing that needs a headless browser (Playwright),
    # which isn't worth adding for one page - IRE/CI identification is
    # already well covered by the two community articles below.
    # The exact thread that prompted this script - old (2022), not linked
    # from anywhere the crawler currently starts, so discovery would
    # likely never reach it on its own.
    "https://www.servicenow.com/community/cmdb-forum/cmdb-health-dashboard-not-working/m-p/224219",

    # --- Event Management (alert correlation, message keys) ---
    "https://www.servicenow.com/community/itom-forum/alert-correlation-rule-not-working-for-flapping-reopend-alerts/td-p/3533026",
    "https://www.servicenow.com/community/itom-forum/event-management-alert-correlation-and-management-rules/m-p/3389224",
    "https://www.servicenow.com/community/itom-forum/event-management-correlation-behavior-after-7-days/m-p/3519521",
    "https://www.servicenow.com/community/itom-forum/how-to-group-alerts-with-a-different-correlation-rules-without/m-p/3353315",
    "https://www.servicenow.com/community/itom-forum/cmdb-correlation-in-the-event-management/m-p/2498348",
    "https://www.servicenow.com/community/itom-forum/event-management-alert-handling/m-p/3350262",
]

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "servicenow-itom-docs")

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150

# Separate from scraped_urls.json (the crawler's own state file), so this
# script's progress doesn't interfere with - or get overwritten by - the
# crawler's.
STATE_FILE = Path(__file__).resolve().parent.parent / "ingested_urls.json"

CHUNKS_OUT_DIR = Path(__file__).resolve().parent.parent / "chunks"
CHUNKS_OUT_FILE = CHUNKS_OUT_DIR / "curated_url_chunks.jsonl"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    # Some docs.servicenow.com pages are client-side-rendered and return
    # an almost-empty shell to a plain HTML request, but serve real
    # markdown content when asked for it - this is harmless to send to
    # any other site (they just ignore it and return HTML as normal).
    "Accept": "text/markdown, text/html;q=0.9, */*;q=0.8",
}

MIN_CONTENT_CHARS = 150  # below this, treat the page as empty/nav-only


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"ingested": []}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def fetch(url: str) -> str | None:
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"  [error] couldn't fetch {url}: {e}")
        return None


def extract_title_and_text(html: str, url: str) -> tuple[str, str]:
    """Returns (title, main_text). Tries a ServiceNow Community-specific
    selector first (Khoros/Lithium forum platforms put the actual post
    body in .lia-message-body-content; without this, extraction pulls in
    the whole page - nav, sidebar, "related content" links, etc.), then
    falls back to a generic extraction for everything else (e.g.
    docs.servicenow.com)."""

    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()

    title_tag = soup.find("h1") or soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else url

    is_community = "servicenow.com/community/" in url

    if is_community:
        # One block per post (question + each reply) on a forum thread -
        # joined together so the whole thread (question + the replies
        # that actually solve it) is captured, not just the first post.
        bodies = soup.select(".lia-message-body-content")
        if bodies:
            text = "\n\n".join(b.get_text("\n", strip=True) for b in bodies)
            return title, text

    # Generic fallback: prefer <article> / <main> if present, else <body>.
    container = soup.find("article") or soup.find("main") or soup.find("body")
    text = container.get_text("\n", strip=True) if container else ""

    if not text.strip():
        # No matching container (or an empty one) usually means this
        # wasn't real HTML to begin with - e.g. raw markdown returned
        # for a client-side-rendered page (see the Accept header above).
        # Fall back to every bit of text BeautifulSoup can find at all,
        # and pull a title from a leading markdown "# heading" line if
        # there was no real <h1>/<title> tag either.
        text = soup.get_text("\n", strip=True)

        if title == url or not title.strip():
            heading_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
            if heading_match:
                title = heading_match.group(1).strip()

    return title, text


_BOILERPLATE_PATTERNS = [
    # docs.servicenow.com's "Summarize / Summarized using AI" widget -
    # same boilerplate the main scraper strips. Matches from "Summarize"
    # through the end of its disclaimer sentence, non-greedily, so only
    # the widget itself is removed, not real surrounding content.
    re.compile(
        r"Summarize\s+Summarized using AI\b.*?not guaranteed to be accurate or complete\.",
        re.DOTALL,
    ),
]


def clean_text(text: str) -> str:
    for pattern in _BOILERPLATE_PATTERNS:
        text = pattern.sub("", text)

    # Collapse runs of blank lines/whitespace left over from extraction.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def make_source_slug(url: str) -> str:
    """A short, human-readable, collision-resistant ID prefix for this
    URL's chunks - distinct from the crawler's and pdf_ingest.py's own ID
    schemes, so nothing existing can ever be overwritten."""

    path = url.split("servicenow.com", 1)[-1]
    path = re.sub(r"[^a-zA-Z0-9]+", "-", path).strip("-").lower()
    path = path[:60]  # keep IDs readable
    digest = hashlib.md5(url.encode("utf-8")).hexdigest()[:6]
    return f"curated-{path}-{digest}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--urls-file",
        help="Optional text file, one URL per line ('#' for comments). "
        "Defaults to the CURATED_URLS list in this script.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch, extract, and chunk, but don't embed or upload anything.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-ingest URLs even if ingested_urls.json says they're already done.",
    )
    args = parser.parse_args()

    if args.urls_file:
        raw_lines = Path(args.urls_file).read_text(encoding="utf-8").splitlines()
        urls = [
            line.strip()
            for line in raw_lines
            if line.strip() and not line.strip().startswith("#")
        ]
    else:
        urls = CURATED_URLS

    state = load_state()
    already_done = set(state["ingested"])

    if not args.force:
        skipped = [u for u in urls if u in already_done]
        urls = [u for u in urls if u not in already_done]
        if skipped:
            print(f"Skipping {len(skipped)} already-ingested URL(s). Use --force to redo them.")

    if not urls:
        print("Nothing to do - every URL is already ingested. Use --force to redo them.")
        return

    print(f"Ingesting {len(urls)} specific URL(s){' (dry run)' if args.dry_run else ''}.\n")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )

    all_texts: list[str] = []
    all_ids: list[str] = []
    all_metadatas: list[dict] = []
    newly_done: list[str] = []

    CHUNKS_OUT_DIR.mkdir(exist_ok=True)
    local_records = []

    for url in urls:
        print(f"[fetch] {url}")

        html = fetch(url)
        if html is None:
            continue

        title, text = extract_title_and_text(html, url)
        text = clean_text(text)

        if len(text) < MIN_CONTENT_CHARS:
            print(f"  [skip] too little content ({len(text)} chars) - likely empty/blocked page")
            continue

        pieces = splitter.split_text(text)
        slug = make_source_slug(url)

        for i, piece in enumerate(pieces, start=1):
            chunk_id = f"{slug}-{i:04d}"
            metadata = {
                "source": url,
                "title": title,
                "chunk_id": chunk_id,
                "page_start": "N/A",  # matches rag.py's web-chunk convention
            }
            all_ids.append(chunk_id)
            all_texts.append(piece)
            all_metadatas.append(metadata)
            local_records.append({"text": piece, "metadata": metadata, "chunk_id": chunk_id})

        print(f"  -> '{title}' : {len(pieces)} chunks")
        newly_done.append(url)

        time.sleep(0.5)  # light politeness delay between requests

    if not all_texts:
        print("\nNo chunks produced - nothing to upload.")
        return

    print(f"\n{len(all_texts)} chunk(s) from {len(newly_done)} page(s).")

    if local_records:
        with CHUNKS_OUT_FILE.open("a", encoding="utf-8") as f:
            for record in local_records:
                f.write(json.dumps(record) + "\n")
        print(f"Appended local copy: {CHUNKS_OUT_FILE.relative_to(Path.cwd()) if CHUNKS_OUT_FILE.is_relative_to(Path.cwd()) else CHUNKS_OUT_FILE}")

    if args.dry_run:
        print("\nDry run - nothing embedded or uploaded. Sample chunk:")
        print("-" * 70)
        print(f"ID: {all_ids[0]}")
        print(f"Source: {all_metadatas[0]['source']}")
        print(all_texts[0][:500])
        print("-" * 70)
        return

    if not PINECONE_API_KEY:
        raise SystemExit("PINECONE_API_KEY is missing from .env")

    print("\nLoading embedding model...")
    embeddings = get_embeddings()

    print("Connecting to Pinecone...")
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(PINECONE_INDEX_NAME)

    vector_store = PineconeVectorStore(index=index, embedding=embeddings)

    print(f"Embedding and upserting {len(all_texts)} chunk(s)...")

    BATCH = 100
    for start in range(0, len(all_texts), BATCH):
        end = start + BATCH
        vector_store.add_texts(
            texts=all_texts[start:end],
            metadatas=all_metadatas[start:end],
            ids=all_ids[start:end],
        )
        print(f"  Uploaded {min(end, len(all_texts))}/{len(all_texts)}")

    state["ingested"] = sorted(already_done | set(newly_done))
    save_state(state)

    print(f"\nDone. {len(newly_done)} URL(s) recorded in {STATE_FILE.name}.")


if __name__ == "__main__":
    main()