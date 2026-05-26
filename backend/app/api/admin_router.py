from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.dependencies import get_mysql_dao
from app.dao.mysql_dao import MySQLDao
from app.services.admin_service import AdminService

router = APIRouter(prefix="/api/admin", tags=["Admin"])


def get_admin_service(mysql_dao: MySQLDao = Depends(get_mysql_dao)) -> AdminService:
    return AdminService(mysql_dao)


def require_admin_id(x_admin_id: Optional[int] = Header(None, alias="X-Admin-Id")) -> int:
    if not x_admin_id:
        raise HTTPException(status_code=401, detail="缺少管理员身份 X-Admin-Id")
    return int(x_admin_id)


class AdminLoginRequest(BaseModel):
    account: str = Field(..., description="用户名或邮箱")
    password: str


class RowPayload(BaseModel):
    data: Dict[str, Any]


@router.post("/login")
def admin_login(body: AdminLoginRequest, svc: AdminService = Depends(get_admin_service)):
    try:
        return {"code": 200, "data": svc.login(body.account, body.password)}
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/tables")
def admin_tables(
    admin_id: int = Depends(require_admin_id),
    svc: AdminService = Depends(get_admin_service),
):
    try:
        svc.verify_admin(admin_id)
        return {"code": 200, "data": svc.list_tables()}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/views")
def admin_views(
    admin_id: int = Depends(require_admin_id),
    svc: AdminService = Depends(get_admin_service),
):
    try:
        svc.verify_admin(admin_id)
        return {"code": 200, "data": svc.list_views()}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/views/overview")
def admin_views_overview(
    admin_id: int = Depends(require_admin_id),
    svc: AdminService = Depends(get_admin_service),
):
    try:
        return {"code": 200, "data": svc.get_analytics_overview(admin_id)}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/views/{view_name}")
def admin_view_data(
    view_name: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str = Query(""),
    filters: str = Query(""),
    admin_id: int = Depends(require_admin_id),
    svc: AdminService = Depends(get_admin_service),
):
    try:
        return {
            "code": 200,
            "data": svc.list_view_data(admin_id, view_name, page, page_size, keyword, filters),
        }
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/stats")
def admin_stats(
    admin_id: int = Depends(require_admin_id),
    svc: AdminService = Depends(get_admin_service),
):
    try:
        return {"code": 200, "data": svc.dashboard_stats(admin_id)}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/data/{table_name}")
def admin_list(
    table_name: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str = Query(""),
    filters: str = Query("", description="JSON 筛选条件数组"),
    admin_id: int = Depends(require_admin_id),
    svc: AdminService = Depends(get_admin_service),
):
    try:
        return {"code": 200, "data": svc.list_data(admin_id, table_name, page, page_size, keyword, filters)}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/data/{table_name}")
def admin_create(
    table_name: str,
    body: RowPayload,
    admin_id: int = Depends(require_admin_id),
    svc: AdminService = Depends(get_admin_service),
):
    try:
        return {"code": 200, "data": svc.create_row(admin_id, table_name, body.data)}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/data/{table_name}/{pk_value}")
def admin_update(
    table_name: str,
    pk_value: str,
    body: RowPayload,
    admin_id: int = Depends(require_admin_id),
    svc: AdminService = Depends(get_admin_service),
):
    try:
        return {"code": 200, "data": svc.update_row(admin_id, table_name, pk_value, body.data)}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/data/{table_name}/{pk_value}")
def admin_delete(
    table_name: str,
    pk_value: str,
    admin_id: int = Depends(require_admin_id),
    svc: AdminService = Depends(get_admin_service),
):
    try:
        return {"code": 200, "data": svc.delete_row(admin_id, table_name, pk_value)}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
