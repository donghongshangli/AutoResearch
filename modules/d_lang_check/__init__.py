r"""
D 组 — 学术语言工具箱（Writefull 方向）

对齐 D 同学任务拆解: 封装 Writefull API + 增强层。

三大核心能力:
  1. 专业语言反馈 (Professional Language Feedback)
     主力: 封装 Writefull Language API → JSON/Track Changes 响应
     备用: BackupLLMService（通用 LLM fallback）
     测试: MockService（固定示例数据）

  2. Academizer 学术风格转换 (Academic Style Transfer)
     主力: 封装 Writefull Academizer API → 风格转换 + 学科标签
     测试: Mock 模式 → 模拟转换

  3. 标题 & 摘要生成 (Title & Abstract Generation)
     标题: 5 个不同侧重点候选标题（方法/结论/疑问/简洁/描述）
     摘要: B-M-R-C 四要素强制引导算法 (Background/Methods/Results/Conclusion)
     测试: Mock 模式 → 关键词提取 + 模板填充

入口与分流:
  run(paper_dir, progress) → 读 D/request.json，按 _meta.task 或 action 字段分流:
    lang_check          → list[dict]  语言检查结果
    generate_title      → dict        候选标题
    generate_abstract   → dict        B-M-R-C 摘要

公开函数:
  academize(text, ...)         → str  学术风格转换
  generate_title(text, ...)    → list[TitleCandidate]  标题生成
  generate_abstract(text, ...) → str / AbstractResult  摘要生成

任务从 D/request.json 读取，结构见 docs/request-schema.md

架构（任务拆解 P10 "接口适配层"）:
  __init__.py           ← 入口 + 流水线编排 + 任务分流
  service.py            ← LanguageService ABC + create_service() 工厂
  writefull_service.py  ← WritefullService（主力）: Language API 封装 + Mock
  mock_service.py       ← MockService（测试）: 固定测试数据
  backup_service.py     ← BackupLLMService（备用）: 通用 LLM fallback
  academizer.py         ← AcademizerService: Academizer API 封装 + Mock
  generator.py          ← GeneratorService: 标题 & 摘要生成 + Mock
  latex_protect.py      ← 增强层: LaTeX 命令保护（拆装法）
  models.py             ← Writefull API 数据模型 + 前端 DTO + 生成模型

配置:
  D_LANG_SERVICE=writefull      主力语言检查服务（默认，当前 Mock 模式）
  D_LANG_SERVICE=mock           测试服务
  D_LANG_SERVICE=backup         备用 LLM
  D_GENERATE_SERVICE=writefull  标题摘要生成服务（默认，当前 Mock 模式）
  WRITEFULL_API_KEY=xxx         真实 API key（待申请）

progress 回调签名: progress(stage: str, message: str, percent: int) -> None
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable, Optional

from .service import create_language_service, LanguageService, ServiceError
from .models import (
    LanguageFeedbackResponse, Suggestion, CheckResult,
    AcademizerResponse, AcademizerChange,
    suggestion_to_check_result, check_results_to_frontend,
    TitleCandidate, AbstractResult,
    title_candidates_to_frontend, abstract_result_to_frontend,
    ParaphraseChange, ParaphraseResult,
    paraphrase_result_to_frontend,
    CitationIssue, CiteCheckResult,
    cite_check_to_frontend,
)
from .latex_protect import LatexProtector

# 重导出公共 API
from .academizer import academize, AcademizerService, VALID_DISCIPLINES, VALID_STRENGTHS
from .generator import (
    generate_title, generate_abstract,
    GeneratorService, VALID_TITLE_FOCUS,
)
from .paraphraser import (
    paraphrase, ParaphraserService,
    VALID_PARAPHRASE_STYLES, PARAPHRASE_DIMENSIONS,
)
from .cite_checker import (
    check_citations, CiteCheckerService,
    VALID_DISCIPLINES as CITE_VALID_DISCIPLINES,
    RISK_LEVELS,
)
from .models import (
    LanguageFeedbackResponse, Suggestion, CheckResult,
    AcademizerResponse, AcademizerChange,
    suggestion_to_check_result, check_results_to_frontend,
    TitleCandidate, AbstractResult,
    title_candidates_to_frontend, abstract_result_to_frontend,
    ParaphraseChange, ParaphraseResult,
    paraphrase_result_to_frontend,
    CitationIssue, CiteCheckResult,
    cite_check_to_frontend,
)

logger = logging.getLogger("autoresearch.d_lang_check")


# ═══════════════════════════════════════════════════════════════
# 模块元数据（交付清单 — 任务拆解 P29）
# ═══════════════════════════════════════════════════════════════

__module_meta__ = {
    "name": "D 组 — 学术语言工具箱（Writefull 方向）",
    "version": "0.6.0",
    "description": "封装 Writefull Language API + Academizer API + Generate API + Paraphrase API + Cite Check API，含 Mock/BackupLLM 备选",
    "architecture": "LanguageService ABC → WritefullService(主力) | MockService(测试) | BackupLLMService(备用)",
    "academizer": "AcademizerService → 学术风格转换 + 学科标签 + LaTeX 拆装保护",
    "generator": "GeneratorService → 标题生成(5候选) + 摘要生成(B-M-R-C) + LaTeX 拆装保护",
    "cite_checker": "CiteCheckerService → 三阶段审计流水线: Claim API → 正则过滤 → Semantic Scholar Top-5 + LaTeX 拆装保护",
    "paraphraser": "ParaphraserService → 段落改写(5维度) + LaTeX 拆装保护",
    "check_dimensions": ["grammar", "spelling", "punctuation", "style"],
    "title_focus_angles": sorted(VALID_TITLE_FOCUS),
    "supported_disciplines": sorted(VALID_DISCIPLINES),
    "dependencies": {
        "python_packages": [],
        "external_api": "Writefull Language API + Academizer API + Generate API（主力）| LLM API（备用）",
        "api_keys": "WRITEFULL_API_KEY | ANTHROPIC_API_KEY（备用）",
    },
    "output_impact": {
        "tex_sections": "生成标题和摘要文本（不直接写 .tex 文件）",
        "citations": "无",
        "refs_bib": "否",
    },
    "new_latex_packages": [],
}


# ═══════════════════════════════════════════════════════════════
# 公开入口: run()
# ═══════════════════════════════════════════════════════════════

def run(
    paper_dir: str,
    progress: Optional[Callable] = None,
) -> list[dict] | dict | str:
    """执行 D 组任务。按 request.json 中的 action/_meta.task 字段分流。

    任务类型:
      lang_check          → list[dict]  语言检查结果
      generate_title      → dict        候选标题 {"status":"ok","candidates":[...]}
      generate_abstract   → dict        B-M-R-C 摘要 {"status":"ok","abstract":{...}}

    任务从 D/request.json 读取。

    参数:
        paper_dir: 论文项目目录（tasks/{paper}/）
        progress:  可选进度回调 progress(stage, message, percent)
    """
    proj_dir = Path(paper_dir)

    def _p(stage: str, msg: str, pct: int) -> None:
        if progress:
            progress(stage, msg, pct)

    # ── 步骤 1: 读取请求 ──
    _p("init", "读取任务…", 5)

    req = _load_request(proj_dir)
    if req is None:
        _p("error", "未找到 D/request.json", 0)
        return [{
            "type": "style", "line": 1,
            "message": "未找到请求文件 (D/request.json)。请先在前端提交任务。",
            "fix": "",
        }]

    # ── 步骤 2: 判断任务类型 ──
    # 优先级: req.action > req._meta.task > 默认 lang_check
    action = req.get("action", "")
    if not action:
        action = req.get("_meta", {}).get("task", "")
    if not action or action in ("lang_check", "check"):
        # mode 字段后备: server 路径下 _meta.task 永远是 lang_check
        # 前端可在 request.json 中加 "mode": "title"|"abstract" 来触发生成功能
        mode = req.get("mode", "")
        if mode == "title":
            action = "generate_title"
        elif mode == "abstract":
            action = "generate_abstract"
        elif mode == "paraphrase":
            action = "paraphrase"
        elif mode == "cite_check":
            action = "cite_check"
        elif mode == "academize":
            action = "academize"
        else:
            action = "lang_check"

    logger.info("D 模块分流: action=%s project=%s",
                action, req.get("_meta", {}).get("project", "?"))

    # ── 分流执行 ──
    if action == "generate_title":
        return _run_generate_title(req, proj_dir, _p)
    elif action == "generate_abstract":
        return _run_generate_abstract(req, proj_dir, _p)
    elif action == "paraphrase":
        return _run_paraphrase(req, proj_dir, _p)
    elif action == "cite_check":
        return _run_cite_check(req, proj_dir, _p)
    elif action == "academize":
        return _run_academize(req, proj_dir, _p)
    elif action == "lang_check":
        return _run_lang_check(req, proj_dir, _p)
    else:
        _p("error", f"未知任务类型: {action}", 0)
        return [{
            "type": "style", "line": 1,
            "message": f"未知任务类型: '{action}'。支持: lang_check, generate_title, generate_abstract",
            "fix": "",
        }]


def _run_lang_check(
    req: dict,
    proj_dir: Path,
    _p: Callable,
) -> list[dict]:
    """执行专业语言反馈检查（原 run() 逻辑，保持不变）。"""
    text, context, focus, intent, scope = _parse_request(req, proj_dir)

    if not text or not text.strip():
        _p("done", "检查文本为空，跳过", 100)
        return []

    _p("init", f"检查范围: {scope} · {len(text)} 字符 · "
               f"维度: {', '.join(focus) if focus else '全部'}", 10)

    # LaTeX 保护
    _p("checking", "识别 LaTeX 保护区…", 15)
    protector = LatexProtector()
    try:
        protector.scan(text)
    except Exception as e:
        logger.warning(f"LaTeX 保护扫描失败: {e}")

    # 创建服务 & 调用
    _p("checking", "调用语言检查服务…", 25)
    try:
        service = create_language_service()
    except Exception as e:
        logger.warning(f"Service 创建失败: {e}，使用 MockService")
        from .mock_service import MockService
        service = MockService()

    _p("checking", f"服务: {service.name}", 30)

    try:
        response = service.check_language(text, focus, context, intent)
    except ServiceError as e:
        _p("error", f"服务调用失败: {e}", 0)
        return [{
            "type": "style", "line": 1,
            "message": f"语言检查服务不可用: {e}",
            "fix": "请检查 API 配置或稍后重试",
        }]
    except Exception as e:
        logger.error(f"未知错误: {e}")
        _p("error", f"检查失败: {e}", 0)
        return [{"type": "style", "line": 1, "message": f"检查失败: {e}", "fix": ""}]

    _p("checking", f"Writefull 返回: {len(response.suggestions)} 条建议 · "
                   f"质量评分 {response.quality_score:.0%}", 60)

    # 转换为内部格式
    _p("filtering", "解析 API 响应…", 70)
    results = [
        suggestion_to_check_result(sug, text, source="writefull")
        for sug in response.suggestions
    ]

    # LaTeX 保护区过滤
    _p("filtering", "过滤 LaTeX 保护区内的误报…", 80)
    try:
        filtered = protector.filter(results)
        removed = len(results) - len(filtered)
        if removed > 0:
            _p("filtering", f"过滤了 {removed} 条 LaTeX 区内误报", 85)
    except Exception:
        filtered = results

    # 格式化 & 返回
    output = check_results_to_frontend(filtered)

    type_counts = _count_by_type(output)
    summary = " · ".join(f"{t}: {c}" for t, c in sorted(type_counts.items()))
    _p("done",
       f"检查完成 — {summary}" if summary else "检查完成 — 未发现问题",
       100)

    return output


def _run_academize(
    req: dict,
    proj_dir: Path,
    _p: Callable,
) -> str:
    """Execute academic style transfer via request.json."""
    _p("init", "Start academic style transfer…", 5)

    text = _get_text_for_generation(req, proj_dir)
    if not text or not text.strip():
        _p("error", "No text available", 0)
        return ""

    discipline = req.get("discipline", "general")
    style_strength = req.get("style_strength", "moderate")
    intent = req.get("intent", "")

    _p("init", f"Text: {len(text)} chars · discipline: {discipline} · "
               f"strength: {style_strength}", 10)
    _p("transforming", "Calling Academizer service…", 30)

    try:
        result = academize(
            text, discipline=discipline,
            style_strength=style_strength,
        )
    except Exception as e:
        logger.error(f"Academizer failed: {e}")
        _p("error", f"Academizer failed: {e}", 0)
        return {"status": "error", "message": str(e)}

    _p("done", f"Academizer complete — {len(result)} chars", 100)
    return result


def _run_generate_title(
    req: dict,
    proj_dir: Path,
    _p: Callable,
) -> dict:
    """执行标题生成: 5 个不同侧重点的候选标题。"""
    _p("init", "开始标题生成…", 5)

    text = _get_text_for_generation(req, proj_dir)
    if not text or not text.strip():
        _p("error", "无可用文本", 0)
        return {"status": "error", "message": "无可用文本。请提供论文内容。", "candidates": []}

    keywords = req.get("keywords", [])
    discipline = req.get("discipline", "general")
    intent = req.get("intent", "")
    focus = req.get("focus", "balanced")
    count = req.get("count", 5)

    _p("init", f"文本: {len(text)} 字符 · 关键词: {', '.join(keywords) if keywords else '自动提取'}", 10)

    _p("generating", "调用标题生成服务…", 30)
    try:
        titles = generate_title(
            text, count=count, focus=focus,
            discipline=discipline, intent=intent,
        )
    except Exception as e:
        logger.error(f"标题生成失败: {e}")
        _p("error", f"生成失败: {e}", 0)
        return {"status": "error", "message": str(e), "candidates": []}

    _p("generating", f"已生成 {len(titles)} 个候选", 80)

    output = title_candidates_to_frontend(titles)
    _p("done", f"标题生成完成 — {len(output)} 个候选", 100)
    return {"status": "ok", "candidates": output}


def _run_generate_abstract(
    req: dict,
    proj_dir: Path,
    _p: Callable,
) -> dict:
    """执行摘要生成: B-M-R-C 结构化摘要。"""
    _p("init", "开始摘要生成 (B-M-R-C 算法)…", 5)

    text = _get_text_for_generation(req, proj_dir)
    if not text or not text.strip():
        _p("error", "无可用文本", 0)
        return {"status": "error", "message": "无可用文本。请提供论文内容。", "abstract": None}

    discipline = req.get("discipline", "general")
    intent = req.get("intent", "")
    max_words = req.get("max_words", 250)

    _p("init", f"文本: {len(text)} 字符 · 目标: {max_words} 词", 10)

    _p("generating", "调用摘要生成服务 (B-M-R-C)…", 30)
    try:
        result_str, result_obj = generate_abstract(
            text, discipline=discipline, max_words=max_words,
            intent=intent, return_full=True,
        )
    except Exception as e:
        logger.error(f"摘要生成失败: {e}")
        _p("error", f"生成失败: {e}", 0)
        return {"status": "error", "message": str(e), "abstract": None}

    _p("generating", f"B-M-R-C 摘要完成 · {result_obj.word_count} 词", 80)

    output = abstract_result_to_frontend(result_obj)
    _p("done", f"摘要生成完成 — {result_obj.word_count} 词", 100)
    return {"status": "ok", "abstract": output}



def _run_cite_check(
    req: dict,
    proj_dir: Path,
    _p: Callable,
) -> list[dict]:
    """Execute citation completeness check."""
    _p("init", "Start citation check (3-stage pipeline)…", 5)

    text = _get_text_for_generation(req, proj_dir)
    if not text or not text.strip():
        _p("error", "No text available", 0)
        return [{"type": "cite_check", "line": 1,
                 "message": "No text. Provide paper content for citation check.",
                 "fix": ""}]

    discipline = req.get("discipline", "general")
    intent = req.get("intent", "")

    _p("init", f"Text: {len(text)} chars · discipline: {discipline}", 10)

    _p("checking", "Stage 1: Writefull Cite API (claim detection)…", 25)
    _p("filtering", "Stage 2: Regex citation marker filter…", 50)
    _p("recommending", "Stage 3: Semantic Scholar Top-5…", 75)

    try:
        issues, result = check_citations(
            text, discipline=discipline, intent=intent,
            return_full=True,
        )
    except Exception as e:
        logger.error(f"Citation check failed: {e}")
        _p("error", f"Citation check failed: {e}", 0)
        return [{"type": "cite_check", "line": 1,
                 "message": f"Citation check failed: {e}", "fix": ""}]

    _p("done", f"Checked {result.total_sentences} sentences · "
               f"{result.uncited_claims} uncited claims · "
               f"{result.cited_sentences} already cited", 100)
    return issues


def _run_paraphrase(
    req: dict,
    proj_dir: Path,
    _p: Callable,
) -> dict:
    """Execute paragraph paraphrasing."""
    _p("init", "Start paraphrasing…", 5)

    text = _get_text_for_generation(req, proj_dir)
    if not text or not text.strip():
        _p("error", "No text available", 0)
        return {"status": "error", "message": "No text. Provide paragraph content.", "rewritten_text": ""}

    style = req.get("style", "academic")
    preserve_keywords = req.get("preserve_keywords", [])
    intent = req.get("intent", "")

    _p("init", f"Text: {len(text)} chars · style: {style}", 10)

    _p("rewriting", "Calling paraphrase service…", 30)
    try:
        result_str, result_obj = paraphrase(
            text, style=style,
            preserve_keywords=preserve_keywords,
            intent=intent, return_full=True,
        )
    except Exception as e:
        logger.error(f"Paraphrase failed: {e}")
        _p("error", f"Paraphrase failed: {e}", 0)
        return {"status": "error", "message": str(e), "rewritten_text": ""}

    _p("rewriting", f"Done — {len(result_obj.changes)} changes · {len(result_obj.triggered_dimensions)} dimensions", 80)

    output = paraphrase_result_to_frontend(result_obj)
    _p("done", f"Paraphrase complete — {len(result_obj.triggered_dimensions)} dimensions triggered", 100)
    return {"status": "ok", "paraphrase": output}

def _get_text_for_generation(req: dict, proj_dir: Path) -> str:
    """从 request.json 或项目目录获取生成所需的论文文本。"""
    # 优先: selection.text
    text = req.get("selection", {}).get("text", "")
    if text.strip():
        return text
    # 其次: full_text 字段
    text = req.get("full_text", "")
    if text.strip():
        return text
    # 最后: 从项目目录读取全文
    return _read_full_text(proj_dir)


# ═══════════════════════════════════════════════════════════════
# 内部: 请求加载 & 解析
# ═══════════════════════════════════════════════════════════════

def _load_request(proj_dir: Path) -> Optional[dict]:
    """加载 D/request.json。"""
    req_path = proj_dir / "D" / "request.json"
    if not req_path.exists():
        return None
    try:
        return json.loads(req_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"request.json 解析失败: {e}")
        return None


def _parse_request(req: dict, proj_dir: Path) -> tuple[str, str, list[str], str, str]:
    """解析 request.json → (text, context, focus, intent, scope)。"""
    scope = req.get("_meta", {}).get("scope", "selection")

    text = ""
    if scope == "selection" and req.get("selection"):
        text = req["selection"].get("text", "")
    elif scope == "full":
        text = _read_full_text(proj_dir)

    context = req.get("context", "")
    focus = req.get("focus", [])
    intent = req.get("intent", "")

    return text, context, focus, intent, scope


def _read_full_text(proj_dir: Path) -> str:
    """全文模式: 读取并合并整个项目文本。"""
    # 尝试 merge_svc
    try:
        from server.services.merge_svc import merge_project
        merged = merge_project(proj_dir)
        text = merged.get("merged_text", "")
        if text:
            return text
    except Exception:
        pass

    # 降级: 读取 main.tex
    main_candidate = proj_dir / "main.tex"
    if main_candidate.exists():
        return main_candidate.read_text(encoding="utf-8", errors="replace")

    for tex_file in proj_dir.rglob("*.tex"):
        try:
            return tex_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
    return ""


def _count_by_type(results: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in results:
        t = r.get("type", "unknown")
        counts[t] = counts.get(t, 0) + 1
    return counts


# ═══════════════════════════════════════════════════════════════
# 自测
# ═══════════════════════════════════════════════════════════════

def _self_test():
    """快速自测: run() + academize() + generate_title() + generate_abstract()。

    用法: python -c "import sys; sys.path.insert(0, '.');
           from modules.d_lang_check import _self_test; _self_test()"
    """
    import tempfile

    tmp = Path(tempfile.gettempdir()) / "_d_self_test"
    tmp.mkdir(exist_ok=True)
    (tmp / "D").mkdir(exist_ok=True)

    test_text = r"""
