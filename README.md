# Mira – AI Travel Booking Assistant

Conversational booking assistant for **Ceylon Compass Holidays**, a fictional Sri Lankan tour operator.

> Work in progress. Architecture, design decisions, evaluation, known limitations and AI tools used are documented before submission.

## Prerequisites

| Tool | Version | Used for |
|---|---|---|
| Docker Desktop (engine running) | 24+ | PostgreSQL and the Python backend |
| Node.js and npm | Node 20+ | The Next.js frontend |
| Git | any | |

You also need the supplied dataset folder `ceylon-compass-dataset` **next to this repo** (`../ceylon-compass-dataset`). To keep it elsewhere, set `MIRA_DATASET_HOST_DIR` to its path. It is mounted **read-only**; the app never changes it.

You don't need Python on your machine: the backend runs in Docker.

## Setup

**1. Environment file.** Copy the example, then open `.env` and fill in `GEMINI_API_KEY` (from Google AI Studio). The Langfuse keys are optional. `.env` is git-ignored; never commit it.

```powershell
Copy-Item .env.example .env
```

(macOS/Linux: `cp .env.example .env`)

**2. Database and backend.** This starts PostgreSQL on host port **5433** and the API on <http://localhost:8000>, with live reload.

```powershell
docker compose up -d --build
```

After editing `.env`, restart the backend so it reads the new values: `docker compose up -d backend`.

**3. Frontend.** This starts on <http://localhost:3010> (a fixed port, so it never clashes with other apps on 3000). The backend allows this origin through `FRONTEND_ORIGIN`; if you change the port, change both. The API address can be set with `NEXT_PUBLIC_API_URL` (default `http://localhost:8000/api/v1`).

```powershell
cd frontend
npm install
npm run dev
```

## Check that it works

Open <http://localhost:8000/api/v1/health>. The API docs are at <http://localhost:8000/docs>.

| Field | Expected | Meaning |
|---|---|---|
| `status` | `ok` | The API is up |
| `today` | `2026-11-19` | The date used for quoting (`MIRA_TODAY`, configurable) |
| `dataset_found` | `true` | The dataset folder is mounted |
| `database` | `ok` | PostgreSQL answers |
| `tracing` | `enabled` / `disabled` | Langfuse keys set or not (optional) |
| `llm_configured` | `true` | `GEMINI_API_KEY` is set |

## Tests

```powershell
docker compose exec backend python -m pytest
```

Tests that call the Gemini chat model are marked `live` and skipped by default. Run them by hand (needs `GEMINI_API_KEY`):

```powershell
docker compose exec backend python -m pytest -m live
```

## Project layout

```
backend/            FastAPI app (Python 3.12, pip), runs in Docker
  app/main.py       entry point: app, CORS, routers
  app/api/          HTTP routes (/api/v1/...)
  app/core/         settings (all configuration comes from env / .env)
  app/data_loader/  reads the dataset (read-only) and logs its data issues
  app/pricing/      deterministic pricing engine: calculate_quote(), CLI python -m app.pricing
  app/db/           tables, sessions, seed, repo (only what Mira creates is stored)
  app/rag/          content retrieval: chunker, Gemini embeddings, FAISS + BM25, retriever
  app/llm/          Gemini client, structured output, router and extraction tasks
  app/guards/       input and output guards (injection, personal data, invented prices)
  app/graph/        LangGraph workflow: state, nodes, tours, prompts, tracing, CLI
  var/index/        saved FAISS index and query-vector cache (git-ignored, rebuilt on change)
  media/ella/       our own Ella illustrations (the dataset has no photos)
  tests/            unit/, api/, db/, rag/ and live/ tests (db/ needs the db container; rag/ needs GEMINI_API_KEY)
evaluation/         eval cases (custom.jsonl); the runner comes later
frontend/           Next.js 15 + TypeScript + Tailwind v4 (chat UI on port 3010)
  scripts/sync-brand.mjs  brand tokens generated from the dataset's brand_pack.json (npm run brand)
  scripts/check-catalog.mjs  checks the Zod catalog against the backend's JSON Schema (npm run check:catalog)
  src/lib/          brand.ts (generated), api.ts (backend client), catalog-schema.ts (Zod),
                    catalog.schema.json (exported by the backend)
  src/components/   Header, chat/ (Chat, Messages, Composer), catalog/ (the generative UI components)
docker-compose.yml  db (PostgreSQL 16) + backend
.env.example        every setting, with placeholders only
```

