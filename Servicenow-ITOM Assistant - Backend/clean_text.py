from pathlib import Path
import re

INPUT_DIR = Path("sample_extraction")

for page_num in [757, 758]:
    file_path = INPUT_DIR / f"page_{page_num}.txt"
    text = file_path.read_text(encoding="utf-8")

    # Remove repeated copyright/footer lines
    lines = []
    for line in text.splitlines():
        if "©" in line or "Other company names" in line:
            continue
        if "trademarks" in line.lower():
            continue
        lines.append(line)

    # Remove excessive blank lines
    text = "\n".join(lines)
    text = re.sub(r"\n\s*\n+", "\n\n", text)

    # Remove leading/trailing whitespace
    text = text.strip()

    output_file = INPUT_DIR / f"clean_page_{page_num}.txt"
    output_file.write_text(text, encoding="utf-8")

    print(f"Saved: {output_file}")
    print(text[:500])
    print("-" * 50)
