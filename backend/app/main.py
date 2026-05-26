from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import search_router, user_router, log_router, query_router, admin_router
from app.core.config import settings
from app.dependencies import get_mysql_dao, get_es_dao, get_query_suggest_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        get_query_suggest_service().ensure_vocabulary(get_mysql_dao(), get_es_dao())
    except Exception:
        pass
    yield


app = FastAPI(
    title="搜索引擎与信息管理系统 API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search_router.router)
app.include_router(user_router.router)
app.include_router(log_router.router)
app.include_router(query_router.router)
app.include_router(admin_router.router)

@app.get("/")
async def root():
    return {
        "message": "NKU Information Retrieval System Backend is Running",
        "env": settings.ENV_TYPE,
        "es_index": settings.ES_INDEX_NAME,
    }
