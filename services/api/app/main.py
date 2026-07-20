from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from app.api import router
from app.enterprise_api import router as enterprise_router
from app.context_health.router import router as context_health_router
from app.config import get_settings
from app.db.postgres import PostgresStore

settings = get_settings()
store = PostgresStore(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await store.connect()
    yield
    await store.close()


app = FastAPI(
    title=settings.app_name,
    version='2.1.0',
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.middleware('http')
async def add_request_id(request: Request, call_next):
    response = await call_next(request)
    request_id = request.headers.get('x-request-id') or request.headers.get('x-correlation-id')
    if request_id:
        response.headers['x-request-id'] = request_id
    return response


@app.get('/health')
async def health():
    connected = await store.ping()
    return {
        'status': 'ok' if connected else 'degraded',
        'app': settings.app_name,
        'environment': settings.environment,
        'version': '2.1.0',
        'postgres_connected': connected,
    }


@app.get('/ready')
async def ready():
    connected = await store.ping()
    return {
        'ready': connected and store.indexes_ready,
        'postgres_connected': connected,
        'indexes_ready': store.indexes_ready,
    }


app.include_router(router, prefix=settings.api_prefix)
app.include_router(enterprise_router, prefix=f'{settings.api_prefix}/enterprise')
app.include_router(context_health_router, prefix=f'{settings.api_prefix}/context-health', tags=['context-health'])
