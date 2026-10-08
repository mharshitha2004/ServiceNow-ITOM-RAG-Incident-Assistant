import json
from pathlib import Path

# Input: your latest cleaned JSONL file
input_file = Path("chunks/discovery_chunks_fixed.jsonl")

# Output: JSONL with metadata added
output_file = Path("chunks/discovery_chunks_with_metadata.jsonl")

def estimate_tokens(text):
    """
    Rough token estimate.
    This is only an approximation, not an exact tokenizer count.
    """
    return len(text.split())

chunks_processed = 0

with input_file.open("r", encoding="utf-8") as infile, \
     output_file.open("w", encoding="utf-8") as outfile:

    for line_number, line in enumerate(infile, start=1):
        if not line.strip():
            continue

        chunk = json.loads(line)

        # Validate required fields
        if "text" not in chunk:
            raise ValueError(
                f"Line {line_number} is missing the 'text' field"
            )

        text = chunk["text"]

        # Add metadata without modifying the original text
        chunk["metadata"] = {
            "chunk_id": chunk.get("chunk_id", chunks_processed + 1),
            "source": input_file.name,
            "section": chunk.get("section", "Unknown"),
            "character_count": len(text),
            "estimated_tokens": estimate_tokens(text)
        }

        outfile.write(
            json.dumps(chunk, ensure_ascii=False) + "\n"
        )

        chunks_processed += 1

print("Metadata added successfully!")
print(f"Chunks processed: {chunks_processed}")
print(f"Output file: {output_file}")