## Configuration

All settings are environment variables; see `.env.example` for the full list. The important ones:

- `MIRA_TODAY`: "today" for quotes and date checks. Defaults to `2026-11-19`, the date the evaluation cases assume.
- `GEMINI_MODEL_FAST` / `GEMINI_MODEL_STRONG`: chat models. The defaults are `gemini-3.1-flash-lite` / `gemini-3.5-flash`, because Gemini 2.5 models are no longer available to new API keys.
- `GEMINI_MODEL_BACKUP`: tried last when both are overloaded (503) or out of quota (429); default `gemini-3.5-flash-lite`. Each Gemini call retries with backoff (1 s, 2 s), then switches model. With every model down, Mira still replies with fixed wording or a handoff.
- `MIRA_MARGIN_DAY` / `MIRA_MARGIN_MULTIDAY`: optional margin overrides. If they're empty, the rate workbook's values are used.
- `MIRA_STAFF_EMAIL` / `MIRA_STAFF_PASSWORD` and `MIRA_APPROVER_EMAIL` / `MIRA_APPROVER_PASSWORD`: the two demo staff accounts. They're created at startup (or with `python -m app.db.seed`) only if a password is set, stored hashed, and never overwritten afterwards.

## Database

Tables are created at startup if missing (8 tables: visitors, conversations, quotes, enquiries, bookings, users, content_items, media), and the demo users and media are seeded. Both steps are safe to repeat. Tours, content and rates are never stored in the database: they're read from the dataset.

## API

All routes are under `/api/v1`; try them at <http://localhost:8000/docs>.

| Route | What it does |
|---|---|
| `POST /chat` | One traveller turn: `{message, conversation_id?, visitor_id?}` → reply, UI components, sources, `quote_id`. Send the `conversation_id` back to continue. |
| `POST /chat/stream` | The same turn as an AG-UI-style event stream (Server-Sent Events), used by the chat UI |
| `GET /conversations/{id}` | The messages so far |
| `GET /quotes/{id}` | A saved quote, public fields only (never cost or margin) |
| `POST /quotes` | A direct quote from a form, through the same pricing engine |
| `POST /enquiries` | "Send to the team" with optional contact details |
| `GET /tours/{id}` | A published tour (drafts are 404); prices in the text are masked |
| `POST /bookings` | Mock booking: re-checks the price, then charges the deposit with the mock provider |
| `GET /health` | Status of the dataset, database, index, tracing and LLM |

Every quote is saved with its public and staff fields and the Langfuse `trace_id`, plus a private enquiry for staff (`no_price` with reason flags when a specialist must confirm).

**Mock payments.** The card `4242 4242 4242 4242` succeeds and `4000 0000 0000 0002` is declined. `MOCK_PAYMENT_FAIL=1` makes every charge fail. A failure returns a friendly message with next steps and saves a `booking_failed` enquiry. Card numbers are never stored or logged.

**Errors** always look like `{"error": "not_found", "message": "..."}`, with no stack traces. Logs mask emails, phone numbers and card numbers.

## Conversation graph

Each chat turn runs through a LangGraph `StateGraph` (`backend/app/graph/`). Gemini only classifies (guard), extracts trip details (discovery) and words the reply (respond). Code decides the route, prices with the pricing engine, picks tours and checks every reply with the output guard. Conversation state is kept per thread by a checkpointer.

```mermaid
graph TD;
	__start__([start]) --> guard;
	guard -.-> discovery;
	guard -.->|injection, off-topic, greeting, handoff| route;
	discovery --> route;
	route -.->|ask, greet, decline| respond;
	route -.-> price;
	route -.-> match_tours;
	route -.-> retrieve;
	price -.-> respond;
	price -.->|"tell me about it too"| retrieve;
	match_tours --> respond;
	retrieve --> respond;
	respond --> persist;
	persist --> build_ui;
	build_ui --> __end__([end]);
```

(Generated with `python -m app.graph.build`, labels added.)

