from pathlib import Path
import re
import json

INPUT_FILE = Path("sample_extraction/discovery_pages_756_759.txt")
OUTPUT_DIR = Path("chunks")
OUTPUT_DIR.mkdir(exist_ok=True)

text = INPUT_FILE.read_text(encoding="utf-8")

# Remove PDF page marker lines
text = re.sub(r"===== PDF PAGE \d+ =====", "", text)

# Remove common copyright/footer lines
text = re.sub(r"©.*", "", text)
text = re.sub(r"Other company names.*", "", text)
text = re.sub(r"ServiceNow,.*trademarks.*", "", text)

# Normalize whitespace
text = re.sub(r"[ \t]+", " ", text)
text = re.sub(r"\n\s*\n+", "\n\n", text)
text = text.strip()

# Headings to use as section boundaries
headings = [
    "Exploring Discovery",
    "Horizontal discovery and top-down discovery",
    "Probes, sensors, and patterns",
    "Horizontal discovery phases",
    "Discovery communication through MID Servers",
    "Types of discovery",
    "IP service affinity",
    "Horizontal discovery process flow with probes and sensors",
    "Kicking off Discovery",
    "Scanning phase",
    "Classification phase",
]

# Build a regex that recognizes these headings
heading_pattern = re.compile(
    r"(?m)^\s*(" + "|".join(
        re.escape(h) for h in sorted(headings, key=len, reverse=True)
    ) + r")\s*$"
)

matches = list(heading_pattern.finditer(text))

sections = []

for i, match in enumerate(matches):
    start = match.start()
    end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

    section_title = match.group(1)
    section_text = text[start:end].strip()

    if section_text:
        sections.append({
            "section": section_title,
            "text": section_text
        })

# Split long sections while keeping some overlap
chunk_size = 1200
overlap = 200

chunks = []

for section in sections:
    section_text = section["text"]
    start = 0

    while start < len(section_text):
        end = start + chunk_size
        chunk_text = section_text[start:end].strip()

        if chunk_text:
            chunks.append({
                "chunk_id": len(chunks) + 1,
                "source": INPUT_FILE.name,
                "section": section["section"],
                "text": chunk_text
            })

        if end >= len(section_text):
            break

        start += chunk_size - overlap

# Save JSONL: one chunk per line
output_file = OUTPUT_DIR / "discovery_chunks.jsonl"

with output_file.open("w", encoding="utf-8") as f:
    for chunk in chunks:
        f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

# Print a preview
for chunk in chunks:
    print(f"\n--- Chunk {chunk['chunk_id']} ---")
    print(f"Section: {chunk['section']}")
    print(chunk["text"])

print(f"\nTotal chunks: {len(chunks)}")
print(f"Saved to: {output_file}")
