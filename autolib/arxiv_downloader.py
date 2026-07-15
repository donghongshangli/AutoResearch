"""
arxiv_downloader.py — arXiv 论文下载器

功能：给定 arXiv ID，下载 PDF 到本地缓存，文件以论文标题命名。

用法:
    from autolib.arxiv_downloader import download_paper
    result = download_paper("2412.18914")
"""

import re
import time
from pathlib import Path
from typing import Optional
from urllib.request import urlopen, Request

from .paper_cache import PaperCache


def download_paper(
    arxiv_id: str,
    project_root: Optional[str] = None,
    force: bool = False,
) -> dict:
    """下载一篇 arXiv 论文 PDF 到本地缓存。

    参数:
        arxiv_id:     arXiv ID，如 "2412.18914"
        project_root: 项目根目录，默认自动推导
        force:        True 则强制重新下载

    返回:
        {"identifier":  "arxiv-2412.18914",
         "cache_path":  "cache/arxiv-2412.18914/",
         "title":       "PRISM: Efficient Long-Range ...",
         "cached":      True/False}
    """
    identifier = f"arxiv-{_normalize_id(arxiv_id)}"
    normalized_id = _normalize_id(arxiv_id)

    cache = PaperCache(project_root)
    if not force and cache.check("arxiv", normalized_id):
        cached_path = cache.get("arxiv", normalized_id)
        return {
            "identifier": identifier,
            "cache_path": cache._to_rel(cached_path),
            "title": "",
            "cached": True,
        }

    # 获取标题
    title = _fetch_title(normalized_id)
    pdf_name = _title_to_filename(title)

    # 下载
    paper_dir = cache._cache_dir / identifier
    paper_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = paper_dir / pdf_name

    _download_pdf(normalized_id, pdf_path)

    return {
        "identifier": identifier,
        "cache_path": cache._to_rel(paper_dir),
        "title": title,
        "cached": False,
    }


_ARXIV_API = "http://export.arxiv.org/api/query"
_ARXIV_PDF = "https://arxiv.org/pdf"


def _normalize_id(raw: str) -> str:
    s = raw.strip()
    if s.lower().startswith("arxiv:"):
        s = s[len("arxiv:"):]
    if "v" in s.lower().split("/")[-1]:
        s = s.rsplit("v", 1)[0]
    return s


def _fetch_title(arxiv_id: str) -> str:
    """通过 arXiv API 获取论文标题。"""
    import xml.etree.ElementTree as ET

    url = f"{_ARXIV_API}?id_list={arxiv_id}&max_results=1"
    req = Request(url, headers={"User-Agent": "AutoResearch/1.0"})
    try:
        with urlopen(req, timeout=30) as resp:
            root = ET.fromstring(resp.read().decode("utf-8"))
    except Exception as e:
        raise RuntimeError(f"arXiv API 请求失败: {e}")

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entry = root.find("atom:entry", ns)
    if entry is None:
        raise RuntimeError(f"未找到论文: {arxiv_id}")

    title_el = entry.find("atom:title", ns)
    if title_el is not None and title_el.text:
        return title_el.text.strip().replace("\n", " ")
    return arxiv_id


def _title_to_filename(title: str, max_len: int = 120) -> str:
    """标题 → 合法文件名。"""
    # 非法字符替换
    name = re.sub(r'[\\/:*?"<>|]', "_", title)
    # 多个空白合并
    name = re.sub(r"\s+", " ", name).strip()
    # 截断
    if len(name) > max_len:
        name = name[:max_len].rsplit(" ", 1)[0]
    return name + ".pdf"


def _download_pdf(arxiv_id: str, dest: Path, timeout: int = 120, retries: int = 3) -> None:
    url = f"{_ARXIV_PDF}/{arxiv_id}"
    req = Request(url, headers={"User-Agent": "AutoResearch/1.0"})
    for attempt in range(retries):
        try:
            with urlopen(req, timeout=timeout) as resp:
                data = b""
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    data += chunk
            dest.write_bytes(data)
            return
        except Exception:
            if attempt == retries - 1:
                raise RuntimeError(f"PDF 下载失败（已重试 {retries} 次）: {url}") from None
            time.sleep(2)
