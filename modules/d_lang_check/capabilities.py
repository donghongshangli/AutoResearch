"""
capabilities.py — All 6 D module capabilities, prompt-driven via DeepSeek.

Each capability is a standalone function:
  1. check_language    — Grammar, spelling, tense, style, logic checking
  2. academize_text    — Academic style transfer
  3. generate_titles   — 5 candidate titles with different focus angles
  4. generate_abstract — B-M-R-C structured abstract
  5. paraphrase_text   — 5-dimension paragraph rewriting
  6. check_citations   — Citation completeness audit (3-stage)

Pattern: text + options → DeepSeek LLM via llm_service → parse JSON → formatted result.
LaTeX protection via shared strip_latex()/restore_latex() from latex_protect.py.
"""

from __future__ import annotations

import re
import logging
from typing import Optional

from .llm_service import call_llm, parse_json_response, LLMServiceError
from .llm_prompts import (
    LANG_CHECK_SYSTEM, LANG_CHECK_USER,
    ACADEMIZE_SYSTEM, ACADEMIZE_USER,
    TITLE_SYSTEM, TITLE_USER,
    ABSTRACT_SYSTEM, ABSTRACT_USER,
    PARAPHRASE_SYSTEM, PARAPHRASE_USER,
    CITE_CHECK_SYSTEM, CITE_CHECK_USER,
)
from .latex_protect import strip_latex, restore_latex
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

logger = logging.getLogger("autoresearch.d_lang_check.capabilities")

# ═══════════════════════════════════════════════════════════════
# Valid options
# ═══════════════════════════════════════════════════════════════

VALID_DISCIPLINES = {
    "computer-science", "biology", "medicine", "physics",
    "chemistry", "engineering", "mathematics", "general",
}
VALID_STRENGTHS = {"light", "moderate", "heavy"}
VALID_TITLE_FOCUS = {"method", "conclusion", "question", "concise", "descriptive", "balanced"}
VALID_PARAPHRASE_STYLES = {"academic", "concise", "fluent", "balanced"}
RISK_LEVELS = {"high", "medium", "low"}

# ═══════════════════════════════════════════════════════════════
# 1. Language Check
# ═══════════════════════════════════════════════════════════════

def check_language(
    text: str,
    focus: Optional[list[str]] = None,
    intent: str = "",
) -> list[dict]:
    """Check academic text for language issues via DeepSeek.

    Args:
        text:   Academic text to check
        focus:  Check dimensions (grammar, spelling, tense, style, logic). Empty = all.
        intent: User supplementary intent

    Returns:
        list[dict] with {type, line, message, fix} for frontend rendering
    """
    if not text or not text.strip():
        return []

    dims = ", ".join(focus) if focus else "grammar, spelling, tense, style, logic, punctuation"
    user_prompt = LANG_CHECK_USER.format(
        text=text, focus=dims, intent=intent or "thorough academic language check"
    )

    logger.info("Language check: %d chars, focus=%s", len(text), dims)
    raw = call_llm(LANG_CHECK_SYSTEM, user_prompt, temperature=0.1, json_mode=False)
    logger.info("LLM raw response (%d chars): %s", len(raw), raw[:300])
    data = parse_json_response(raw)
    logger.info("LLM parsed: type=%s, keys=%s",
                type(data).__name__,
                list(data.keys())[:10] if isinstance(data, dict) else "N/A")

    # Prompt asks for {"issues": [...]}, but handle edge cases robustly
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("issues", data.get("suggestions", []))
        if not items:
            logger.warning("Empty issues from LLM — keys present: %s, raw[:200]: %s",
                           list(data.keys()) if isinstance(data, dict) else "N/A",
                           raw[:200])
    else:
        logger.warning("Unexpected LLM response type: %s, raw[:200]: %s", type(data).__name__, raw[:200])
        items = []

    logger.info("Extracted %d issues from LLM response", len(items))

    results = []
    for item in items:
        sug = Suggestion(
            start=int(item.get("start", 0)),
            end=int(item.get("end", 0)),
            original=item.get("original", ""),
            replacement=item.get("fix", item.get("replacement", "")),
            type=item.get("type", "style"),
            reason=item.get("message", item.get("reason", "")),
            confidence=float(item.get("confidence", 0.5)),
        )
        cr = suggestion_to_check_result(sug, text, source="deepseek")
        results.append(cr)

    return check_results_to_frontend(results)


# ═══════════════════════════════════════════════════════════════
# 2. Academic Style Transfer (Academizer)
# ═══════════════════════════════════════════════════════════════

