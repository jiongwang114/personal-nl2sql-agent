
"""
Document Chunker Module

Provides chunking strategies for splitting documents into retrievable chunks:
- SemanticChunker: Smart chunking based on document structure
"""

from dataengineer.storage.document.chunker.semantic_chunker import SemanticChunker

__all__ = [
    "SemanticChunker",
]
