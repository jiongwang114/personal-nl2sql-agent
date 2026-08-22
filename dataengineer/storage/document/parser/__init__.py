
"""
Document Parser Module

Provides parsers for different document formats:
- Markdown (using markdown-it-py)
- HTML (using BeautifulSoup4)
"""

from dataengineer.storage.document.parser.html_parser import HTMLParser
from dataengineer.storage.document.parser.markdown_parser import MarkdownParser
from dataengineer.storage.document.parser.metadata_extractor import MetadataExtractor

__all__ = [
    "MarkdownParser",
    "HTMLParser",
    "MetadataExtractor",
]