def academize_text(
    text: str,
    discipline: str = "general",
    style_strength: str = "moderate",
    return_full: bool = False,
) -> str | tuple[str, AcademizerResponse]:
    """Convert informal text to formal academic writing style via DeepSeek.

    Args:
        text:           Text to convert
        discipline:     Field: computer-science, biology, medicine, physics, general
        style_strength: light | moderate | heavy
        return_full:    If True, return (text, AcademizerResponse) with changes list

    Returns:
        str or (str, AcademizerResponse)
    """
    if discipline not in VALID_DISCIPLINES:
        raise ValueError(f"Invalid discipline: '{discipline}'. Valid: {sorted(VALID_DISCIPLINES)}")
    if style_strength not in VALID_STRENGTHS:
        raise ValueError(f"Invalid strength: '{style_strength}'. Valid: {sorted(VALID_STRENGTHS)}")
    if not text or not text.strip():
        if return_full:
            return text, AcademizerResponse(academized_text=text, discipline=discipline,
                                            style_strength=style_strength)
        return text

    # LaTeX protection: strip → LLM → restore
    protected_text, latex_map = strip_latex(text)

    user_prompt = ACADEMIZE_USER.format(
        text=protected_text, discipline=discipline, style_strength=style_strength
    )
    logger.info("Academize: %d chars, discipline=%s, strength=%s", len(text), discipline, style_strength)
    raw = call_llm(ACADEMIZE_SYSTEM, user_prompt, temperature=0.3, json_mode=True)
    data = parse_json_response(raw)

    academized = restore_latex(data.get("academized_text", text), latex_map)

    changes = [
        AcademizerChange(
            original=c.get("original", ""),
            replacement=c.get("replacement", ""),
            rationale=c.get("rationale", ""),
        )
        for c in data.get("changes", [])
    ]

    response = AcademizerResponse(
        academized_text=academized,
        changes=changes,
        discipline=discipline,
        style_strength=style_strength,
    )

    if return_full:
        return academized, response
    return academized


# ═══════════════════════════════════════════════════════════════
# 3. Title Generation
# ═══════════════════════════════════════════════════════════════

def generate_titles(
    text: str,
    count: int = 5,
    focus: str = "balanced",
    discipline: str = "general",
    intent: str = "",
) -> list[TitleCandidate]:
    """Generate candidate paper titles via DeepSeek.

    Args:
        text:       Paper content
        count:      Number of candidates (default 5)
        focus:      balanced | method | conclusion | question | concise | descriptive
        discipline: Field
        intent:     User supplementary intent

    Returns:
        list[TitleCandidate]
    """
    if focus not in VALID_TITLE_FOCUS:
        raise ValueError(f"Invalid focus: '{focus}'. Valid: {sorted(VALID_TITLE_FOCUS)}")
    if not text or not text.strip():
        return []

    protected_text, latex_map = strip_latex(text)

    user_prompt = TITLE_USER.format(
        text=protected_text, discipline=discipline, intent=intent or "generate publication-ready titles"
    )
    logger.info("Title generation: %d chars, focus=%s, count=%d", len(text), focus, count)
    raw = call_llm(TITLE_SYSTEM, user_prompt, temperature=0.5, json_mode=True)
    data = parse_json_response(raw)

    candidates = []
    for c in data.get("candidates", [])[:count]:
        title_text = restore_latex(c.get("title", ""), latex_map)
        candidates.append(TitleCandidate(
            text=title_text,
            focus=c.get("focus", "balanced"),
            rationale=c.get("rationale", ""),
        ))
    return candidates


# ═══════════════════════════════════════════════════════════════
# 4. Abstract Generation (B-M-R-C)
# ═══════════════════════════════════════════════════════════════

def generate_abstract(
    text: str,
    discipline: str = "general",
    max_words: int = 250,
    intent: str = "",
    return_full: bool = False,
) -> str | tuple[str, AbstractResult]:
    """Generate B-M-R-C structured abstract via DeepSeek.

    B (Background) → M (Methods) → R (Results) → C (Conclusion)

    Args:
        text:       Paper content
        discipline: Field
        max_words:  Target word count
        intent:     User supplementary intent
        return_full: If True, return (abstract_str, AbstractResult)

    Returns:
        str or (str, AbstractResult)
    """
    if not text or not text.strip():
        if return_full:
            return "", AbstractResult()
        return ""

    protected_text, latex_map = strip_latex(text)

    user_prompt = ABSTRACT_USER.format(
        text=protected_text, max_words=max_words, discipline=discipline,
        intent=intent or "generate a structured abstract"
    )
    logger.info("Abstract generation: %d chars, max_words=%d", len(text), max_words)
    raw = call_llm(ABSTRACT_SYSTEM, user_prompt, temperature=0.3, json_mode=True)
    data = parse_json_response(raw)

    def _clean(s):
        return restore_latex(s, latex_map)

    full = _clean(data.get("full_abstract", ""))
    # Truncate to max_words
    words = full.split()
    if len(words) > max_words:
        full = " ".join(words[:max_words])

    result = AbstractResult(
        abstract=full,
        background=_clean(data.get("background", "")),
        methods=_clean(data.get("methods", "")),
        results=_clean(data.get("results", "")),
        conclusion=_clean(data.get("conclusion", "")),
        word_count=len(full.split()) if full else 0,
    )

    if return_full:
        return result.abstract, result
    return result.abstract


