"""
Few-shot example loader for JSON output examples.
Scans the package directory for example JSON and corresponding PDFs.
"""
from pathlib import Path
from typing import List, Tuple

def load_examples(max_examples: int = None) -> List[Tuple[str, str]]:
    """
    Load example PDF/JSON pairs from the examples directory.
    Expects JSON files and matching PDF files with the same base name.
    
    :param max_examples: If given, limit the number of examples returned.
    :return: List of (example_pdf_text, example_json_text) tuples.
    """
    examples_dir = Path(__file__).parent
    example_pairs: List[Tuple[str, str]] = []
    json_files = sorted(examples_dir.glob("*.json"))
    for json_file in json_files:
        if max_examples is not None and len(example_pairs) >= max_examples:
            break
        try:
            example_json_text = json_file.read_text(encoding="utf-8")
        except Exception:
            continue
        pdf_file = json_file.with_suffix(".pdf")
        if not pdf_file.exists():
            continue
        example_pdf_text = ""
        try:
            import fitz
            with fitz.open(stream=pdf_file.read_bytes(), filetype="pdf") as doc:
                example_pdf_text = "\n".join(page.get_text() for page in doc)
        except Exception:
            example_pdf_text = ""
        if example_pdf_text.strip() and example_json_text.strip():
            example_pairs.append((example_pdf_text, example_json_text))
    return example_pairs