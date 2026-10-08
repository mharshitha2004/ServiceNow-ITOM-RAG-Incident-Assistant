import pymupdf
from pathlib import Path

PDF_PATH = Path("servicenow-australia-it-operations-management-enus.pdf")

OUTPUT_DIR = Path("sample_extraction")
OUTPUT_DIR.mkdir(exist_ok=True)

# PDF page numbers (human-readable, starting at 1)
START_PAGE = 756
END_PAGE = 759

output_file = OUTPUT_DIR / "discovery_pages_756_759.txt"

if not PDF_PATH.exists():
    raise FileNotFoundError(
        f"PDF not found: {PDF_PATH.resolve()}\n"
        "Make sure the PDF is in the same folder as this script."
    )

with pymupdf.open(PDF_PATH) as pdf:
    total_pages = len(pdf)

    print(f"Total pages in PDF: {total_pages}")

    if START_PAGE < 1 or END_PAGE > total_pages:
        raise ValueError("Requested page range is outside the PDF.")

    extracted_pages = []

    for page_num in range(START_PAGE, END_PAGE + 1):
        # PyMuPDF uses zero-based page indexes
        page = pdf[page_num - 1]
        text = page.get_text("text", sort=True)

        extracted_pages.append(
            f"\n\n===== PDF PAGE {page_num} =====\n\n{text}"
        )

        print(
            f"Page {page_num}: "
            f"{len(text)} characters extracted"
        )

    full_text = "\n".join(extracted_pages)

    output_file.write_text(
        full_text,
        encoding="utf-8"
    )

    print("\nExtraction complete!")
    print(f"Saved to: {output_file.resolve()}")
    print(f"Total extracted characters: {len(full_text)}")

    print("\n--- Preview ---")
    print(full_text[:3000])