import json
input_file = "chunks/discovery_chunks_with_metadata.jsonl"
with open(input_file, "r", encoding="utf-8") as f:
    chunks = [json.loads(line) for line in f if line.strip()]
print("Total chunks:", len(chunks))
for chunk in chunks:
    print("\nChunk ID:", chunk["metadata"]["chunk_id"])
    print("Section:", chunk["metadata"]["section"])
    print("Characters:", chunk["metadata"]["character_count"])
    print("Estimated tokens:", chunk["metadata"]["estimated_tokens"])