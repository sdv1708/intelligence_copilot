"""Document handling with smart chunking and direct LLM upload options."""

from typing import List, Dict, Any, Tuple
import sqlite3
from core.chunk import chunk_text
from core.embed import encode, search_index, build_or_load_index, save_index
from core.utils import get_env, log_message, get_storage_path


# Token estimation: ~4 characters per token (rough estimate)
# Most LLMs have 100k+ token context windows
# Reserve 20k tokens for prompts/system messages
MAX_DIRECT_TOKENS = 80000  # ~320k characters
MAX_DIRECT_CHARS = 320000


def should_send_directly(text: str) -> bool:
    """
    Determine if document should be sent directly to LLM without chunking.
    
    Args:
        text: Document text
        
    Returns:
        True if document is small enough to send directly
    """
    char_count = len(text)
    return char_count <= MAX_DIRECT_CHARS


def get_improved_chunks(text: str, max_len: int = 4000, overlap: int = 800) -> List[str]:
    """
    Improved chunking with larger chunks and more overlap to preserve relationships.
    
    Args:
        text: Input text
        max_len: Maximum characters per chunk (increased from 1200)
        overlap: Overlap between chunks (increased from 120)
        
    Returns:
        List of text chunks
    """
    chunks = []
    i = 0
    n = len(text)
    
    while i < n:
        # Calculate the end position
        end = min(n, i + max_len)
        
        # Try to find a paragraph boundary (double newline) first
        cut = text.rfind("\n\n", i, end)
        
        # If no paragraph boundary, try sentence boundary
        if cut == -1:
            cut = text.rfind(". ", i, end)
        
        # If no sentence boundary found or too short, use the max_len endpoint
        if cut == -1 or cut < i + int(max_len * 0.5):
            cut = end
        
        # Extract the chunk
        chunk = text[i:cut].strip()
        
        if chunk:  # Only add non-empty chunks
            chunks.append(chunk)
        
        # Move to next position with overlap
        i = max(cut - overlap, i + 1)
    
    log_message("INFO", f"Created {len(chunks)} improved chunks from {n} characters (max_len={max_len}, overlap={overlap})")
    return chunks


