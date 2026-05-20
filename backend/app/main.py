# backend/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import search_router, user_router, log_router
import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env.dev"))
# 初始化应用实例 [cite: 5]
app = FastAPI(
    title="搜索引擎与信息管理系统 API",
    version="1.0.0"
)

# 配置 CORS 中间件，允许 B/S 架构下的前端跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # 实际部署时应替换为前端实际域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载业务路由 [cite: 7]
app.include_router(search_router.router)
app.include_router(user_router.router)
app.include_router(log_router.router)

@app.get("/")
async def root():
    return {"message": "NKU Information Retrieval System Backend is Running"}

if __name__ == "__main__":
    import uvicorn
    # 通过 uvicorn 启动 ASGI 服务器
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)