"""
任务执行路由 — 统一 SSE 流式等待接口

GET /api/tasks/{project}/{group}/stream
  读 request.json → 调对应模块 run() → SSE 推送进度

模块只需在 run() 里调 progress(stage, message, percent)。
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import asyncio
import json
import importlib
import threading
from queue import Queue as ThreadQueue, Empty

from server import TASKS_DIR, check_project

router = APIRouter()

GROUP_MODULE = {
    "B": "modules.b_agent",
    "C": "modules.c_polish",
    "D": "modules.d_lang_check",
    "E": "modules.e_workflow",
}


@router.get("/{project}/{group}/stream")
async def task_stream(project: str, group: str):
    """SSE 流式任务执行。"""
    if group not in GROUP_MODULE:
        raise HTTPException(400, f"无效组: {group}")
    check_project(project)

    req_path = TASKS_DIR / project / group / "request.json"
    if not req_path.exists():
        raise HTTPException(400, f"请先提交 {group} 组请求")

    mod = importlib.import_module(GROUP_MODULE[group])
    run_fn = getattr(mod, "run")

    tq: ThreadQueue = ThreadQueue()
    done = threading.Event()

    def _in_thread():
        try:
            def _progress(stage, msg, pct):
                tq.put({"stage": stage, "message": msg, "percent": pct})

            result = run_fn(str(TASKS_DIR / project), progress=_progress)
            tq.put({"stage": "done", "message": "完成", "percent": 100, "result": result})
        except Exception as exc:
            tq.put({"stage": "error", "message": str(exc), "percent": 0})
        finally:
            done.set()

    threading.Thread(target=_in_thread, daemon=True).start()

    async def _event_stream():
        try:
            while True:
                try:
                    data = tq.get(timeout=0.2)
                except Empty:
                    if done.is_set():
                        break
                    await asyncio.sleep(0.1)
                    continue
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                if data["stage"] in ("done", "error"):
                    break
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