def recall_with_context(
    db_conn: sqlite3.Connection, 
    meeting_id: str, 
    query: str = "", 
    k: int = 8,
    include_surrounding: bool = True
) -> List[Dict[str, Any]]:
    """
    Retrieve context with surrounding chunks to preserve relationships.
    
    Args:
        db_conn: Database connection
        meeting_id: Meeting ID
        query: Search query
        k: Number of results
        include_surrounding: Include surrounding chunks for context
        
    Returns:
        List of chunks with metadata
    """
    # Fetch all materials
    cursor = db_conn.cursor()
    cursor.execute("SELECT id, text FROM materials WHERE meeting_id = ?", (meeting_id,))
    rows = cursor.fetchall()
    
    if not rows:
        log_message("WARNING", f"No materials found for meeting {meeting_id}")
        return []
    
    # Check if any material is small enough to send directly
    all_texts = []
    material_map = {}
    for material_id, text in rows:
        all_texts.append(text)
        material_map[material_id] = text
    
    # If total text is small, return full documents
    total_chars = sum(len(text) for text in all_texts)
    if total_chars <= MAX_DIRECT_CHARS:
        log_message("INFO", f"Document small enough ({total_chars} chars), returning full text")
        results = []
        for material_id, text in rows:
            results.append({
                "text": text,
                "material_id": material_id,
                "chunk_idx": 0,
                "score": 1.0,
                "is_full_document": True
            })
        return results[:k]
    
    # Use improved chunking for larger documents
    all_chunks = []
    chunk_metadata = []
    
    for material_id, text in rows:
        # Use improved chunking with larger chunks
        chunks = get_improved_chunks(text, max_len=4000, overlap=800)
        
        for chunk_idx, chunk in enumerate(chunks):
            all_chunks.append(chunk)
            chunk_metadata.append({
                "material_id": material_id,
                "chunk_idx": chunk_idx,
                "text": chunk,
                "total_chunks": len(chunks)
            })
    
    if not all_chunks:
        return []
    
    # Encode query
    if query:
        query_emb = encode([query])
    else:
        query_emb = encode([" ".join(all_chunks[:5])])
    
    # Load or create FAISS index
    faiss_path = get_env("FAISS_PATH", get_storage_path("faiss"))
    index_path = f"{faiss_path}/{meeting_id}.index"
    
    try:
        index = build_or_load_index(index_path)
        
        if index.ntotal == 0:
            chunk_embeddings = encode(all_chunks)
            index.add(chunk_embeddings)
            save_index(index, index_path)
        
        # Search
        search_k = min(k * 2, index.ntotal) if index.ntotal > 0 else k
        distances, indices = search_index(index, query_emb, k=search_k)
        
        # Build results with surrounding chunks
        results = []
        seen_indices = set()
        
        if len(indices[0]) > 0:
            for i, idx in enumerate(indices[0]):
                if idx == -1 or idx >= len(chunk_metadata):
                    continue
                
                score = float(distances[0][i])
                min_threshold = 0.05 if query else 0.15
                if score < min_threshold:
                    continue
                
                metadata = chunk_metadata[idx]
                material_id = metadata["material_id"]
                chunk_idx = metadata["chunk_idx"]
                total_chunks = metadata["total_chunks"]
                
                # Add main chunk
                if idx not in seen_indices:
                    results.append({
                        "text": metadata["text"],
                        "material_id": material_id,
                        "chunk_idx": chunk_idx,
                        "score": score,
                        "is_full_document": False
                    })
                    seen_indices.add(idx)
                
                # Add surrounding chunks if requested
                if include_surrounding:
                    # Add previous chunk
                    if chunk_idx > 0:
                        prev_idx = idx - 1
                        if prev_idx >= 0 and prev_idx < len(chunk_metadata):
                            prev_meta = chunk_metadata[prev_idx]
                            if prev_meta["material_id"] == material_id and prev_idx not in seen_indices:
                                results.append({
                                    "text": prev_meta["text"],
                                    "material_id": material_id,
                                    "chunk_idx": prev_meta["chunk_idx"],
                                    "score": score * 0.9,  # Slightly lower score
                                    "is_full_document": False,
                                    "is_surrounding": True
                                })
                                seen_indices.add(prev_idx)
                    
                    # Add next chunk
                    if chunk_idx < total_chunks - 1:
                        next_idx = idx + 1
                        if next_idx < len(chunk_metadata):
                            next_meta = chunk_metadata[next_idx]
                            if next_meta["material_id"] == material_id and next_idx not in seen_indices:
                                results.append({
                                    "text": next_meta["text"],
                                    "material_id": material_id,
                                    "chunk_idx": next_meta["chunk_idx"],
                                    "score": score * 0.9,
                                    "is_full_document": False,
                                    "is_surrounding": True
                                })
                                seen_indices.add(next_idx)
                
                if len(results) >= k * 3:  # Allow more results when including surrounding
                    break
        
        # Sort by score and return top k
        results.sort(key=lambda x: x["score"], reverse=True)
        log_message("INFO", f"Recalled {len(results)} chunks (including surrounding) for meeting {meeting_id}")
        return results[:k]
    
    except Exception as e:
        log_message("ERROR", f"Error during recall with context: {str(e)}")
        return []


def format_context_with_relationships(results: List[Dict[str, Any]]) -> str:
    """
    Format retrieved chunks preserving relationships and context.
    
    Args:
        results: List of retrieved chunks
        
    Returns:
        Formatted context string
    """
    if not results:
        return "No context retrieved."
    
    blocks = []
    current_material = None
    
    for i, result in enumerate(results, 1):
        material_id = result['material_id']
        chunk_idx = result['chunk_idx']
        text = result['text']
        score = result['score']
        is_full = result.get('is_full_document', False)
        is_surrounding = result.get('is_surrounding', False)
        
        # Group by material
        if current_material != material_id:
            if current_material is not None:
                blocks.append("")  # Add spacing between materials
            current_material = material_id
            blocks.append(f"=== Material: {material_id} ===")
        
        # Format chunk
        if is_full:
            source = f"{material_id} (FULL DOCUMENT)"
            blocks.append(f"[{i}] {source}\n{text}\n---")
        elif is_surrounding:
            source = f"{material_id}#c{chunk_idx} (CONTEXT)"
            blocks.append(f"[{i}] {source}\nScore: {score:.3f}\n{text}\n---")
        else:
            source = f"{material_id}#c{chunk_idx}"
            blocks.append(f"[{i}] {source}\nScore: {score:.3f}\n{text}\n---")
    
    return "\n".join(blocks)

