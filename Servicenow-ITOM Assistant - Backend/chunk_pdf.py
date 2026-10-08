import json
from pathlib import Path
from langchain_text_splitters import RecursiveCharacterTextSplitter

# -----------------------------------
# 1. File paths
# -----------------------------------

INPUT_FILE = Path("extracted_pages.jsonl")
OUTPUT_FILE = Path("all_chunks.jsonl")

# -----------------------------------
# 2. Chunking configuration
# -----------------------------------

BATCH_SIZE = 100       # Pages processed per batch
CHUNK_SIZE = 1000      # Characters per chunk
CHUNK_OVERLAP = 150    # Overlapping characters

splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", ". ", " ", ""]
)

# -----------------------------------
# 3. Validate input file
# -----------------------------------

if not INPUT_FILE.exists():
    raise FileNotFoundError(
        f"Input file not found: {INPUT_FILE.resolve()}"
    )

# -----------------------------------
# 4. Chunk the extracted pages
# -----------------------------------

total_pages = 0
total_chunks = 0
batch = []

# "w" creates a fresh output file each run
with INPUT_FILE.open("r", encoding="utf-8") as infile, \
     OUTPUT_FILE.open("w", encoding="utf-8") as outfile:

    def process_batch(pages, first_chunk_id):
        """Split a batch of pages and write its chunks."""

        batch_chunks = []
        next_chunk_id = first_chunk_id

        for page in pages:
            page_number = page["page_number"]
            text = page.get("text", "").strip()

            # Skip pages with no extractable text
            if not text:
                continue

            page_chunks = splitter.split_text(text)

            for chunk_text in page_chunks:
                record = {
                    "chunk_id": next_chunk_id,
                    "text": chunk_text,
                    "metadata": {
                        "source": INPUT_FILE.name,
                        "page_start": page_number,
                        "page_end": page_number,
                        "character_count": len(chunk_text),
                        "estimated_tokens": len(chunk_text.split())
                    }
                }

                batch_chunks.append(record)
                next_chunk_id += 1

        # Write batch results immediately
        for chunk in batch_chunks:
            outfile.write(
                json.dumps(chunk, ensure_ascii=False) + "\n"
            )

        return len(batch_chunks)

    for line in infile:
        if not line.strip():
            continue

        page = json.loads(line)
        batch.append(page)
        total_pages += 1

        if len(batch) == BATCH_SIZE:
            created = process_batch(batch, total_chunks + 1)
            total_chunks += created
            batch = []

            print(
                f"Processed {total_pages} pages | "
                f"Created {total_chunks} chunks"
            )

    # Process the final partial batch
    if batch:
        created = process_batch(batch, total_chunks + 1)
        total_chunks += created

        print(
            f"Processed {total_pages} pages | "
            f"Created {total_chunks} chunks"
        )

print("\nChunking complete!")
print(f"Pages processed: {total_pages}")
print(f"Total chunks created: {total_chunks}")
print(f"Output saved to: {OUTPUT_FILE.resolve()}")