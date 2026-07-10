"""Compatibility import for the split FastAPI application."""

from ultrafast_memory.apps.api.main import app, create_app

__all__ = ["app", "create_app"]
