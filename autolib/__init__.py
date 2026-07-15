"""
autolib — AutoResearch 公共基础设施库（同学 A 维护）

对外暴露:
    PaperCache         — 论文缓存管理器
    download_paper     — arXiv 论文下载
    LatexParser        — LaTeX 结构化解析器
    Section            — 论文章节数据结构
    PaperAST           — 整篇论文解析结果
    DocGraph           — 论文文档知识图谱
    BibEntry           — 文献条目
    OutlineNode        — 论文骨架节点
    CiteSummary        — 引用文献摘要
    RefSummary         — 交叉引用摘要
    ExpandedContext    — Section 依赖摘要包
"""

from .paper_cache import PaperCache
from .arxiv_downloader import download_paper
from .latex_parser import LatexParser, Section, PaperAST
from .doc_graph import (
    DocGraph,
    BibEntry,
    OutlineNode,
    CiteSummary,
    RefSummary,
    ExpandedContext,
)
from .utils import find_main_tex
from .project_sync import sync_main_tex

__all__ = [
    "PaperCache", "download_paper",
    "LatexParser", "Section", "PaperAST",
    "DocGraph", "BibEntry",
    "OutlineNode", "CiteSummary", "RefSummary", "ExpandedContext",
]
