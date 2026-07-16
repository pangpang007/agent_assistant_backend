from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.core.redis import close_redis, init_redis
from app.middleware import setup_cors, setup_security_middleware
from app.middleware.auth import AuthMiddleware
from app.middleware.error_handler import setup_error_handlers
from app.middleware.request_log import RequestLogMiddleware

setup_logging()

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("starting_application", app_name=settings.app_name)
    await init_redis()

    from app.core.database import async_session_factory
    from app.core.seed import seed_preset_data

    try:
        async with async_session_factory() as session:
            await seed_preset_data(session)
    except Exception as e:
        logger.warning("seed_failed", error=str(e))

    yield
    await close_redis()
    logger.info("stopping_application")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Middleware order (last added = outermost / runs first on request):
# RequestLog → security → Auth → CORS
app.add_middleware(RequestLogMiddleware)
setup_security_middleware(app)
app.add_middleware(AuthMiddleware)
setup_cors(app)
setup_error_handlers(app)

app.include_router(api_router)
