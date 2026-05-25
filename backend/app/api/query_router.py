from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional

from app.dependencies import get_query_suggest_service, get_mysql_dao, get_es_dao
from app.services.query_suggest_service import QuerySuggestService
from app.dao.mysql_dao import MySQLDao
from app.dao.es_dao import EsDAO

router = APIRouter(prefix="/api/query", tags=["Query Suggest & Correct"])


@router.get("/history")
def query_history(
    user_id: Optional[int] = None,
    limit: int = Query(8, ge=1, le=20),
    svc: QuerySuggestService = Depends(get_query_suggest_service),
    mysql_dao: MySQLDao = Depends(get_mysql_dao),
):
    try:
        items = svc.history_suggestions(user_id, mysql_dao, limit=limit)
        return {"code": 200, "data": {"suggestions": items}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/associate")
def query_associate(
    q: str = Query(..., min_length=1),
    user_id: Optional[int] = None,
    limit: int = Query(8, ge=1, le=20),
    svc: QuerySuggestService = Depends(get_query_suggest_service),
    mysql_dao: MySQLDao = Depends(get_mysql_dao),
    es_dao: EsDAO = Depends(get_es_dao),
):
    try:
        data = svc.associate(q, user_id, mysql_dao, es_dao, limit=limit)
        return {"code": 200, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/suggest")
def query_suggest(
    q: str = Query(..., min_length=1),
    user_id: Optional[int] = None,
    limit: int = Query(8, ge=1, le=20),
    svc: QuerySuggestService = Depends(get_query_suggest_service),
    mysql_dao: MySQLDao = Depends(get_mysql_dao),
    es_dao: EsDAO = Depends(get_es_dao),
):
    try:
        data = svc.associate(q, user_id, mysql_dao, es_dao, limit=limit)
        return {"code": 200, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/correct")
def query_correct(
    q: str = Query(..., min_length=1),
    svc: QuerySuggestService = Depends(get_query_suggest_service),
    mysql_dao: MySQLDao = Depends(get_mysql_dao),
    es_dao: EsDAO = Depends(get_es_dao),
):
    try:
        result = svc.correct(q, mysql_dao, es_dao)
        return {"code": 200, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reload-vocab")
def reload_vocabulary(
    svc: QuerySuggestService = Depends(get_query_suggest_service),
    mysql_dao: MySQLDao = Depends(get_mysql_dao),
    es_dao: EsDAO = Depends(get_es_dao),
):
    try:
        n = svc.reload_vocabulary(mysql_dao, es_dao)
        return {"code": 200, "data": {"count": n}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
