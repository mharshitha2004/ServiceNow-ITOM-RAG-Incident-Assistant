
import json
import os
import time

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone

# -----------------------------
# 1. Configuration
# -----------------------------

load_dotenv()

API_KEY = os.getenv("PINECONE_API_KEY")
INDEX_NAME = os.getenv(
    "PINECONE_INDEX_NAME",
    "servicenow-itom-docs"
)

INPUT_FILE = "deduplicated_chunks.jsonl"

BATCH_SIZE = 100
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

if not API_KEY:
    raise ValueError(
        "PINECONE_API_KEY is missing. "
        "Please add it to your .env file."
    )

# -----------------------------
# 2. Load embedding model
# -----------------------------

print("Loading embedding model...")

model = SentenceTransformer(EMBEDDING_MODEL)

print("Embedding model loaded.")
print("Vector dimension:", model.get_sentence_embedding_dimension())

# -----------------------------
# 3. Connect to Pinecone
# -----------------------------

print("Connecting to Pinecone...")

pc = Pinecone(api_key=API_KEY)
index = pc.Index(INDEX_NAME)

print("Connected to index:", INDEX_NAME)

# -----------------------------
# 4. Read JSONL chunks
# -----------------------------

print("Reading chunks...")

chunks = []

with open(INPUT_FILE, "r", encoding="utf-8") as file:
    for line_number, line in enumerate(file, start=1):
        if not line.strip():
            continue

        try:
            chunk = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"Invalid JSON on line {line_number}"
            ) from error

        chunk_id = chunk.get("chunk_id")
        text = chunk.get("text")
        metadata = chunk.get("metadata", {})

        if not chunk_id:
            raise ValueError(
                f"Missing chunk_id on line {line_number}"
            )

        if not isinstance(text, str) or not text.strip():
            raise ValueError(
                f"Missing or empty text on line {line_number}"
            )

        chunks.append({
            "id": str(chunk_id),
            "text": text,
            "metadata": metadata
        })

print(f"Loaded {len(chunks):,} chunks.")

# -----------------------------
# 5. Create embeddings and upload
# -----------------------------

total_chunks = len(chunks)
uploaded = 0

print("Starting embedding and upload...")

for start in range(0, total_chunks, BATCH_SIZE):
    batch = chunks[start:start + BATCH_SIZE]

    texts = [item["text"] for item in batch]

    # Generate normalized 384-dimensional embeddings
    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False
    )

    vectors = []

    for item, embedding in zip(batch, embeddings):
        metadata = dict(item["metadata"])

        # Store text with the vector so retrieved results
        # can be used as context in the RAG pipeline.
        metadata["text"] = item["text"]

        vectors.append({
            "id": item["id"],
            "values": embedding.tolist(),
            "metadata": metadata
        })

    # Upload this batch
    index.upsert(vectors=vectors)

    uploaded += len(batch)

    print(
        f"Uploaded {uploaded:,} / {total_chunks:,} chunks"
    )

print("\nUpload completed!")
print(f"Total vectors submitted: {uploaded:,}")

# -----------------------------
# 6. Verify index statistics
# -----------------------------

print("\nChecking Pinecone index statistics...")

time.sleep(2)

stats = index.describe_index_stats()

print(stats)