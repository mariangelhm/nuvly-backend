import asyncio
from contextlib import asynccontextmanager, suppress
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.core.config import get_settings
from app.core.database import close_database, create_indexes, ping_database
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.modules.auth.routes import router as auth_router
from app.modules.auth.routes import admin_router as auth_admin_router
from app.modules.auth.service import AuthService
from app.modules.catalog.routes import admin_router as catalog_admin_router
from app.modules.catalog.routes import router as catalog_router
from app.modules.domain.customer_routes import router as customer_router
from app.modules.domain.public_routes import router as public_router
from app.modules.domain.studio_routes import admin_router as studio_admin_router
from app.modules.domain.studio_routes import router as studio_router
from app.modules.health.routes import router as health_router
from app.modules.media.routes import router as media_router
from app.modules.media.service import ensure_static_directories
from app.modules.payments.routes import router as payments_router
from app.modules.pricing.routes import admin_router as pricing_admin_router
from app.modules.pricing.routes import router as pricing_router
from app.modules.pricing.service import ensure_pricing_seed

NUVLY_INTERNAL_EMAIL = "nuvlystudio@gmail.com"
NUVLY_INTERNAL_PASSWORD = "Admin.1234"
from app.modules.support.routes import router as support_router

configure_logging()
logger = logging.getLogger(__name__)


async def initialize_application(app: FastAPI) -> None:
    logger.info("Starting Nuvly Backend")
    try:
        await asyncio.to_thread(ping_database)
        await asyncio.to_thread(create_indexes)
        seed_stats = await asyncio.to_thread(ensure_pricing_seed)
        internal_user = await asyncio.to_thread(
            lambda: AuthService().ensure_internal_user(
                email=NUVLY_INTERNAL_EMAIL,
                password=NUVLY_INTERNAL_PASSWORD,
                name="Nuvly",
                internal_role="admin",
            )
        )
        app.state.startup_status = "ready"
        app.state.startup_error = None
        logger.info("MongoDB connected and indexes created")
        logger.info(
            "Pricing seed ensured | insertedPlans=%s insertedComponents=%s insertedTemplateCategories=%s skippedPlans=%s skippedComponents=%s skippedTemplateCategories=%s",
            seed_stats.insertedPlans,
            seed_stats.insertedComponents,
            seed_stats.insertedTemplateCategories,
            seed_stats.skippedPlans,
            seed_stats.skippedComponents,
            seed_stats.skippedTemplateCategories,
        )
        logger.info("Internal auth user ensured | email=%s userId=%s", internal_user["email"], internal_user["id"])
    except Exception as exc:
        app.state.startup_status = "degraded"
        app.state.startup_error = str(exc)
        logger.exception("MongoDB startup failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.startup_status = "starting"
    app.state.startup_error = None
    startup_task = asyncio.create_task(initialize_application(app))
    try:
        yield
    finally:
        if not startup_task.done():
            startup_task.cancel()
            with suppress(asyncio.CancelledError):
                await startup_task
        close_database()
        logger.info("Nuvly Backend stopped")

settings = get_settings()
ensure_static_directories()
app = FastAPI(
    title=settings.app_name,
    description="Backend MVP para Nuvly Studio: páginas web e invitaciones digitales desde configuración estructurada.",
    version="0.1.0-python314",
    docs_url=f"{settings.api_prefix}/docs",
    redoc_url=f"{settings.api_prefix}/redoc",
    openapi_url=f"{settings.api_prefix}/openapi.json",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_exception_handlers(app)
app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(auth_admin_router, prefix=settings.api_prefix)
app.include_router(health_router, prefix=settings.api_prefix)
app.include_router(media_router, prefix=settings.api_prefix)
app.include_router(payments_router, prefix=settings.api_prefix)
app.include_router(catalog_router, prefix=settings.api_prefix)
app.include_router(catalog_admin_router, prefix=settings.api_prefix)
app.include_router(pricing_router, prefix=settings.api_prefix)
app.include_router(pricing_admin_router, prefix=settings.api_prefix)
app.include_router(studio_router, prefix=settings.api_prefix)
app.include_router(studio_admin_router, prefix=settings.api_prefix)
app.include_router(public_router, prefix=settings.api_prefix)
app.include_router(customer_router, prefix=settings.api_prefix)
app.include_router(support_router, prefix=settings.api_prefix)

@app.get("/")
def root():
    return {"service": settings.app_name, "env": settings.app_env, "docs": f"{settings.api_prefix}/docs"}