Chat in the terminal:

```powershell
docker compose exec backend python -m app.graph.cli --debug
```

Scripted turns: `python -m app.graph.cli --say "Hi" --say "2 adults from 3 May 2027"`.

**Tracing.** With the Langfuse keys set, each turn is one trace, grouped by conversation as a session. It holds a span for every node and every Gemini call, plus the prompt version. Emails, phone numbers and card-like numbers are masked before anything is sent to Langfuse, and before the model sees the message. If Langfuse is unreachable or a key is wrong, chat keeps working without traces.

## Generative UI

Mira's replies can carry UI components, but only from a fixed catalog of eight: `traveller_picker`, `tour_card`, `itinerary_day`, `price_breakdown`, `booking_form`, `specialist_notice`, `source_list` and `welcome_back` (`backend/app/ui/catalog.py`).

- **Code chooses, not the LLM.** The `build_ui` node picks components from the verified state (`app/ui/build.py`): a saved quote gives a tour card, a price card and a booking form; a refusal or an unanswered question gives a specialist notice; suggested tours give tour cards plus the top tour's day-by-day plan; a question about who is travelling gives the traveller picker.
- **Prices never travel in a component.** `price_breakdown` and `booking_form` carry only a `quote_id`. The browser fetches the verified public quote from `GET /quotes/{id}`.
- **Validated twice.** The server checks every payload against a Pydantic discriminated union with `extra="forbid"` (`app/guards/ui_validator.py`). It drops unknown types, bad or extra props, markup or script in text, money amounts in text, and price components that don't point at this turn's saved quote. Drops are logged and recorded in the trace (`ui_rejected`). The browser checks again with Zod (`frontend/src/lib/catalog-schema.ts`), and the registry renders only known types. Each component has an error boundary.
- **One contract.** `python -m app.ui.export` writes the catalog's JSON Schema to `frontend/src/lib/catalog.schema.json`. A backend test fails if that file is stale, and `npm run check:catalog` fails if the Zod schemas drift from it.
- **Booking and enquiry forms** post straight to `/bookings` and `/enquiries`. Contact details and card numbers never pass through the chat, the LLM or the traces.

**Screenshots** (`docs/screenshots/`, taken at 1280 px and 375 px):

| | Desktop (1280 px) | Phone (375 px) |
|---|---|---|
| Instant quote: tour card, price card (fetched by quote ID), booking form | ![Quote, desktop](docs/screenshots/desktop-quote.jpg) | ![Quote and booking form, phone](docs/screenshots/mobile-quote-booking.jpg) |
| No price (S04): specialist notice, enquiry sent | ![No price, desktop](docs/screenshots/desktop-no-price.jpg) | ![No price, phone](docs/screenshots/mobile-no-price.jpg) |
| Policy answer with source chips | ![Sources, desktop](docs/screenshots/desktop-sources.jpg) | ![Sources, phone](docs/screenshots/mobile-sources.jpg) |
| Planner: suggested tour cards and day-by-day plan | ![Planner, desktop](docs/screenshots/desktop-planner.jpg) | |

**Decision: AG-UI-style SSE instead of CopilotKit (step 11.1).** CopilotKit would need its own Node runtime between the browser and our Python graph, plus an adapter for our LangGraph state. With the submission deadline close, we used the plan's fallback instead: `POST /chat/stream` sends AG-UI event types over Server-Sent Events:

1. `RUN_STARTED`
2. `STEP_FINISHED` for each graph node, which drives the "what Mira is doing" status line
3. `TEXT_MESSAGE_START`, `TEXT_MESSAGE_CONTENT` and `TEXT_MESSAGE_END`
4. one `CUSTOM` `ui_component` event per validated component
5. `RUN_FINISHED`, carrying the full response, or `RUN_ERROR`

The frontend reads the stream with `fetch`, so there is no extra dependency. The text arrives as one block, because the reply is generated as structured output and then checked by the output guard before anyone sees it.

## Why the backend runs in Docker

The backend's dependencies are installed with **pip** inside a Linux container (`backend/Dockerfile`). This keeps native packages (FAISS, SQLAlchemy, psycopg) working the same on every machine, including Windows machines where Smart App Control blocks unsigned Python extension DLLs.
