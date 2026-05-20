# backend/app/api/search_router.py
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import Optional

from app.dependencies import get_search_service
from app.services.search_service import SearchService

router = APIRouter(prefix="/api", tags=["Search Engine"])

# ================= 数据校验模型 =================
class SearchRequest(BaseModel):
    query_text: str = Field(..., min_length=1, description="用户搜索词")
    search_type: str = Field(default="site", pattern="^(site|phrase|wildcard|document)$", description="检索模式")
    user_id: Optional[int] = Field(default=None, description="登录用户ID以开启个性化")
    page: int = Field(default=1, ge=1, description="分页页码")

# ================= 路由端点 =================

@router.post("/search")
async def execute_search(request: SearchRequest, search_service: SearchService = Depends(get_search_service)):
    """
    接收多模式检索请求，调用 Service 返回清洗与干预后的分页结果
    """
    try:
        result = search_service.process_search(
            query_text=request.query_text,
            search_type=request.search_type,
            user_id=request.user_id,
            page=request.page
        )
        return {"code": 200, "message": "success", "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Search Error: {str(e)}")

@router.get("/snapshot", response_class=HTMLResponse)
async def view_snapshot(url: str = Query(..., description="目标网页的原始URL"), search_service: SearchService = Depends(get_search_service)):
    """
    根据原始 URL 从 MySQL 映射读取本地快照文件并直接渲染给浏览器
    """
    try:
        html_content = search_service.get_snapshot(url)
        return HTMLResponse(content=html_content, status_code=200)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail="Snapshot HTML file not found on disk or DB mapping missing.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read snapshot: {str(e)}")