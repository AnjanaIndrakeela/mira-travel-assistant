# Mira – AI Travel Booking Assistant

Conversational booking assistant for **Ceylon Compass Holidays** (fictional Sri Lankan tour operator).

> Work in progress. Full documentation (architecture, design decisions, evaluation, limitations, AI tools used) will be added before submission.

## Prerequisites

- Docker Desktop (engine running)
- Node.js 20+ and npm
- The supplied dataset folder `ceylon-compass-dataset` next to this repo (or set `MIRA_DATASET_HOST_DIR`). It is mounted **read-only**; the app never modifies it.

## Setup

```bash
cp .env.example .env        # then fill in GEMINI_API_KEY and the LANGFUSE_* keys
docker compose up -d --build   # PostgreSQL (host port 5433) + backend (http://localhost:8000)
cd frontend && npm install && npm run dev   # http://localhost:3000
```

Health check: <http://localhost:8000/api/v1/health>

## Tests

```bash
docker compose exec backend python -m pytest -q
```

## Why the backend runs in Docker

The backend dependencies are installed with **pip** inside a Linux container (`backend/Dockerfile`). This keeps native packages (FAISS, SQLAlchemy, psycopg, LangGraph's serialisers) working the same on every machine, including Windows machines where Smart App Control blocks unsigned Python extension DLLs.
