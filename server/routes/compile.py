"""
编译路由 — xelatex → PDF
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import asyncio

from server import TASKS_DIR, check_project

router = APIRouter()


class CompileResult(BaseModel):
    status: str
    pdf_path: str | None
    log: str


@router.post("/{paper_name}", response_model=CompileResult)
async def compile_paper(paper_name: str):
    check_project(paper_name)
    from server.services.compile_svc import compile_latex
    result = await asyncio.to_thread(compile_latex, TASKS_DIR / paper_name)
    return CompileResult(**result)


@router.get("/{paper_name}/pdf")
async def get_pdf(paper_name: str):
    check_project(paper_name)
    pdf_path = TASKS_DIR / paper_name / "build" / "main.pdf"
    if not pdf_path.exists():
        raise HTTPException(404, "PDF 尚未编译，请先调用 POST /compile/{paper_name}")
    return FileResponse(pdf_path, media_type="application/pdf")