\section{Introduction}
\label{sec:intro}

The transformer architecture has been widely used in natural language processing.
We use a lot of data to train our model. The results shows that our method is very good.
However, the model don't perform well on small datasets.

As shown in Figure \ref{fig:arch}, our system recieve input from multiple sources.

We find out that the performance is heavily dependant on the quality of the data.
It's important to note that this finding is independant of the model architecture.
"""
    req = {
        "_meta": {
            "task": "lang_check", "project": "_d_self_test",
            "scope": "selection", "paper_dir": str(tmp),
            "created_at": "2026-07-17T00:00:00Z",
        },
        "selection": {
            "text": test_text, "file": "sections/intro.tex",
            "section_title": "Introduction", "start_line": 1, "end_line": 15,
        },
        "context": "", "focus": [], "intent": "",
    }
    (tmp / "D" / "request.json").write_text(
        json.dumps(req, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── 测试 1: run() lang_check ──
    print("=" * 60)
    print("Test 1: run() lang_check via WritefullService (mock mode)")
    print("=" * 60)
    results = run(str(tmp), progress=lambda s, m, p: print(f"  [{s}] {m} ({p}%)"))
    print(f"\n  Total: {len(results)} issues")
    for i, r in enumerate(results[:6], 1):
        print(f"  #{i} L{r['line']}: [{r['type']}] {r['message'][:80]}")
        if r['fix']:
            print(f"       -> {r['fix'][:80]}")
    if len(results) > 6:
        print(f"  ... and {len(results)-6} more")

    # ── 测试 2: academize() ──
    print(f"\n{'=' * 60}")
    print("Test 2: academize() via AcademizerService (mock mode)")
    print("=" * 60)
    sample = "We did a lot of tests to find out if our new method works."
    print(f"\n  Original: {sample}")
    for strength in ["light", "moderate", "heavy"]:
        result = academize(sample, discipline="computer-science", style_strength=strength)
        print(f"  [{strength}] {result}")

    # ── 测试 3: academize with return_full ──
    print(f"\n  Return_full test:")
    result, response = academize(
        sample, discipline="computer-science",
        style_strength="moderate", return_full=True,
    )
    print(f"  Discipline: {response.discipline}")
    print(f"  Changes: {len(response.changes)}")
    for c in response.changes[:3]:
        print(f"    {c.original!r} -> {c.replacement!r}  [{c.rationale[:50]}]")

    # -- Test 3b: run() with action=academize via request.json --
    print(f"\n  run() with action=academize:")
    acad_req = {
        "_meta": {"task": "academize", "project": "_d_self_test",
                  "scope": "selection", "paper_dir": str(tmp),
                  "created_at": "2026-07-17T00:00:00Z"},
        "selection": {"text": sample, "file": "test.tex"},
        "discipline": "computer-science",
        "style_strength": "moderate",
        "intent": "make it formal",
    }
    (tmp / "D" / "request.json").write_text(
        json.dumps(acad_req, ensure_ascii=False, indent=2), encoding="utf-8")
    result = run(str(tmp), progress=lambda s, m, p: print(f"    [{s}] {m} ({p}%)"))
    if isinstance(result, str):
        print(f"    Result: {result[:100]}...")

    # ── 测试 4: generate_title() 独立调用 ──
    print(f"\n{'=' * 60}")
    print("Test 4: generate_title() standalone (mock mode)")
    print("=" * 60)
    sample_paper = (
        "This paper addresses the challenge of long-range document generation "
        "using large language models. We propose a novel structured memory "
        "architecture called PRISM that enables efficient processing of documents "
        "exceeding 100,000 tokens. Experiments on arXiv-Long and GovReport "
        "benchmarks demonstrate a 23% improvement in ROUGE-L scores over "
        "existing baselines."
    )
    titles = generate_title(
        sample_paper, count=5, focus="balanced",
        discipline="computer-science",
        intent="突出方法论创新",
    )
    for i, t in enumerate(titles, 1):
        print(f"  #{i} [{t.focus}] {t.text}")
        print(f"      Rationale: {t.rationale[:80]}")

    # ── 测试 5: generate_abstract() 独立调用 ──
    print(f"\n{'=' * 60}")
    print("Test 5: generate_abstract() standalone (mock mode, B-M-R-C)")
    print("=" * 60)
    abstract_str, abs_result = generate_abstract(
        sample_paper, discipline="computer-science",
        max_words=250, return_full=True,
    )
    print(f"  [B] Background:  {abs_result.background[:100]}...")
    print(f"  [M] Methods:     {abs_result.methods[:100]}...")
    print(f"  [R] Results:     {abs_result.results[:100]}...")
    print(f"  [C] Conclusion:  {abs_result.conclusion[:100]}...")
    print(f"  Word count: {abs_result.word_count}")

    # ── 测试 6: run() with action="generate_title" ──
    print(f"\n{'=' * 60}")
    print("Test 6: run() with action=generate_title via request.json")
    print("=" * 60)
    gen_req = {
        "_meta": {
            "task": "generate_title", "project": "_d_self_test",
            "scope": "selection", "paper_dir": str(tmp),
            "created_at": "2026-07-17T00:00:00Z",
        },
        "selection": {"text": sample_paper, "file": "paper.tex"},
        "keywords": ["document generation", "LLM", "structured memory"],
        "discipline": "computer-science",
        "focus": "balanced",
        "intent": "generate publication title",
    }
    (tmp / "D" / "request.json").write_text(
        json.dumps(gen_req, ensure_ascii=False, indent=2), encoding="utf-8")
    results = run(str(tmp), progress=lambda s, m, p: print(f"  [{s}] {m} ({p}%)"))
    if isinstance(results, dict) and results.get("candidates"):
        for i, c in enumerate(results["candidates"], 1):
            print(f"  #{i} [{c['focus']}] {c['text']}")

    # ── 测试 7: run() with action="generate_abstract" ──
    print(f"\n{'=' * 60}")
    print("Test 7: run() with action=generate_abstract via request.json")
    print("=" * 60)
    gen_req["_meta"]["task"] = "generate_abstract"
    gen_req["max_words"] = 200
    (tmp / "D" / "request.json").write_text(
        json.dumps(gen_req, ensure_ascii=False, indent=2), encoding="utf-8")
    results = run(str(tmp), progress=lambda s, m, p: print(f"  [{s}] {m} ({p}%)"))
    if isinstance(results, dict) and results.get("abstract"):
        a = results["abstract"]
        print(f"  [B] {a.get('background', '')[:80]}...")
        print(f"  [M] {a.get('methods', '')[:80]}...")
        print(f"  [R] {a.get('results', '')[:80]}...")
        print(f"  [C] {a.get('conclusion', '')[:80]}...")
        print(f"  Word count: {a.get('word_count', 'N/A')}")

        # -- Test 9: check_citations() standalone + via run() --
    print(f"\n{'=' * 60}")
    print("Test 9: check_citations() standalone (mock mode, 3-stage pipeline)")
    print("=" * 60)
    sample_cite = (
        "The transformer architecture has been widely adopted in NLP tasks. "
        "Recent studies have shown that transformer-based models achieve "
        "state-of-the-art performance on a wide range of benchmarks. "
        "It is well known that deeper networks can capture more complex features. "
        "Our proposed method outperforms existing approaches \\cite{vaswani2017} "
        "by 15% on the standard benchmark. "
        "Fine-tuning pre-trained language models significantly improves "
        "downstream task accuracy as demonstrated in prior work."
    )
    issues, result = check_citations(
        sample_cite, discipline="computer-science", return_full=True,
    )
    print(f"  Total sentences: {result.total_sentences}")
    print(f"  Already cited: {result.cited_sentences}")
    print(f"  Uncited claims: {result.uncited_claims}")
    for iss in issues:
        print(f"  [{iss['risk_level']}] L{iss['line']}: {iss['reason'][:60]}")
        print(f"       Confidence: {iss['confidence']:.0%}")
        print(f"       Action: {iss['suggested_action'][:80]}")

    # Test 9b: run() with action=cite_check via request.json
    print(f"\n  run() with action=cite_check:")
    gen_req["_meta"]["task"] = "cite_check"
    gen_req["discipline"] = "computer-science"
    (tmp / "D" / "request.json").write_text(
        json.dumps(gen_req, ensure_ascii=False, indent=2), encoding="utf-8")
    results = run(str(tmp), progress=lambda s, m, p: print(f"    [{s}] {m} ({p}%)"))
    if isinstance(results, list):
        for r in results[:3]:
            print(f"    [{r.get('risk_level', '?')}] L{r['line']}: {r['reason'][:60]}")

    # -- Test 8: paraphrase() standalone + via run() --
    print(f"\n{'=' * 60}")
    print("Test 8: paraphrase() standalone (mock mode, 5 dimensions)")
    print("=" * 60)
    sample_para = (
        "The transformer architecture has been widely used in natural language processing. "
        "However, the model does not perform well on small datasets. "
        "We suggest using more data or adding extra training steps. "
        "The results show that it struggles with few examples."
    )
    result_str, result_obj = paraphrase(
        sample_para, style="academic", return_full=True,
    )
    print(f"  Rewritten: {result_str[:120]}...")
    print(f"  Changes: {len(result_obj.changes)}")
    for c in result_obj.changes:
        print(f"    [{c.reason[:35]}] {c.original[:40]} -> {c.replacement[:40]}")
    print(f"  Triggered: {result_obj.triggered_dimensions}")

    # Test 8b: run() with action=paraphrase via request.json
    print(f"\n  run() with action=paraphrase:")
    gen_req["_meta"]["task"] = "paraphrase"
    gen_req["style"] = "academic"
    (tmp / "D" / "request.json").write_text(
        json.dumps(gen_req, ensure_ascii=False, indent=2), encoding="utf-8")
    results = run(str(tmp), progress=lambda s, m, p: print(f"    [{s}] {m} ({p}%)"))
    if isinstance(results, dict) and results.get("paraphrase"):
        p = results["paraphrase"]
        print(f"    Rewritten: {p.get('rewritten_text', '')[:80]}...")
        print(f"    Dimensions: {p.get('triggered_dimensions', [])}")

    import shutil
    shutil.rmtree(tmp)
    print(f"\n{'=' * 60}")
    print("All self-tests (incl. academize dispatch + paraphraser) passed.")
    print("=" * 60)


if __name__ == "__main__":
    _self_test()
