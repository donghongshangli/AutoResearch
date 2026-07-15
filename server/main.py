"""
AutoResearch 后端入口

启动: uvicorn server.main:app --reload --host 0.0.0.0 --port 8000
"""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from server.routes import papers, compile, edit, projects, formula, request, tasks, git

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("autoresearch")

app = FastAPI(title="AutoResearch", version="0.1.0")

# CORS: 全开（内部开发工具，不暴露公网）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(projects.router, prefix="/api/projects", tags=["项目管理"])
app.include_router(papers.router, prefix="/api/papers", tags=["论文编辑"])
app.include_router(compile.router, prefix="/api/compile", tags=["编译"])
app.include_router(edit.router, prefix="/api/edit", tags=["润色检查"])
app.include_router(formula.router, prefix="/api/formula", tags=["公式识别"])
app.include_router(request.router, prefix="/api/request", tags=["请求面板"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["任务执行（SSE流式）"])
app.include_router(git.router, prefix="/api/git", tags=["Git 版本管理"])


@app.on_event("startup")
async def startup():
    logger.info("AutoResearch 已启动 — http://127.0.0.1:8000")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# ── 前端托管 ──
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.get("/", response_class=HTMLResponse)
async def index():
    """托管前端首页。"""
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return HTMLResponse(index_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>frontend/index.html not found</h1>", status_code=404)
