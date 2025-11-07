"""Embedding and FAISS index management."""

from typing import List, Optional
import numpy as np
import os
from core.utils import get_env, log_message

# Lazy-load the model
_model = None


def get_model():
    """Get or load the SentenceTransformer model."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        log_message("INFO", "Loading SentenceTransformer model (all-MiniLM-L6-v2)...")
        _model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _model


def build_or_load_index(path: str, dim: int = 384):
    """
    Create or load a FAISS index.
    
    Args:
        path: Path to save/load the FAISS index
        dim: Embedding dimension (384 for MiniLM)
    
    Returns:
        FAISS index object
    """
    try:
        import faiss
    except ImportError:
        log_message("ERROR", "FAISS not installed. Run: pip install faiss-cpu")
        raise
    
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    
    if os.path.exists(path):
        log_message("INFO", f"Loading FAISS index from {path}")
        return faiss.read_index(path)
    else:
        log_message("INFO", f"Creating new FAISS index at {path}")
        # IndexFlatIP = Inner Product (cosine similarity on normalized vectors)
        index = faiss.IndexFlatIP(dim)
        faiss.write_index(index, path)
        return index


def save_index(index, path: str):
    """Save FAISS index to disk."""
    try:
        import faiss
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        faiss.write_index(index, path)
        log_message("INFO", f"Saved FAISS index to {path}")
    except Exception as e:
        log_message("ERROR", f"Failed to save FAISS index: {str(e)}")


def encode(chunks: List[str]) -> np.ndarray:
    """
    Encode a list of text chunks into embeddings.
    
    Args:
        chunks: List of text strings
    
    Returns:
        Normalized embeddings as float32 numpy array (shape: [len(chunks), 384])
    """
    if not chunks:
        return np.array([], dtype="float32").reshape(0, 384)
    
    model = get_model()
    log_message("INFO", f"Encoding {len(chunks)} chunks...")
    embeddings = model.encode(chunks, normalize_embeddings=True)
    result = np.array(embeddings).astype("float32")
    log_message("INFO", f"Encoded shape: {result.shape}")
    return result


def add_to_index(index, embeddings: np.ndarray) -> int:
    """
    Add embeddings to FAISS index.
    
    Args:
        index: FAISS index
        embeddings: Embeddings to add (shape: [n, 384])
    
    Returns:
        Number of embeddings added
    """
    if len(embeddings) == 0:
        return 0
    
    index.add(embeddings)
    log_message("INFO", f"Added {len(embeddings)} embeddings to index. Total: {index.ntotal}")
    return len(embeddings)


def search_index(index, query_embedding: np.ndarray, k: int = 8) -> tuple[np.ndarray, np.ndarray]:
    """
    Search FAISS index for top-k similar items.
    
    Args:
        index: FAISS index
        query_embedding: Query embedding (shape: [1, 384])
        k: Number of results to return
    
    Returns:
        (distances, indices) - shape [1, k] each
    """
    if index.ntotal == 0:
        log_message("WARNING", "FAISS index is empty")
        return np.array([]), np.array([])
    
    k = min(k, index.ntotal)
    distances, indices = index.search(query_embedding, k)
    log_message("INFO", f"Search returned top-{k} results (distances: {distances[0]})")
    return distances, indices

