from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.core.database import close_database, create_indexes, ping_database
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.modules.experiences.routes import router as experiences_router
from app.modules.health.routes import router as health_router
from app.modules.published.routes import router as published_router

configure_logging()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Nuvly Backend")
    ping_database()
    create_indexes()
    logger.info("MongoDB connected and indexes ensured")
    yield
    close_database()
    logger.info("Nuvly Backend stopped")

settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    description="Backend MVP para Nuvly Studio: páginas web e invitaciones digitales desde configuración estructurada.",
    version="0.1.0-python314",
    docs_url=f"{settings.api_prefix}/docs",
    redoc_url=f"{settings.api_prefix}/redoc",
    openapi_url=f"{settings.api_prefix}/openapi.json",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_exception_handlers(app)
app.include_router(health_router, prefix=settings.api_prefix)
app.include_router(experiences_router, prefix=settings.api_prefix)
app.include_router(published_router, prefix=settings.api_prefix)

@app.get("/")
def root():
    return {"service": settings.app_name, "env": settings.app_env, "docs": f"{settings.api_prefix}/docs"}
