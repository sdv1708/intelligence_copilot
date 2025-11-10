"""Recall and retrieval logic for fetching relevant context."""

from typing import List, Dict, Any, Optional
import sqlite3
from core.embed import encode, search_index, build_or_load_index
from core.utils import get_env, log_message


def recall_context(db_conn: sqlite3.Connection, meeting_id: str, 
                   query: str = "", k: int = 8) -> List[Dict[str, Any]]:
    """
    Retrieve top-k relevant context for a meeting.
    
    Args:
        db_conn: SQLite database connection
        meeting_id: ID of the meeting
        query: Optional search query (if empty, use all material from meeting)
        k: Number of results to return
    
    Returns:
        List of dicts with keys: {text, material_id, chunk_idx, score}
    """
    
    # Fetch all materials for this meeting
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT id, text FROM materials WHERE meeting_id = ?
    """, (meeting_id,))
    rows = cursor.fetchall()
    
    if not rows:
        log_message("WARNING", f"No materials found for meeting {meeting_id}")
        return []
    
    # For MVP: chunk all materials and keep in memory
    # TODO: In production, store chunk metadata in DB for efficient retrieval
    all_chunks = []
    chunk_metadata = []
    
    for material_id, text in rows:
        # Import here to avoid circular dependency
        from core.chunk import chunk_text
        chunks = chunk_text(text)
        
        for chunk_idx, chunk in enumerate(chunks):
            all_chunks.append(chunk)
            chunk_metadata.append({
                "material_id": material_id,
                "chunk_idx": chunk_idx,
                "text": chunk
            })
    
    if not all_chunks:
        log_message("WARNING", f"No chunks created from materials for meeting {meeting_id}")
        return []
    
    # Encode query or use all chunks
    if query:
        query_emb = encode([query])
    else:
        # Use average of all chunks as query (fallback)
        query_emb = encode([" ".join(all_chunks[:5])])  # Use first 5 chunks as representative
    
    # Load or create FAISS index for this meeting
    from core.utils import get_storage_path
    faiss_path = get_env("FAISS_PATH", get_storage_path("faiss"))
    index_path = f"{faiss_path}/{meeting_id}.index"
    
    try:
        index = build_or_load_index(index_path)
        
        # If index is empty, add all chunks
        if index.ntotal == 0:
            chunk_embeddings = encode(all_chunks)
            index.add(chunk_embeddings)
            from core.embed import save_index
            save_index(index, index_path)
        
        # Search
        distances, indices = search_index(index, query_emb, k=k)
        
        # Build result list
        results = []
        if len(indices[0]) > 0:
            for i, idx in enumerate(indices[0]):
                if idx == -1:  # Invalid index
                    continue
                score = float(distances[0][i])
                metadata = chunk_metadata[idx]
                results.append({
                    "text": metadata["text"],
                    "material_id": metadata["material_id"],
                    "chunk_idx": metadata["chunk_idx"],
                    "score": score
                })
        
        log_message("INFO", f"Recalled {len(results)} chunks for meeting {meeting_id}")
        return results
    
    except Exception as e:
        log_message("ERROR", f"Error during recall: {str(e)}")
        return []


def format_context_blocks(results: List[Dict[str, Any]]) -> str:
    """
    Format retrieved chunks into context blocks for the LLM prompt.
    
    Args:
        results: List of retrieved chunks from recall_context
    
    Returns:
        Formatted string for inclusion in prompt
    """
    if not results:
        return "No context retrieved."
    
    blocks = []
    for i, result in enumerate(results, 1):
        source = f"{result['material_id']}#c{result['chunk_idx']}"
        snippet = result['text'][:500]  # Truncate for display
        block = f"[{i}] Source: {source}\nScore: {result['score']:.3f}\n{snippet}\n---"
        blocks.append(block)
    
    return "\n".join(blocks)

