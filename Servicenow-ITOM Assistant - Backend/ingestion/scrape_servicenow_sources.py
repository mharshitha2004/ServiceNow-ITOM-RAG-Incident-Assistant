"""
Crawl ServiceNow's own Community and product-docs sites, keep only pages
that look like they're about ITOM or Asset Management (SAMP/HAM/ITAM),
chunk them the same way as your PDFs, and add them to the SAME Pinecone
index - additively, same as pdf_ingest.py.

READ THIS FIRST:

1. ServiceNow's official numbered Support KB (articles like KB1584544,
   at support.servicenow.com) sits behind a customer login. No scraper
   can reach those - that requires a real authenticated session, which
   this script deliberately does not attempt (see the note at the
   bottom of this docstring if you have valid support credentials and
   want that anyway).

2. Separately from that, and separately from the discussion forums,
   ServiceNow Community runs its own public "Articles" spaces - genuine
   KB-style reference content with no login wall. SEED_URLS below
   points at the ITOM / CMDB / Asset Management community spaces and at
   the public product docs. The crawler will discover more articles in the
   same spaces via on-page links that match KEYWORD_ALLOWLIST. I could
   not confirm a HAM- or SAM-specific article space exists (community
   URLs mentioning "ham-articles" turned up in search results but I
   couldn't verify a working listing page for it) - CANDIDATE_SEEDS
   below lists a few worth checking by hand and adding to SEED_URLS
   yourself if they resolve.

2. Whether crawling is allowed. I have no network access from here, so I
   could not check robots.txt or ServiceNow's Terms of Use for either
   site. Check both yourself before running this against their servers,
   and keep REQUEST_DELAY_SECONDS at a polite value (2s+) regardless.

How scope is enforced (so this stays "ITOM + Asset Management only"):
  - ALLOWED_DOMAINS restricts every fetch to ServiceNow's own domains.
  - KEYWORD_ALLOWLIST is checked against each discovered link's URL and
    link text; a link is only followed if it matches. Adjust the list
    to tighten or loosen scope.
  - MAX_PAGES caps the whole run so a misconfigured seed can't crawl the
    entire site.

Why this can't collide with your existing (or the PDF-ingested) vectors:
  same additive-only add_texts()-by-new-id approach as pdf_ingest.py, IDs
  prefixed "community-" or "docs-" plus a slug of the URL.

State file (scraped_urls.json) records every URL already ingested and the
vector IDs it produced, so re-running the script skips pages it has
already scraped - safe to re-run on a schedule. Use --force to re-scrape
and overwrite (by the SAME ids, so this is the one case that DOES
intentionally update existing vectors - only ones this script created).

Usage:
    pip install langchain langchain-community langchain-pinecone \\
                langchain-huggingface langchain-text-splitters \\
                beautifulsoup4 requests

    python ingestion/scrape_servicenow_sources.py --dry-run
    python ingestion/scrape_servicenow_sources.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pinecone import Pinecone
from langchain_pinecone import PineconeVectorStore

import sys

sys.path.append(str(Path(__file__).resolve().parent))
from embeddings import get_embeddings  # noqa: E402

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration - review and adjust before running for real
# ---------------------------------------------------------------------------

SEED_URLS = [
    # Community spaces. Listing pages are only used to discover links; they
    # are not indexed themselves (see NO_INDEX_URL_PATTERNS).
    "https://www.servicenow.com/community/itom/ct-p/it-operations-management",
    "https://www.servicenow.com/community/itom-articles/tkb-p/it-operations-management-kb",
    "https://www.servicenow.com/community/cmdb-articles/tkb-p/configuration-management-db-kb",
    "https://www.servicenow.com/community/sam/ct-p/it-asset-management",
    # Public docs. Old "docs/bundle/<product>" landing URLs return no text
    # (JavaScript-rendered), so these are real content pages instead.
    "https://www.servicenow.com/docs/r/it-operations-management/r_ITOMApplications.html",
    # IT Asset Management docs (Yokohama release - confirmed reachable, older).
    "https://www.servicenow.com/docs/r/yokohama/it-asset-management/it-asset-management.html",
]

# Not confirmed - turned up in search results but I could not verify these
# resolve. Worth checking by hand; add to SEED_URLS above if they do.
CANDIDATE_SEEDS = [
    "https://www.servicenow.com/community/ham-articles",
    "https://www.servicenow.com/community/ham-forum/it-asset-management/td-p/3382464",
    "https://www.servicenow.com/community/sam-articles",
    # Latest-release ITAM docs, by analogy with the ITOM URL above. Open it in
    # a browser first; if it loads, add it to SEED_URLS.
    "https://www.servicenow.com/docs/r/it-asset-management/it-asset-management.html",
]

ALLOWED_DOMAINS = {
    "www.servicenow.com",
    "community.servicenow.com",
    "docs.servicenow.com",
}

# ---------------------------------------------------------------------------
# Optional: authenticated access to the real Support KB (support.servicenow.com)
#
# The numbered KB articles (KB1584544-style) require a logged-in session.
# This script can't script an actual login (2FA, SSO, etc. vary per org),
# but if you already have a valid support.servicenow.com login in your
# browser, you can hand this script that session's cookie and it will use
# it for every request:
#
#   1. Log in to support.servicenow.com in your browser as normal.
#   2. Open DevTools -> Application/Storage -> Cookies -> support.servicenow.com.
#   3. Copy every cookie as "name1=value1; name2=value2; ..." (or just the
#      session cookie your org uses - varies by SSO setup).
#   4. Add to your .env:  SUPPORT_SESSION_COOKIE="name1=value1; name2=value2"
#   5. Add a KB search/listing URL to SEED_URLS, e.g.
#      "https://support.servicenow.com/kb?id=kb_search&query=ITOM"
#
# Without SUPPORT_SESSION_COOKIE set, support.servicenow.com is left out of
# ALLOWED_DOMAINS entirely, so nothing tries to hit its login wall.
# Session cookies expire - if pages start coming back as login pages, your
# copied cookie is stale; repeat the steps above.
# ---------------------------------------------------------------------------

SUPPORT_SESSION_COOKIE = os.getenv("SUPPORT_SESSION_COOKIE", "").strip()

if SUPPORT_SESSION_COOKIE:
    ALLOWED_DOMAINS.add("support.servicenow.com")

# A discovered link is only followed if its URL or visible text contains
# one of these (case-insensitive). Keeps the crawl to ITOM + SAMP/HAM.
KEYWORD_ALLOWLIST = [
    "itom", "it-operations-management",
    "discovery", "mid-server", "mid server",
    "service-mapping", "service mapping",
    "event-management", "event management",
    "orchestration", "cloud-management", "cloud management",
    "cmdb", "aiops",
    "asset-management", "asset management", "itam",
    "hardware-asset", "hardware asset", "ham",
    "software-asset", "software asset", "samp", "sam",
]

MAX_PAGES = 400
REQUEST_DELAY_SECONDS = 2.0
REQUEST_TIMEOUT = 20
MIN_ARTICLE_CHARS = 300  # shorter than this is almost always nav/boilerplate

# Max pages indexed per site section in ONE run, so one huge docs area (e.g.
# Cloud Account Management) can't use up the whole budget before Asset
# Management is reached. Skipped URLs are kept for the next run.
MAX_PAGES_PER_SECTION = 40
MAX_FRONTIER = 20000
# Hard stop on total requests (including skipped/listing pages) per run, as a
# multiple of the page budget, so a run can't spend forever on listing pages.
MAX_FETCH_MULTIPLIER = 3
FRONTIER_KEY = "__frontier__"

# Set True to skip Community forum Q&A threads (often unanswered questions)
# and keep only docs, articles and blog posts.
BLOCK_FORUM_THREADS = False

# Links matching any of these are never queued (kudos widgets, RSS feeds,
# attachments, pagination, event pages, tag listings, login redirects).
BLOCKED_URL_PATTERNS = [
    r"/kudos/", r"kudosbuttonv2", r"/rss/", r"/attachments/",
    r"/label-name/", r"/thread-id/", r"/occasions/", r"sso_login_redirect",
    r"categorypage", r"/(?:ev|ec|eb)-p/", r"/(?:ba|ta|td)-p/\d+/page/\d+",
    # member profile pages (personal info, no documentation value), search/UI
    # widgets, and marketing pages / PDFs that return 403 to scripts anyway
    r"/community/user/", r"viewprofilepage", r"enableautocomplete",
    r"/community/tkb/v2/", r"/products/", r"/content/dam/",
    # Variants of pages we already get from their normal URL: comment/reply
    # permalinks, highlighted views, and print versions of forum threads and
    # KB articles (blog print pages are NOT blocked - they're the only way to
    # get blog text). These produced duplicates and untitled fragments.
    r"/highlight/", r"/emcs_t/", r"/tac-p/", r"/bc-p/", r"/comment-id/",
    r"forumtopicprintpage", r"/tkb/articleprintpage/",
]
if BLOCK_FORUM_THREADS:
    BLOCKED_URL_PATTERNS.append(r"-forum/")

# Listing/index pages: fetched so their links can be followed, but never
# chunked or uploaded.
NO_INDEX_URL_PATTERNS = [r"/(?:ct|bd|tkb|bg)-p/", r"community\.servicenow\.com/community/?$"]

# Lines the docs site injects into every page; they add noise to chunk 1.
BOILERPLATE_LINES = {"summarize", "summarized using ai", "show full answer", "show less"}
BOILERPLATE_PREFIXES = ("this content was generated using new openai",)

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
BATCH_SIZE = 100

STATE_FILE = Path("scraped_urls.json")
CHUNKS_OUT_DIR = Path("chunks")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; ITOMAssistantIngestBot/1.0; "
        "internal documentation ingestion)"
    )
}


# ---------------------------------------------------------------------------
# Fetching and scoping
# ---------------------------------------------------------------------------


def _build_allowlist_regex() -> re.Pattern:
    # Short keywords ("ham", "sam", "itom"...) must match as whole tokens, or
    # "ham" would match "graham", "champion", "shampoo" and drag in junk.
    parts = []
    for keyword in KEYWORD_ALLOWLIST:
        keyword = keyword.strip().lower()
        escaped = re.escape(keyword)
        if len(keyword) <= 4:
            parts.append(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])")
        else:
            parts.append(escaped)
    return re.compile("|".join(parts))


ALLOWLIST_RE = _build_allowlist_regex()
BLOCKED_RE = re.compile("|".join(BLOCKED_URL_PATTERNS))
NO_INDEX_RE = re.compile("|".join(NO_INDEX_URL_PATTERNS))


def matches_allowlist(text: str) -> bool:
    return bool(ALLOWLIST_RE.search(text.lower()))


def is_blocked(url: str) -> bool:
    return bool(BLOCKED_RE.search(url))


def is_listing_page(url: str) -> bool:
    return bool(NO_INDEX_RE.search(url))


_THREAD_RE = re.compile(
    r"/community/(?P<board>[^/]+)/[^/]+/(?:td|m|ta|ba)-p/(?P<id>\d+)"
)


def thread_key(url: str) -> str | None:
    """Same post can be reached as .../td-p/<id> and .../m-p/<id>. Returning
    the same key for both lets us skip the second one *before* fetching it."""
    match = _THREAD_RE.search(url)
    return f"{match.group('board')}/{match.group('id')}" if match else None


def section_key(url: str) -> str:
    """Coarse 'area of the site' used to cap pages per section per run."""
    parts = [p for p in urlparse(url).path.split("/") if p]
    if len(parts) >= 3 and parts[0] == "docs":
        return "/".join(parts[:3])  # docs/r/<product-or-release>
    if len(parts) >= 2 and parts[0] == "community":
        return "/".join(parts[:2])  # community/<board>
    return parts[0] if parts else ""


def _cookies_for(url: str) -> dict:
    if not SUPPORT_SESSION_COOKIE or "support.servicenow.com" not in url:
        return {}
    cookies = {}
    for pair in SUPPORT_SESSION_COOKIE.split(";"):
        if "=" in pair:
            name, _, value = pair.strip().partition("=")
            cookies[name] = value
    return cookies


def fetch(url: str) -> tuple[BeautifulSoup | None, bool]:
    """Return (soup, retry_later). retry_later is True for timeouts, connection
    errors and 5xx responses; 4xx (404 etc.) are treated as permanent."""
    try:
        response = requests.get(
            url, headers=HEADERS, cookies=_cookies_for(url), timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
    except requests.exceptions.HTTPError as error:
        print(f"  [skip] {url} -> {error}")
        status = error.response.status_code if error.response is not None else 0
        return None, status >= 500
    except requests.exceptions.RequestException as error:
        print(f"  [skip] {url} -> {error}")
        return None, True

    return BeautifulSoup(response.text, "html.parser"), False


def discover_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    found = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        link_text = a.get_text(" ", strip=True)

        try:
            absolute = urljoin(base_url, href)
            parsed = urlparse(absolute)
        except ValueError:
            continue  # malformed link (e.g. broken IPv6 bracket) - ignore it

        if parsed.scheme not in ("http", "https"):
            continue
        if parsed.netloc not in ALLOWED_DOMAINS:
            continue
        if is_blocked(absolute):
            continue
        if not matches_allowlist(absolute) and not matches_allowlist(link_text):
            continue

        # Drop fragment/query noise so the same page isn't queued twice
        # under slightly different URLs.
        clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        found.append(clean)

    return found


def extract_article(soup: BeautifulSoup) -> tuple[str, str]:
    """Return (title, main_text), stripped of nav/footer/script noise."""

    title_tag = soup.find("h1") or soup.find("title")
    title = title_tag.get_text(" ", strip=True) if title_tag else "Untitled"

    for tag in soup(["script", "style", "nav", "header", "footer", "form"]):
        tag.decompose()

    # Prefer a real content container if the page has one; fall back to body.
    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find(attrs={"role": "main"})
        or soup.body
    )

    text = main.get_text("\n", strip=True) if main else ""
    lines = [
        line
        for line in text.split("\n")
        if line.strip().lower() not in BOILERPLATE_LINES
        and not line.strip().lower().startswith(BOILERPLATE_PREFIXES)
    ]
    text = re.sub(r"\n{2,}", "\n\n", "\n".join(lines))

    return title, text


def slugify(url: str) -> str:
    path = urlparse(url).path.strip("/")
    slug = re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-")
    return slug[:80] or "page"


def source_prefix(url: str) -> str:
    parsed = urlparse(url)
    is_community = "community" in parsed.netloc or parsed.path.startswith("/community/")
    return "community" if is_community else "docs"


def page_slug(url: str) -> str:
    # slugify() truncates to 80 chars, which made different long URLs share
    # the same slug (and therefore the same vector IDs, silently overwriting
    # each other). The URL hash makes every page's IDs unique.
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    return f"{source_prefix(url)}-{slugify(url)}-{digest}"


# ---------------------------------------------------------------------------
# Chunking (identical parameters to pdf_ingest.py / chunk_pdf.py)
# ---------------------------------------------------------------------------


def chunk_page(url: str, title: str, text: str) -> list[dict]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunks = []
    for piece in splitter.split_text(text):
        piece = piece.strip()
        if not piece:
            continue

        chunks.append(
            {
                "text": piece,
                "metadata": {
                    "source": url,
                    "title": title,
                    # No page numbers for web content; rag.py's context
                    # formatting falls back to these when page_start is
                    # absent (see the rag.py update alongside this file).
                    "page_start": "N/A",
                    "page_end": "N/A",
                    "character_count": len(piece),
                    "estimated_tokens": len(piece.split()),
                },
            }
        )

    return chunks


# ---------------------------------------------------------------------------
# State (so re-runs are incremental, not full re-scrapes)
# ---------------------------------------------------------------------------


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main crawl
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Crawl and print what would be scraped/chunked - no Pinecone or disk writes.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-scrape and overwrite pages already recorded in scraped_urls.json.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=MAX_PAGES,
        help=f"Crawl budget (default {MAX_PAGES}).",
    )
    args = parser.parse_args()

    state = {} if args.force else load_state()
    # Links found in earlier runs but not visited yet (budget/section cap hit).
    frontier = [] if args.force else state.pop(FRONTIER_KEY, [])

    to_visit = list(SEED_URLS) + [u for u in frontier if u not in SEED_URLS]
    visited: set[str] = set()
    deferred: list[str] = []  # skipped this run because their section hit its cap
    retry: list[str] = []  # transient fetch failures (timeouts, 5xx)
    section_counts: dict[str, int] = {}
    # Fingerprints of pages already collected, so the same forum thread
    # reached via both /td-p/ and /m-p/ URLs isn't indexed twice.
    seen_fingerprints = {
        v["fp"] for v in state.values() if isinstance(v, dict) and v.get("fp")
    }
    seen_thread_keys = {
        v["tk"] for v in state.values() if isinstance(v, dict) and v.get("tk")
    }
    fetch_count = 0
    max_fetches = args.max_pages * MAX_FETCH_MULTIPLIER
    all_new_chunks: list[dict] = []
    all_new_ids: list[str] = []
    pages_scraped = 0

    print(
        f"Starting crawl from {len(SEED_URLS)} seed URL(s) + {len(frontier)} queued from "
        f"earlier runs, budget {args.max_pages} pages, {MAX_PAGES_PER_SECTION} per section."
    )

    while to_visit and pages_scraped < args.max_pages and fetch_count < max_fetches:
        url = to_visit.pop(0)
        if url in visited:
            continue
        visited.add(url)

        if url in state and not args.force:
            print(f"[cached] {url} (already scraped - use --force to redo)")
            continue

        tkey = thread_key(url)
        if tkey and tkey in seen_thread_keys:
            print(f"[skip] {url} (same post already collected)")
            continue

        section = section_key(url)
        if not is_listing_page(url) and section_counts.get(section, 0) >= MAX_PAGES_PER_SECTION:
            deferred.append(url)
            continue

        print(f"[fetch] {url}")
        fetch_count += 1
        soup, retryable = fetch(url)
        time.sleep(REQUEST_DELAY_SECONDS)
        if soup is None:
            if retryable:
                retry.append(url)
            continue

        # Queue newly discovered, in-scope links for later.
        for link in discover_links(soup, url):
            if link not in visited and link not in state:
                to_visit.append(link)

        if is_listing_page(url):
            print("  [listing] links followed, page not indexed")
            continue

        title, text = extract_article(soup)
        if len(text) < MIN_ARTICLE_CHARS:
            print(f"  [skip] too little content ({len(text)} chars) - likely a listing/nav page")
            continue

        fingerprint = hashlib.sha1(
            (title.lower() + "|" + re.sub(r"\s+", " ", text[:500]).lower()).encode("utf-8")
        ).hexdigest()
        if fingerprint in seen_fingerprints:
            print("  [skip] duplicate of a page already collected")
            state[url] = {"title": title, "ids": [], "fp": fingerprint, "duplicate": True}
            if tkey:
                state[url]["tk"] = tkey
                seen_thread_keys.add(tkey)
            continue

        page_chunks = chunk_page(url, title, text)
        if not page_chunks:
            continue

        slug = page_slug(url)
        page_ids = [f"{slug}-{i:04d}" for i in range(1, len(page_chunks) + 1)]
        for chunk, chunk_id in zip(page_chunks, page_ids):
            chunk["chunk_id"] = chunk_id

        print(f"  -> '{title}' : {len(page_chunks)} chunks")

        all_new_chunks.extend(page_chunks)
        all_new_ids.extend(page_ids)
        state[url] = {"title": title, "ids": page_ids, "fp": fingerprint}
        if tkey:
            state[url]["tk"] = tkey
            seen_thread_keys.add(tkey)
        seen_fingerprints.add(fingerprint)
        section_counts[section] = section_counts.get(section, 0) + 1
        pages_scraped += 1

    if fetch_count >= max_fetches and pages_scraped < args.max_pages:
        print(f"Stopped after {fetch_count} requests (limit {max_fetches}); rest is queued.")

    # Everything discovered but not processed goes to the next run.
    pending = deferred + retry + [u for u in to_visit if u not in visited and u not in state]
    pending = list(dict.fromkeys(pending))[:MAX_FRONTIER]

    print(f"\nCrawled {pages_scraped} new page(s), {len(all_new_chunks)} chunk(s) total.")
    print(f"{len(pending)} discovered URL(s) queued for the next run.")

    if not all_new_chunks:
        print("Nothing new to upload.")
        if not args.dry_run:
            save_state({**state, FRONTIER_KEY: pending})
        return

    if args.dry_run:
        print("\n--dry-run: nothing written. Sample chunk:")
        print(json.dumps(all_new_chunks[0], ensure_ascii=False, indent=2)[:800])
        return

    CHUNKS_OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CHUNKS_OUT_DIR / "servicenow_web_chunks.jsonl"
    # Append so multiple runs accumulate into one local file for neighbor lookup.
    with out_path.open("a", encoding="utf-8") as f:
        for chunk in all_new_chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    print(f"Appended local copy: {out_path}")

    api_key = os.getenv("PINECONE_API_KEY")
    index_name = os.getenv("PINECONE_INDEX_NAME", "servicenow-itom-docs")
    if not api_key:
        raise ValueError("PINECONE_API_KEY is missing. Add it to your .env file.")

    pc = Pinecone(api_key=api_key)
    index = pc.Index(index_name)
    vector_store = PineconeVectorStore(index=index, embedding=get_embeddings(), text_key="text")

    texts = [c["text"] for c in all_new_chunks]
    metadatas = [c["metadata"] for c in all_new_chunks]

    print("Embedding and upserting...")
    for start in range(0, len(all_new_chunks), BATCH_SIZE):
        end = start + BATCH_SIZE
        vector_store.add_texts(
            texts=texts[start:end], metadatas=metadatas[start:end], ids=all_new_ids[start:end]
        )
        print(f"Uploaded {min(end, len(all_new_chunks))}/{len(all_new_chunks)}")

    save_state({**state, FRONTIER_KEY: pending})
    print(f"\nDone. State saved to {STATE_FILE} ({len(state)} URLs recorded, {len(pending)} queued).")


if __name__ == "__main__":
    main()