import json
import re
from pathlib import Path
from collections import defaultdict

INPUT_FILE = Path("all_chunks.jsonl")
OUTPUT_FILE = Path("deduplicated_chunks.jsonl")
REPORT_FILE = Path("duplicates_removed_report.txt")

def normalize_text(text):
    """Ignore capitalization and whitespace differences."""
    return re.sub(r"\s+", " ", text.strip()).casefold()

unique_chunks = {}
duplicate_groups = defaultdict(list)

total_chunks = 0

with INPUT_FILE.open("r", encoding="utf-8") as infile:
    for line_number, line in enumerate(infile, start=1):
        if not line.strip():
            continue

        total_chunks += 1
        chunk = json.loads(line)

        text = chunk.get("text", "")

        if not isinstance(text, str) or not text.strip():
            # Keep malformed/empty records separate for investigation.
            key = f"__empty_or_invalid_{line_number}"
        else:
            key = normalize_text(text)

        if key not in unique_chunks:
            unique_chunks[key] = chunk
            duplicate_groups[key].append({
                "line": line_number,
                "chunk_id": chunk.get("chunk_id"),
                "metadata": chunk.get("metadata", {})
            })
        else:
            duplicate_groups[key].append({
                "line": line_number,
                "chunk_id": chunk.get("chunk_id"),
                "metadata": chunk.get("metadata", {})
            })

# Preserve the original metadata and add all duplicate locations.
for key, occurrences in duplicate_groups.items():
    if len(occurrences) <= 1:
        continue

    canonical_chunk = unique_chunks[key]
    metadata = canonical_chunk.setdefault("metadata", {})

    locations = []

    for occurrence in occurrences:
        original_metadata = occurrence.get("metadata", {})

        locations.append({
            "chunk_id": occurrence.get("chunk_id"),
            "page_start": original_metadata.get("page_start"),
            "page_end": original_metadata.get("page_end")
        })

    # JSON string is used so the value remains simple metadata.
    metadata["duplicate_locations"] = json.dumps(
        locations, ensure_ascii=False
    )

# Write the deduplicated output.
with OUTPUT_FILE.open("w", encoding="utf-8") as outfile:
    for chunk in unique_chunks.values():
        outfile.write(
            json.dumps(chunk, ensure_ascii=False) + "\n"
        )

# Write the duplicate report.
duplicate_count = 0

with REPORT_FILE.open("w", encoding="utf-8") as report:
    report.write("DUPLICATE REMOVAL REPORT\n")
    report.write("=======================\n\n")
    report.write(f"Original chunks: {total_chunks}\n")
    report.write(f"Unique chunks: {len(unique_chunks)}\n")

    for key, occurrences in duplicate_groups.items():
        if len(occurrences) <= 1:
            continue

        removed = len(occurrences) - 1
        duplicate_count += removed

        report.write("\n------------------------\n")
        report.write(f"Occurrences: {len(occurrences)}\n")
        report.write(f"Copies removed: {removed}\n")

        for occurrence in occurrences:
            report.write(
                f"Line {occurrence['line']} | "
                f"Chunk ID: {occurrence['chunk_id']} | "
                f"Metadata: {occurrence['metadata']}\n"
            )

        report.write(f"Text preview: {key[:300]}\n")

    report.write("\n------------------------\n")
    report.write(f"Total duplicate copies removed: {duplicate_count}\n")

print("Deduplication complete!")
print(f"Original chunks: {total_chunks}")
print(f"Unique chunks: {len(unique_chunks)}")
print(f"Duplicate copies removed: {duplicate_count}")
print(f"Output: {OUTPUT_FILE.resolve()}")
print(f"Report: {REPORT_FILE.resolve()}")