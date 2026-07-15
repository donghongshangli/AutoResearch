"""
公式识别路由 — 手写公式图片 → LaTeX + PDF 预览
"""

import uuid
import shutil
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from server import TASKS_DIR as _ROOT  # WORK_DIR needs project root, not tasks/

router = APIRouter()

ROOT = _ROOT.parent  # AutoResearch 项目根


class FormulaResult(BaseModel):
    status: str
    latex: str | None = None
    pdf_url: str | None = None
    message: str = ""


@router.post("/recognize", response_model=FormulaResult)
async def recognize_formula(file: UploadFile = File(...)):
    from server.services.formula_svc import recognize_formula as do_recognize, compile_formula

    upload_dir = ROOT / "cache" / "formula" / "upload"
    upload_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename).suffix if file.filename else ".png"
    if ext.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
        raise HTTPException(400, f"不支持的格式: {ext}（支持 png/jpg/webp）")

    img_path = upload_dir / f"{uuid.uuid4().hex}{ext.lower()}"
    with open(img_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    latex, error = do_recognize(str(img_path))
    if error:
        return FormulaResult(status="error", message=error)
    if not latex:
        return FormulaResult(status="error", message="识别结果为空")

    comp = compile_formula(latex, ROOT)
    if comp["status"] != "ok":
        return FormulaResult(status="ok", latex=latex, message=f"编译失败:\n{comp.get('log', '')}")
    return FormulaResult(status="ok", latex=latex, pdf_url="/formula/pdf")


@router.get("/pdf")
async def get_formula_pdf():
    pdf = ROOT / "cache" / "formula" / "build" / "formula.pdf"
    if pdf.exists():
        return FileResponse(pdf, media_type="application/pdf")
    raise HTTPException(404, "PDF 未找到")
