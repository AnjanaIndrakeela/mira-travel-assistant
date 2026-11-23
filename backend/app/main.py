"""FastAPI entry point for Mira."""

import logging
from collections import Counter
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.bookings import router as bookings_router
from app.api.chat import router as chat_router
from app.api.enquiries import router as enquiries_router
from app.api.errors import install_error_handlers
from app.api.health import router as health_router
from app.api.quotes import router as quotes_router
from app.api.staff import router as staff_router
from app.api.tours import router as tours_router
from app.core.config import get_settings
from app.core.logging import install_log_masking
from app.data_loader import get_dataset
from app.data_loader.integrity import verify
from app.db.seed import seed
from app.db.session import create_tables, get_sessionmaker
from app.rag import get_retriever

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
install_log_masking()          # 9.10: emails, phones and card numbers never reach the logs
logger = logging.getLogger("mira")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Check the dataset is unchanged, then load it once (read-only) for the whole app.
    integrity = verify()
    (logger.info if integrity.ok else logger.error)(integrity.summary())
    ds = get_dataset()
    logger.info("Loaded %d tours with rates, %d content docs (%d published); %d data issues: %s",
                len(ds.rates.tours), len(ds.content.docs), len(ds.content.published()),
                len(ds.issues), dict(Counter(i.code for i in ds.issues)))
    app.state.dataset = ds
    app.state.dataset_integrity_ok = integrity.ok

    # Create missing tables and seed demo users/media (both idempotent). If the database is
    # down the app still starts; /health then reports database "down".
    try:
        create_tables()
        with get_sessionmaker()() as session, session.begin():
            logger.info("Seed: %s", seed(session).summary())
    except Exception as exc:  # noqa: BLE001
        logger.error("Database setup skipped: %s", exc.__class__.__name__)

    # Content index (R4): loads from backend/var/index/, embeds only if the content changed.
    # Without a Gemini key the app still starts; /health then reports index "unavailable".
    try:
        app.state.retriever = get_retriever()
    except Exception as exc:  # noqa: BLE001
        app.state.retriever = None
        logger.warning("Content index unavailable: %s", exc)
    yield


app = FastAPI(title="Mira – Ceylon Compass Holidays", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # the frontend's origin, written either way (localhost / 127.0.0.1)
    allow_origins=sorted({settings.frontend_origin,
                          settings.frontend_origin.replace("://localhost", "://127.0.0.1")}),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

install_error_handlers(app)
for r in (health_router, chat_router, quotes_router, enquiries_router, tours_router, bookings_router,
          staff_router):
    app.include_router(r, prefix="/api/v1")
