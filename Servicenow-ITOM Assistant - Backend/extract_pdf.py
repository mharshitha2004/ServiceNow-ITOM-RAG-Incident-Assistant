import pymupdf
import json
from pathlib import Path

# Change this to the exact name of your original PDF
PDF_PATH = Path("servicenow-australia-it-operations-management-enus.pdf")

OUTPUT_PATH = Path("extracted_pages.jsonl")

if not PDF_PATH.exists():
    raise FileNotFoundError(
        f"PDF not found: {PDF_PATH.resolve()}\n"
        "Place the PDF in this folder or update PDF_PATH."
    )

with pymupdf.open(PDF_PATH) as pdf, \
     OUTPUT_PATH.open("w", encoding="utf-8") as output:

    total_pages = len(pdf)

    for page_index, page in enumerate(pdf):
        text = page.get_text("text").strip()

        record = {
            "page_number": page_index + 1,
            "text": text
        }

        output.write(
            json.dumps(record, ensure_ascii=False) + "\n"
        )

        if (page_index + 1) % 100 == 0:
            print(f"Processed {page_index + 1}/{total_pages} pages")

print(f"\nExtraction complete!")
print(f"Total pages: {total_pages}")
print(f"Saved to: {OUTPUT_PATH.resolve()}")