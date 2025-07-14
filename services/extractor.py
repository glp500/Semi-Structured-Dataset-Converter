"""
PDF table extraction utilities using PyMuPDF.
"""
import fitz  # PyMuPDF

__all__ = ["extract_tables_from_pdf"]

def extract_tables_from_pdf(pdf_bytes: bytes, method: str = "auto") -> list[str]:
    """
    Extract table data (and other text as fallback) from a PDF file.
    
    Uses PyMuPDF's table detection to retrieve structured table content.
    If tables are detected, returns the text content of each table.
    If no tables are found on a page, falls back to raw text extraction for that page.
    
    :param pdf_bytes: The PDF file content as bytes.
    :param method: Table detection method: 
                   "auto" (auto-detect, tries line-based then text-based), 
                   "lattice" (line-based detection only), 
                   "matrix" (text-based detection only).
    :return: A list of strings, where each string corresponds to the content of one PDF page.
    """
    pages_content: list[str] = []
    # Open PDF from bytes
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        for page in doc:
            page_text = ""
            tables = None
            # Choose detection strategy based on method
            if method == "auto":
                table_finder = page.find_tables()
                tables = [tbl for tbl in table_finder] if table_finder else []
                if not tables:
                    # If no tables with default, try text-based detection
                    table_finder = page.find_tables(strategy="text")
                    tables = [tbl for tbl in table_finder] if table_finder else []
            elif method == "lattice":
                table_finder = page.find_tables(strategy="lines")
                tables = [tbl for tbl in table_finder] if table_finder else []
            elif method == "matrix":
                table_finder = page.find_tables(strategy="text")
                tables = [tbl for tbl in table_finder] if table_finder else []
            else:
                # Unknown method, default to auto
                table_finder = page.find_tables()
                tables = [tbl for tbl in table_finder] if table_finder else []
            if tables and len(tables) > 0:
                # Extract all tables on the page
                table_texts = []
                for t in tables:
                    try:
                        data = t.extract()  # list of list of strings
                    except AttributeError:
                        data = []
                        # Could implement manual extraction via cell bounding boxes if needed.
                    if data:
                        for row in data:
                            line = ", ".join(str(cell) for cell in row)
                            table_texts.append(line)
                        table_texts.append("")
                page_text = "\n".join(table_texts).strip()
            else:
                # No table found, fallback to entire page text
                page_text = page.get_text().strip()
            pages_content.append(page_text if page_text is not None else "")
    finally:
        doc.close()
    return pages_content