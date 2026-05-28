from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.routes import digest, embeddings, events, icebreaker, profiles

settings = get_settings()
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.core.supabase import get_supabase_client
    await get_supabase_client()
    yield


app = FastAPI(
    title="Knit API",
    version="0.1.0",
    docs_url="/docs" if not settings.is_prod else None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://joinknit.app"] if settings.is_prod else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(events.router)
app.include_router(profiles.router)
app.include_router(embeddings.router)
app.include_router(icebreaker.router)
app.include_router(digest.router)


@app.get("/health")
async def health():
    return {"status": "ok", "environment": settings.ENVIRONMENT}
