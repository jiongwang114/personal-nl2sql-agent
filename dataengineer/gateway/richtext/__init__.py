
"""Markdown IR layer: Markdown -> IR -> platform-specific rich text."""

from dataengineer.gateway.richtext.chunker import chunk_text
from dataengineer.gateway.richtext.escape import slack_escape
from dataengineer.gateway.richtext.ir import MarkdownIR
from dataengineer.gateway.richtext.parser import markdown_to_ir
from dataengineer.gateway.richtext.render import render_ir

__all__ = ["MarkdownIR", "chunk_text", "markdown_to_ir", "render_ir", "slack_escape"]