# ═══════════════════════════════════════════════════════════════
# 5. Paragraph Rewriting (Paraphraser)
# ═══════════════════════════════════════════════════════════════

def paraphrase_text(
    text: str,
    style: str = "academic",
    preserve_keywords: Optional[list[str]] = None,
    intent: str = "",
    return_full: bool = False,
) -> str | tuple[str, ParaphraseResult]:
    """Rewrite a paragraph for academic clarity via DeepSeek.

    5 dimensions: sentence_order, coherence, redundancy, topic_sentence, long_sentence.
    Constraint: process ONE paragraph at a time.

    Args:
        text:              Paragraph to rewrite
        style:             academic | concise | fluent | balanced
        preserve_keywords: Keywords to keep unchanged
        intent:            User supplementary intent
        return_full:       If True, return (rewritten_text, ParaphraseResult)

    Returns:
        str or (str, ParaphraseResult)
    """
    if style not in VALID_PARAPHRASE_STYLES:
        raise ValueError(f"Invalid style: '{style}'. Valid: {sorted(VALID_PARAPHRASE_STYLES)}")
    if not text or not text.strip():
        if return_full:
            return "", ParaphraseResult()
        return ""

    protected_text, latex_map = strip_latex(text)

    user_prompt = PARAPHRASE_USER.format(
        text=protected_text, style=style,
        keywords=", ".join(preserve_keywords) if preserve_keywords else "none",
        intent=intent or "improve academic clarity"
    )
    logger.info("Paraphrase: %d chars, style=%s", len(text), style)
    raw = call_llm(PARAPHRASE_SYSTEM, user_prompt, temperature=0.4, json_mode=True)
    data = parse_json_response(raw)

    rewritten = restore_latex(data.get("rewritten_text", ""), latex_map)

    changes = []
    for c in data.get("changes", []):
        changes.append(ParaphraseChange(
            original=restore_latex(c.get("original", ""), latex_map),
            replacement=restore_latex(c.get("replacement", ""), latex_map),
            reason=c.get("reason", ""),
        ))

    result = ParaphraseResult(
        rewritten_text=rewritten,
        changes=changes,
        triggered_dimensions=data.get("triggered_dimensions", []),
    )

    if return_full:
        return rewritten, result
    return rewritten


# ═══════════════════════════════════════════════════════════════
# 6. Citation Check (3-stage pipeline)
# ═══════════════════════════════════════════════════════════════

# Regex engine for citation markers (Stage 2 filter)
_LATEX_CITE_RE = re.compile(
    r'\\(?:cite|citet|citep|citealt|citealp|citeauthor|citeyear|nocite)'
    r'\s*(?:\[[^\]]*\])?\s*\{[^}]*\}',
)
_BRACKET_CITE_RE = re.compile(r'\[\d+(?:[,;-]\d+)*\]')
_AUTHOR_YEAR_RE = re.compile(r'\([A-Z][a-z]+(?:\s+et\s+al\.)?(?:,\s*\d{4}[a-z]?)\)')
_SUPERSCRIPT_CITE_RE = re.compile(r'[¹²³⁴⁵⁶⁷⁸⁹⁰]+')
_DOI_RE = re.compile(r'\b(10\.\d{4,}/[^\s]+)\b')


