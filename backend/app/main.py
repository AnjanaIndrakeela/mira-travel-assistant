"""FastAPI entry point for Mira."""

import logging
from collections import Counter
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.core.config import get_settings
from app.data_loader import get_dataset
from app.data_loader.integrity import verify

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
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
    yield


app = FastAPI(title="Mira – Ceylon Compass Holidays", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api/v1")
