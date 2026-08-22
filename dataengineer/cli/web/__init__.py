
"""
Web interface for DataEngineer Agent.

Serves a React-based chatbot frontend backed by FastAPI.
"""

from dataengineer.cli.web.chatbot import create_web_app, run_web_interface

__all__ = [
    "create_web_app",
    "run_web_interface",
]
