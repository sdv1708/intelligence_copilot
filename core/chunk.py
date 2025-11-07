"""Text chunking utility for preparing documents for embedding."""

from typing import List
from core.utils import log_message


def chunk_text(txt: str, max_len: int = 1200, overlap: int = 120) -> List[str]:
    """
    Split text into overlapping chunks.
    Attempts to split on sentence boundaries for better semantic coherence.
    
    Args:
        txt: Input text to chunk
        max_len: Maximum characters per chunk
        overlap: Overlap between chunks in characters
    
    Returns:
        List of text chunks
    """
    chunks = []
    i = 0
    n = len(txt)
    
    while i < n:
        # Calculate the end position
        end = min(n, i + max_len)
        
        # Try to find a sentence boundary (period followed by space)
        cut = txt.rfind(". ", i, end)
        
        # If no sentence boundary found or too short, use the max_len endpoint
        if cut == -1 or cut < i + int(max_len * 0.6):
            cut = end
        
        # Extract the chunk
        chunk = txt[i:cut].strip()
        
        if chunk:  # Only add non-empty chunks
            chunks.append(chunk)
        
        # Move to next position with overlap
        i = max(cut - overlap, i + 1)
    
    log_message("INFO", f"Created {len(chunks)} chunks from {n} characters (max_len={max_len}, overlap={overlap})")
    return chunks

