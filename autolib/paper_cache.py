"""
paper_cache.py — 论文缓存管理器

直接基于文件系统，不维护索引文件。
缓存目录命名规则: {source}-{source_id}，如 arxiv-2412.18914

核心接口（外部脚本调用）:
    cache = PaperCache()
    cache.check("arxiv", "2412.18914")   → bool  已缓存？
    cache.get("arxiv", "2412.18914")     → Path  缓存目录
    cache.list()                          → list  所有缓存标识符
"""

import threading
from pathlib import Path
from typing import Optional


class PaperCache:
    """论文缓存管理器（进程内单例）。"""

    _instance: Optional["PaperCache"] = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls, project_root: Optional[str] = None) -> "PaperCache":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    obj = super().__new__(cls)
                    obj._initialized = False
                    cls._instance = obj
        return cls._instance

    def __init__(self, project_root: Optional[str] = None) -> None:
        if self._initialized:
            return
        if project_root is None:
            project_root = Path(__file__).resolve().parent.parent
        self._root = Path(project_root)
        self._cache_dir = self._root / "cache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._initialized = True

    # ==================================================================
    # 核心接口 — 外部调用入口
    # ==================================================================

    def check(self, source: str, source_id: str) -> bool:
        """给定来源和 ID，检查是否已缓存。

        用法: cache.check("arxiv", "2412.18914") → True/False
        """
        return _any_pdf(self._cache_dir / f"{source}-{source_id}")

    def get(self, source: str, source_id: str) -> Optional[Path]:
        """给定来源和 ID，返回缓存目录路径。未缓存返回 None。

        用法: cache.get("arxiv", "2412.18914") → Path(...) / None
        """
        paper_dir = self._cache_dir / f"{source}-{source_id}"
        if _any_pdf(paper_dir):
            return paper_dir
        return None

    def list(self) -> list[str]:
        """返回所有已缓存的标识符列表。"""
        return sorted(
            d.name
            for d in self._cache_dir.iterdir()
            if d.is_dir() and _any_pdf(d)
        )

    def _to_rel(self, path: Path) -> str:
        """绝对路径 → 项目根相对路径。"""
        try:
            return str(path.resolve().relative_to(self._root.resolve()))
        except ValueError:
            return str(path)


# ======================================================================
# 工具函数
# ======================================================================

def _any_pdf(paper_dir: Path) -> bool:
    """目录内存在任意 .pdf 文件。"""
    if not paper_dir.is_dir():
        return False
    return any(f.suffix.lower() == ".pdf" for f in paper_dir.iterdir())
