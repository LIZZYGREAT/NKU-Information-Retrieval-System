# backend/app/api/user_router.py
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr,Field
from app.services.user_service import UserService
from app.dependencies import get_user_service


router = APIRouter(prefix="/api/user", tags=["Auth & User Management"])

# ================= 数据校验模型 =================
class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

# ================= 路由端点 =================

@router.post("/register")
async def register(request: RegisterRequest, user_service: UserService = Depends(get_user_service)):
    """
    处理新用户注册，底层触发器会自动分配默认推荐偏好
    """
    try:
        user_info = user_service.register_user(request.username, request.email, request.password)
        return {"code": 200, "message": "Registration successful", "data": user_info}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/login")
async def login(request: LoginRequest, user_service: UserService = Depends(get_user_service)):
    try:
        auth_info = user_service.login_user(request.email, request.password)
        return {"code": 200, "message": "Login successful", "data": auth_info}
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e))

@router.delete("/logout_permanently")
async def delete_account(user_id: int, user_service: UserService = Depends(get_user_service)):
    """
    业务场景：用户注销功能。触发底层含有事务的级联删除操作。
    """
    try:
        success = user_service.delete_account(user_id)
        if success:
            return {"code": 200, "message": "Account and all associated records securely deleted."}
    except RuntimeError as e:
        # 底层事务回滚抛出的异常
        raise HTTPException(status_code=500, detail=str(e))

class OnboardingRequest(BaseModel):
    user_id: int = Field(..., description="目标用户ID")
    role: str = Field(default="访客", description="身份枚举")
    college_id: Optional[int] = Field(default=None, description="对应 CollegeDomain 表的自增ID")
    interests: List[str] = Field(default=[], description="勾选的初始偏好标签列表")

@router.post("/onboarding")
async def complete_onboarding(request: OnboardingRequest, user_service: UserService = Depends(get_user_service)):
    """
    处理新用户冷启动信息填写。支持全参数或部分参数跳过。
    """
    try:
        success = user_service.process_onboarding(
            user_id=request.user_id, 
            role=request.role, 
            college_id=request.college_id, 
            interests=request.interests
        )
        return {"code": 200, "message": "Onboarding completed successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/profile")
async def get_profile(user_id: int, user_service: UserService = Depends(get_user_service)):
    try:
        profile = user_service.get_user_profile(user_id)
        return {"code": 200, "data": profile}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))