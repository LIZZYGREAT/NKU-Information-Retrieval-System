# backend/app/api/log_router.py
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List
from app.services.user_service import UserService

from app.dao.mysql_dao import MySQLDao 
from app.dependencies import get_user_service, get_mysql_dao

router = APIRouter(prefix="/api", tags=["Logs & Analytics"])

@router.get("/log/suggestions", response_model=dict)
async def get_search_suggestions(user_id: int = Query(...), user_service: UserService = Depends(get_user_service)):
    """
    返回用户近期的 10 条有效搜索记录，供前端自动补全使用
    """
    try:
        suggestions = user_service.get_search_suggestions(user_id)
        return {"code": 200, "data": {"suggestions": suggestions}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/admin/report")
async def get_admin_report(mysql_dao: MySQLDao = Depends(get_mysql_dao)):
    """
    供管理员调用：直接查询底层的 View_UserSearchActivity 视图
    """
    try:
        sql = "SELECT * FROM View_UserSearchActivity"
        with mysql_dao.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                report_data = cursor.fetchall()
        return {"code": 200, "data": report_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch view data: {str(e)}")