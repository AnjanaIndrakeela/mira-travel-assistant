"""Vercel entry point: the whole FastAPI app as one Python function (vercel.json sends every
path here). Locally and in Docker the app runs with uvicorn instead."""

from app.main import app  # noqa: F401
