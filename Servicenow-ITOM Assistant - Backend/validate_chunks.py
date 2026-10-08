import json
import re
from pathlib import Path
from collections import Counter

# Input and output files
INPUT_FILE = Path("all_chunks.jsonl")
REPORT_FILE = Path("chunk_quality_report.txt")
FLAGGED_FILE = Path("flagged_chunks.jsonl")

# Thresholds for identifying suspicious chunks
MIN_CHARS = 100
MAX_CHARS = 2000

total_lines = 0
valid_chunks = []
issues = []
duplicate_texts = Counter()
chunk_ids = Counter()

# ---------------------------------
# 1. Read and validate JSONL records
# ---------------------------------

with INPUT_FILE.open("r", encoding="utf-8") as file:
    for line_number, line in enumerate(file, start=1):
        total_lines += 1

        try:
            chunk = json.loads(line)
        except json.JSONDecodeError as error:
            issues.append({
                "line": line_number,
                "issue": f"Invalid JSON: {error}",
                "chunk": None
            })
            continue

        if not isinstance(chunk, dict):
            issues.append({
                "line": line_number,
                "issue": "Record is not a JSON object",
                "chunk": chunk
            })
            continue

        valid_chunks.append(chunk)

        # ---------------------------------
        # 2. Check required fields
        # ---------------------------------

        required_fields = ["chunk_id", "text", "metadata"]

        for field in required_fields:
            if field not in chunk:
                issues.append({
                    "line": line_number,
                    "issue": f"Missing field: {field}",
                    "chunk": chunk
                })

        text = chunk.get("text", "")
        metadata = chunk.get("metadata")

        if not isinstance(text, str):
            issues.append({
                "line": line_number,
                "issue": "Text is not a string",
                "chunk": chunk
            })
            continue

        # ---------------------------------
        # 3. Check empty or short text
        # ---------------------------------

        cleaned_text = text.strip()

        if not cleaned_text:
            issues.append({
                "line": line_number,
                "issue": "Empty text",
                "chunk": chunk
            })
        elif len(cleaned_text) < MIN_CHARS:
            issues.append({
                "line": line_number,
                "issue": f"Very short text: {len(cleaned_text)} chars",
                "chunk": chunk
            })

        # ---------------------------------
        # 4. Check unusually large chunks
        # ---------------------------------

        if len(text) > MAX_CHARS:
            issues.append({
                "line": line_number,
                "issue": f"Large chunk: {len(text)} chars",
                "chunk": chunk
            })

        # ---------------------------------
        # 5. Check duplicate text
        # ---------------------------------

        normalized_text = re.sub(r"\s+", " ", cleaned_text).lower()

        if normalized_text:
            duplicate_texts[normalized_text] += 1

        # ---------------------------------
        # 6. Check chunk IDs
        # ---------------------------------

        chunk_id = chunk.get("chunk_id")

        if chunk_id is not None:
            chunk_ids[str(chunk_id)] += 1

        # ---------------------------------
        # 7. Check metadata
        # ---------------------------------

        if not isinstance(metadata, dict):
            issues.append({
                "line": line_number,
                "issue": "Metadata is missing or not an object",
                "chunk": chunk
            })
        else:
            for field in ["page_start", "page_end"]:
                if field not in metadata:
                    issues.append({
                        "line": line_number,
                        "issue": f"Metadata missing {field}",
                        "chunk": chunk
                    })

            start = metadata.get("page_start")
            end = metadata.get("page_end")

            if isinstance(start, int) and isinstance(end, int):
                if start > end:
                    issues.append({
                        "line": line_number,
                        "issue": "page_start is greater than page_end",
                        "chunk": chunk
                    })

            if not metadata.get("source"):
                issues.append({
                    "line": line_number,
                    "issue": "Missing source metadata",
                    "chunk": chunk
                })

# ---------------------------------
# 8. Find duplicate IDs
# ---------------------------------

for chunk_id, count in chunk_ids.items():
    if count > 1:
        issues.append({
            "line": "-",
            "issue": f"Duplicate chunk_id {chunk_id}: {count} occurrences",
            "chunk": None
        })

# ---------------------------------
# 9. Find duplicate text
# ---------------------------------

duplicate_groups = {
    text: count
    for text, count in duplicate_texts.items()
    if count > 1
}

# ---------------------------------
# 10. Save flagged records
# ---------------------------------

with FLAGGED_FILE.open("w", encoding="utf-8") as file:
    for issue in issues:
        if issue["chunk"] is not None:
            file.write(json.dumps(issue, ensure_ascii=False) + "\n")

# ---------------------------------
# 11. Save summary report
# ---------------------------------

lengths = [
    len(chunk["text"])
    for chunk in valid_chunks
    if isinstance(chunk.get("text"), str)
]

with REPORT_FILE.open("w", encoding="utf-8") as report:
    report.write("CHUNK QUALITY REPORT\n")
    report.write("====================\n\n")

    report.write(f"Total JSONL lines: {total_lines}\n")
    report.write(f"Valid JSON objects: {len(valid_chunks)}\n")
    report.write(f"Total flagged issues: {len(issues)}\n")
    report.write(f"Unique duplicate text groups: {len(duplicate_groups)}\n")

    if lengths:
        report.write(f"Shortest chunk: {min(lengths)} chars\n")
        report.write(f"Longest chunk: {max(lengths)} chars\n")
        report.write(
            f"Average chunk length: {sum(lengths) / len(lengths):.1f} chars\n"
        )

    report.write("\nISSUES\n------\n")

    for issue in issues:
        report.write(
            f"Line {issue['line']}: {issue['issue']}\n"
        )

    report.write("\nDUPLICATE TEXT GROUPS\n---------------------\n")

    for text, count in duplicate_groups.items():
        report.write(f"{count} occurrences: {text[:200]}\n")

print("Validation complete!")
print(f"JSONL lines: {total_lines}")
print(f"Valid JSON objects: {len(valid_chunks)}")
print(f"Flagged issues: {len(issues)}")
print(f"Duplicate text groups: {len(duplicate_groups)}")
print(f"Report saved to: {REPORT_FILE.resolve()}")
print(f"Flagged records saved to: {FLAGGED_FILE.resolve()}")
