"""
D Module — Academic Language Toolbox (v1.0.0)

Prompt-driven academic writing tools powered by DeepSeek LLM.
All 6 capabilities share a unified architecture:
  text + options → DeepSeek (via llm_service) → JSON parsing → formatted result

Capabilities:
  1. lang_check         — Grammar, spelling, tense, style, logic checking
  2. academize          — Academic style transfer (informal → formal)
  3. generate_title     — 5 candidate titles (method/conclusion/question/concise/descriptive)
  4. generate_abstract  — B-M-R-C structured abstract generation
  5. paraphrase         — 5-dimension paragraph rewriting
  6. cite_check         — Citation completeness audit (3-stage pipeline)

Entry point:
  run(paper_dir, progress) → reads D/request.json → dispatches action → returns result

Architecture:
  __init__.py       ← Entry + dispatch + public API exports
  models.py         ← Dataclasses + frontend format converters
  capabilities.py   ← All 6 capability implementations
  llm_service.py    ← DeepSeek LLM client (call + JSON parse)
  llm_prompts.py    ← Academic prompt templates (system + user)
  latex_protect.py  ← LaTeX command protection (strip/restore + line filter)

Configuration:
  DEEPSEEK_API_KEY  — Required. DeepSeek API key for all capabilities.
  BACKUP_LLM_MODEL  — Optional. Override model name (default: deepseek-v4-pro).

progress callback signature: progress(stage: str, message: str, percent: int) → None
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable, Optional

# ═══════════════════════════════════════════════════════════════
# Public API — re-export capability functions
# ═══════════════════════════════════════════════════════════════

from .capabilities import (
    check_language,
    academize_text as academize,
    generate_titles as generate_title,
    generate_abstract,
    paraphrase_text as paraphrase,
    check_citations,
    VALID_DISCIPLINES, VALID_STRENGTHS, VALID_TITLE_FOCUS,
    VALID_PARAPHRASE_STYLES, RISK_LEVELS,
)

# Re-export models and converters
from .models import (
    Suggestion, LanguageFeedbackResponse, CheckResult,
    AcademizerResponse, AcademizerChange,
    TitleCandidate, AbstractResult,
    ParaphraseChange, ParaphraseResult,
    CitationIssue, CiteCheckResult,
    suggestion_to_check_result, check_results_to_frontend,
    title_candidates_to_frontend, abstract_result_to_frontend,
    paraphrase_result_to_frontend, cite_check_to_frontend,
)

# Re-export LaTeX protector
from .latex_protect import strip_latex, restore_latex, filter_results as filter_latex_results

logger = logging.getLogger("autoresearch.d_lang_check")

# ═══════════════════════════════════════════════════════════════
# Module metadata
# ═══════════════════════════════════════════════════════════════

__module_meta__ = {
    "name": "D Module — Academic Language Toolbox",
    "version": "1.0.0",
    "description": "Prompt-driven academic writing tools (lang_check, academize, generate_title, generate_abstract, paraphrase, cite_check) powered by DeepSeek LLM",
    "architecture": "Unified: request → dispatch → DeepSeek prompt → JSON parse → frontend format",
    "capabilities": {
        "lang_check": "Grammar, spelling, tense, style, logic checking → list[dict]",
        "academize": "Academic style transfer → str",
        "generate_title": "5 candidate titles → dict",
        "generate_abstract": "B-M-R-C abstract → dict",
        "paraphrase": "5-dimension paragraph rewrite → dict",
        "cite_check": "Citation completeness audit → list[dict]",
    },
    "dependencies": {
        "python_packages": ["httpx"],
        "api": "DeepSeek API (chat/completions)",
        "api_keys": ["DEEPSEEK_API_KEY"],
    },
}


# ═══════════════════════════════════════════════════════════════
# Entry: run()
# ═══════════════════════════════════════════════════════════════

# Action → handler mapping
_ACTION_HANDLERS = {
    "lang_check": "_run_lang_check",
    "academize": "_run_academize",
    "generate_title": "_run_generate_title",
    "generate_abstract": "_run_generate_abstract",
    "paraphrase": "_run_paraphrase",
    "cite_check": "_run_cite_check",
}


def run(
    paper_dir: str,
    progress: Optional[Callable] = None,
) -> list[dict] | dict | str:
    """Execute a D module task. Reads D/request.json and dispatches by action.

    Actions:
      lang_check          → list[dict]   Language issues [{type, line, message, fix}, ...]
      academize           → str          Academic-style text
      generate_title      → dict         {"status":"ok", "candidates":[...]}
      generate_abstract   → dict         {"status":"ok", "abstract":{...}}
      paraphrase          → dict         {"status":"ok", "paraphrase":{...}}
      cite_check          → list[dict]   Citation issues

    Args:
        paper_dir: Paper project directory (tasks/{paper}/)
        progress:  Optional progress callback progress(stage, message, percent)
    """
    proj_dir = Path(paper_dir)

    def _p(stage: str, msg: str, pct: int) -> None:
        if progress:
            progress(stage, msg, pct)

    # 1. Load request
    _p("init", "正在读取任务配置...", 5)
    req = _load_request(proj_dir)
    if req is None:
        _p("error", "D/request.json 未找到", 0)
        return [{"type": "style", "line": 1,
                 "message": "请求文件 (D/request.json) 未找到。请从前端提交任务。",
                 "fix": ""}]

    # 2. Resolve action
    action = req.get("action") or req.get("_meta", {}).get("task") or "lang_check"
    logger.info("D module dispatch: action=%s project=%s",
                action, req.get("_meta", {}).get("project", "?"))

    # 3. Dispatch
    handler_name = _ACTION_HANDLERS.get(action)
    if handler_name is None:
        _p("error", f"未知操作: {action}", 0)
        supported = ", ".join(_ACTION_HANDLERS.keys())
        return [{"type": "style", "line": 1,
                 "message": f"未知操作: '{action}'。支持的操作: {supported}",
                 "fix": ""}]

    handler = globals()[handler_name]
    return handler(req, proj_dir, _p)


# ═══════════════════════════════════════════════════════════════
# Action handlers — each reads request → calls capability → returns result
# ═══════════════════════════════════════════════════════════════

def _run_lang_check(req: dict, proj_dir: Path, _p: Callable) -> list[dict]:
    """Language check: grammar, spelling, tense, style, logic."""
    text, focus, intent, scope = _parse_check_request(req, proj_dir)

    if not text or not text.strip():
        _p("complete", "无文本可检查 — 跳过", 100)
        return []

    _p("init", f"范围: {scope} · {len(text)} 字符 · "
               f"重点: {', '.join(focus) if focus else '全部'}", 10)

    _p("checking", "正在调用 DeepSeek 语言检查...", 25)
    results = check_language(text, focus=focus, intent=intent)

    # Filter LaTeX protected regions
    _p("filtering", "正在过滤 LaTeX 保护区域...", 80)
    from .latex_protect import filter_results
    # Convert dicts back to CheckResult for filtering
    check_results = [
        CheckResult(type=r["type"], line=r["line"], message=r["message"], fix=r["fix"])
        for r in results
    ]
    filtered = filter_results(check_results, text)
    output = check_results_to_frontend(filtered)
    removed = len(results) - len(output)

    if removed > 0:
        _p("filtering", f"已过滤 {removed} 个 LaTeX 区域误报", 85)

    type_counts: dict[str, int] = {}
    for r in output:
        t = r.get("type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1
    summary = " · ".join(f"{t}: {c}" for t, c in sorted(type_counts.items()))
    _p("complete", f"检查完成 — {summary}" if summary else "检查完成 — 未发现问题", 100)

    return output


def _run_academize(req: dict, proj_dir: Path, _p: Callable) -> dict | str:
    """Academic style transfer."""
    text = _get_text(req, proj_dir)
    if not text or not text.strip():
        _p("error", "无可用文本", 0)
        return {"status": "error", "message": "无可用文本。"}

    discipline = req.get("discipline", "general")
    strength = req.get("style_strength", "moderate")

    _p("transforming", f"学术化: {len(text)} 字符 · {discipline} · {strength}", 30)
    try:
        result = academize(text, discipline=discipline, style_strength=strength)
    except Exception as e:
        logger.error(f"Academize failed: {e}")
        _p("error", str(e), 0)
        return {"status": "error", "message": str(e)}

    _p("complete", f"学术化完成 — {len(result)} 字符", 100)
    return result


def _run_generate_title(req: dict, proj_dir: Path, _p: Callable) -> dict:
    """Title generation: 5 candidate titles."""
    text = _get_text(req, proj_dir)
    if not text or not text.strip():
        _p("error", "无可用文本", 0)
        return {"status": "error", "message": "无可用文本。", "candidates": []}

    count = req.get("count", 5)
    focus = req.get("focus", "balanced")
    discipline = req.get("discipline", "general")
    intent = req.get("intent", "")

    _p("generating", f"正在生成 {count} 个标题: {len(text)} 字符", 30)
    try:
        titles = generate_title(text, count=count, focus=focus,
                                discipline=discipline, intent=intent)
    except Exception as e:
        logger.error(f"Title generation failed: {e}")
        _p("error", str(e), 0)
        return {"status": "error", "message": str(e), "candidates": []}

    output = title_candidates_to_frontend(titles)
    _p("complete", f"已生成 {len(output)} 个候选标题", 100)
    return {"status": "ok", "candidates": output}


def _run_generate_abstract(req: dict, proj_dir: Path, _p: Callable) -> dict:
    """Abstract generation: B-M-R-C structured."""
    text = _get_text(req, proj_dir)
    if not text or not text.strip():
        _p("error", "无可用文本", 0)
        return {"status": "error", "message": "无可用文本。", "abstract": None}

    discipline = req.get("discipline", "general")
    max_words = req.get("max_words", 250)
    intent = req.get("intent", "")

    _p("generating", f"正在生成 B-M-R-C 摘要: {len(text)} 字符, ~{max_words} 词", 30)
    try:
        abstract_str, result_obj = generate_abstract(
            text, discipline=discipline, max_words=max_words,
            intent=intent, return_full=True,
        )
    except Exception as e:
        logger.error(f"Abstract generation failed: {e}")
        _p("error", str(e), 0)
        return {"status": "error", "message": str(e), "abstract": None}

    output = abstract_result_to_frontend(result_obj)
    _p("complete", f"摘要完成 — {result_obj.word_count} 词", 100)
    return {"status": "ok", "abstract": output}


def _run_paraphrase(req: dict, proj_dir: Path, _p: Callable) -> dict:
    """Paragraph rewriting."""
    text = _get_text(req, proj_dir)
    if not text or not text.strip():
        _p("error", "无可用文本", 0)
        return {"status": "error", "message": "无可用文本。", "paraphrase": None}

    style = req.get("style", "academic")
    preserve_keywords = req.get("preserve_keywords", [])
    intent = req.get("intent", "")

    _p("rewriting", f"正在改写: {len(text)} 字符 · 风格={style}", 30)
    try:
        rewritten, result_obj = paraphrase(
            text, style=style, preserve_keywords=preserve_keywords,
            intent=intent, return_full=True,
        )
    except Exception as e:
        logger.error(f"Paraphrase failed: {e}")
        _p("error", str(e), 0)
        return {"status": "error", "message": str(e), "paraphrase": None}

    output = paraphrase_result_to_frontend(result_obj)
    dims = result_obj.triggered_dimensions
    _p("complete", f"改写完成 — {len(dims)} 维度: {', '.join(dims)}", 100)
    return {"status": "ok", "paraphrase": output}


def _run_cite_check(req: dict, proj_dir: Path, _p: Callable) -> list[dict]:
    """Citation completeness check."""
    text = _get_text(req, proj_dir)
    if not text or not text.strip():
        _p("error", "无可用文本", 0)
        return [{"type": "cite_check", "line": 1,
                 "message": "无可用文本进行引用检查。", "fix": ""}]

    discipline = req.get("discipline", "general")
    intent = req.get("intent", "")

    _p("checking", f"引用检查: {len(text)} 字符 · {discipline}", 10)
    _p("checking", "阶段 1: 通过 DeepSeek 识别论断...", 25)
    _p("filtering", "阶段 2: 过滤已引用句子...", 50)
    _p("recommending", "阶段 3: 搜索 Semantic Scholar...", 75)

    try:
        issues, result = check_citations(
            text, discipline=discipline, intent=intent, return_full=True,
        )
    except Exception as e:
        logger.error(f"Citation check failed: {e}")
        _p("error", str(e), 0)
        return [{"type": "cite_check", "line": 1,
                 "message": f"引用检查失败: {e}", "fix": ""}]

    _p("complete", f"已检查 {result.total_sentences} 句 · "
               f"{result.uncited_claims} 未引用 · {result.cited_sentences} 已引用", 100)
    return issues


# ═══════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════

def _load_request(proj_dir: Path) -> Optional[dict]:
    """Load D/request.json from paper directory."""
    req_path = proj_dir / "D" / "request.json"
    if not req_path.exists():
        return None
    try:
        return json.loads(req_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, Exception) as e:
        logger.warning("Failed to parse request.json: %s", e)
        return None


def _get_text(req: dict, proj_dir: Path) -> str:
    """Extract text from request (selection > full_text > read files)."""
    # Priority 1: selection.text
    text = req.get("selection", {}).get("text", "")
    if text.strip():
        return text
    # Priority 2: full_text field
    text = req.get("full_text", "")
    if text.strip():
        return text
    # Priority 3: read from project files
    return _read_full_text(proj_dir)


def _parse_check_request(req: dict, proj_dir: Path) -> tuple[str, list[str], str, str]:
    """Parse request for lang_check: (text, focus, intent, scope)."""
    scope = req.get("_meta", {}).get("scope", "selection")
    text = _get_text(req, proj_dir) if scope == "selection" else _read_full_text(proj_dir)
    focus = req.get("focus", [])
    intent = req.get("intent", "")
    return text, focus, intent, scope


def _read_full_text(proj_dir: Path) -> str:
    """Read and merge the entire paper project for full-text mode."""
    # Try merge_svc first
    try:
        from server.services.merge_svc import merge_project
        merged = merge_project(proj_dir)
        text = merged.get("merged_text", "")
        if text:
            return text
    except Exception:
        pass

    # Fallback: read main.tex
    main = proj_dir / "main.tex"
    if main.exists():
        return main.read_text(encoding="utf-8", errors="replace")

    # Last resort: any .tex file
    for tex_file in proj_dir.rglob("*.tex"):
        try:
            return tex_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
    return ""


# ═══════════════════════════════════════════════════════════════
# Self-test
# ═══════════════════════════════════════════════════════════════

def _self_test():
    """Quick self-test: exercises run() with all 6 actions.

    Usage:
        python -c "import sys; sys.path.insert(0, '.');
        from modules.d_lang_check import _self_test; _self_test()"
    """
    import tempfile
    import shutil

    tmp = Path(tempfile.gettempdir()) / "_d_self_test"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(exist_ok=True)
    (tmp / "D").mkdir(exist_ok=True)

    test_text = (
        "The transformer architecture has been widely used in natural language processing. "
        "We use a lot of data to train our model. The results shows that our method is very good. "
        "However, the model don't perform well on small datasets. "
        "As shown in Figure \\ref{fig:arch}, our system recieve input from multiple sources. "
        "We find out that the performance is heavily dependant on the quality of the data. "
        "Its important to note that this finding is independant of the model architecture."
    )

    def progress(stage, msg, pct):
        print(f"  [{stage}] {msg} ({pct}%)")

    results_summary = []

    # Test each action
    for action in ["lang_check", "academize", "generate_title", "generate_abstract", "paraphrase", "cite_check"]:
        print(f"\n{'='*60}")
        print(f"Test: run() with action={action}")
        print(f"{'='*60}")

        req = {
            "_meta": {"task": action, "project": "_d_self_test", "scope": "selection",
                       "paper_dir": str(tmp), "created_at": "2026-07-26T00:00:00Z"},
            "selection": {"text": test_text, "file": "test.tex",
                           "section_title": "Test", "start_line": 1, "end_line": 10},
            "context": "", "focus": ["grammar", "spelling"], "intent": "test",
            "discipline": "computer-science", "style_strength": "moderate",
            "style": "academic", "max_words": 150, "count": 5,
        }
        (tmp / "D" / "request.json").write_text(
            json.dumps(req, ensure_ascii=False, indent=2), encoding="utf-8")

        try:
            result = run(str(tmp), progress=progress)
            if isinstance(result, list):
                print(f"  Result: {len(result)} items")
                for r in result[:3]:
                    print(f"    L{r.get('line','?')}: [{r.get('type','?')}] {str(r.get('message',''))[:60]}")
            elif isinstance(result, dict):
                status = result.get("status", "?")
                keys = [k for k in result if k != "status"]
                print(f"  Status: {status}, keys: {keys}")
                if result.get("candidates"):
                    for c in result["candidates"][:2]:
                        print(f"    [{c.get('focus','?')}] {c.get('text','')[:60]}")
                if result.get("abstract"):
                    a = result["abstract"]
                    print(f"    Word count: {a.get('word_count','?')}")
            elif isinstance(result, str):
                print(f"  Result: {len(result)} chars — {result[:80]}...")
            results_summary.append(f"  ✅ {action}: OK")
        except Exception as e:
            print(f"  ❌ {action}: FAILED — {e}")
            results_summary.append(f"  ❌ {action}: {e}")

    print(f"\n{'='*60}")
    print("Self-test summary:")
    for s in results_summary:
        print(s)
    print(f"{'='*60}")

    shutil.rmtree(tmp)


if __name__ == "__main__":
    _self_test()