def check_citations(
    text: str,
    discipline: str = "general",
    intent: str = "",
    return_full: bool = False,
) -> list[dict] | tuple[list[dict], CiteCheckResult]:
    """Citation completeness audit via DeepSeek (3-stage pipeline).

    Stage 1: DeepSeek identifies claims needing citations (high recall).
    Stage 2: Regex filters out sentences that already have citation markers.
    Stage 3: CrossRef (DOI) + Semantic Scholar for literature recommendations.

    Args:
        text:       Academic text to audit
        discipline: Field (affects common-knowledge thresholds)
        intent:     User supplementary intent
        return_full: If True, return (issues_list, CiteCheckResult)

    Returns:
        list[dict] or (list[dict], CiteCheckResult)
    """
    if discipline not in VALID_DISCIPLINES:
        raise ValueError(f"Invalid discipline: '{discipline}'. Valid: {sorted(VALID_DISCIPLINES)}")
    if not text or not text.strip():
        if return_full:
            return [], CiteCheckResult()
        return []

    # LaTeX protection
    protected_text, latex_map = strip_latex(text)

    # Stage 0: DOI extraction + CrossRef verification
    dois = _DOI_RE.findall(protected_text)
    verified_refs = {}
    for doi in dois[:10]:
        info = _verify_doi_crossref(doi)
        if info:
            verified_refs[doi] = info

    # Stage 1: DeepSeek claim identification
    user_prompt = CITE_CHECK_USER.format(
        text=protected_text, discipline=discipline,
        intent=intent or "thorough citation audit"
    )
    logger.info("Citation check: %d chars, discipline=%s", len(text), discipline)
    raw = call_llm(CITE_CHECK_SYSTEM, user_prompt, temperature=0.2, json_mode=True)
    data = parse_json_response(raw)

    # Stage 2: Regex filter — skip sentences already containing citations
    claims = []
    total_sentences = max(1, len(re.split(r'[.!?]\s+', protected_text)))
    cited_count = 0

    for item in data.get("claims", []):
        raw_sentence = item.get("sentence", "")
        sentence = restore_latex(raw_sentence, latex_map)

        if _has_citation_marker(sentence):
            cited_count += 1
            continue  # Already cited, skip

        claims.append(CitationIssue(
            sentence=sentence,
            line=item.get("line", 1),
            reason=item.get("reason", ""),
            risk_level=item.get("risk_level", "medium"),
            confidence=float(item.get("confidence", 0.5)),
            suggested_action=item.get("suggested_action", ""),
            recommended_citations=_search_semantic_scholar(sentence),
        ))

    result = CiteCheckResult(
        issues=claims,
        total_sentences=total_sentences,
        cited_sentences=cited_count,
        uncited_claims=len(claims),
    )

    issues = cite_check_to_frontend(result)

    if return_full:
        return issues, result
    return issues


# ═══════════════════════════════════════════════════════════════
# Citation helpers: Regex + CrossRef + Semantic Scholar
# ═══════════════════════════════════════════════════════════════

def _has_citation_marker(sentence: str) -> bool:
    """Check if a sentence already contains citation markers."""
    return bool(
        _LATEX_CITE_RE.search(sentence)
        or _BRACKET_CITE_RE.search(sentence)
        or _AUTHOR_YEAR_RE.search(sentence)
        or _SUPERSCRIPT_CITE_RE.search(sentence)
    )


def _verify_doi_crossref(doi: str) -> Optional[dict]:
    """Verify DOI via CrossRef API (free, no API key required)."""
    import httpx
    try:
        r = httpx.get(f'https://api.crossref.org/works/{doi}', timeout=15)
        r.raise_for_status()
        msg = r.json().get('message', {})
        return {
            'title': (msg.get('title', [''])[0] if msg.get('title') else '').strip(),
            'authors': [
                f"{a.get('given', '')} {a.get('family', '')}".strip()
                for a in msg.get('author', [])[:3]
            ],
            'year': msg.get('created', {}).get('date-parts', [[0]])[0][0],
            'doi': doi,
        }
    except Exception as e:
        logger.debug(f"CrossRef lookup failed for {doi}: {e}")
        return None


def _search_semantic_scholar(sentence: str, top_k: int = 5) -> list[str]:
    """Search Semantic Scholar for related papers (free API, rate-limited)."""
    import time as _t
    import httpx
    _t.sleep(1.1)  # Rate limit: ~1 req/s

    query = ' '.join(sentence.split()[:20])
    for attempt in range(3):
        try:
            r = httpx.get(
                'https://api.semanticscholar.org/graph/v1/paper/search',
                params={'query': query, 'limit': top_k, 'fields': 'title,year'},
                timeout=15,
            )
            if r.status_code == 429:
                _t.sleep(3)
                continue
            r.raise_for_status()
            papers = r.json().get('data', [])
            return [
                f"{p.get('title', '')} ({p.get('year', '')})"
                if p.get('year') else p.get('title', '')
                for p in papers
            ]
        except Exception as e:
            if attempt < 2:
                _t.sleep(3)
            else:
                logger.debug(f"Semantic Scholar search failed: {e}")
    return []
