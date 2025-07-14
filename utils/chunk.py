"""
Utility functions for text chunking.
"""
__all__ = ["chunk_text"]

def chunk_text(text: str, max_chars: int = 12000) -> list[str]:
    """
    Split a long text into chunks such that each chunk's length does not exceed max_chars.
    Tries to split at newline or whitespace boundaries for cleaner chunks.
    """
    chunks: list[str] = []
    current_pos = 0
    length = len(text)
    while current_pos < length:
        end_pos = current_pos + max_chars
        if end_pos >= length:
            chunk = text[current_pos:].strip()
            if chunk:
                chunks.append(chunk)
            break
        split_idx = text.rfind("\n", current_pos, end_pos)
        if split_idx == -1 or split_idx < current_pos:
            split_idx = text.rfind(" ", current_pos, end_pos)
        if split_idx == -1 or split_idx < current_pos:
            split_idx = end_pos - 1
        if split_idx < current_pos:
            split_idx = end_pos - 1
            if split_idx < current_pos:
                split_idx = length - 1
        chunk = text[current_pos: split_idx + 1].strip()
        if chunk:
            chunks.append(chunk)
        current_pos = split_idx + 1
    return [c for c in chunks if c]