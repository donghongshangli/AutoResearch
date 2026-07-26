"""
models.py — Data models and frontend format converters for all 6 D module capabilities.

Data flow:
  Backend API (DeepSeek JSON) → Dataclass → Frontend Converter → dict (JSON serializable)

Frontend contract (index.html:1128-1133):
  Each issue: {type, line, message, fix}
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ═══════════════════════════════════════════════════════════════
# Language Check Models
# ═══════════════════════════════════════════════════════════════

@dataclass
class Suggestion:
    """A single language issue found by the checker."""
    start: int
    """Character offset start (0-based, inclusive)"""
    end: int
    """Character offset end (0-based, exclusive)"""
    original: str
    """Original text fragment"""
    replacement: str
    """Suggested replacement"""
    type: str
    """Issue type: grammar | spelling | tense | style | punctuation"""
    reason: str
    """Explanation of the issue"""
    confidence: float = 1.0
    """Confidence score (0.0-1.0)"""


@dataclass
class LanguageFeedbackResponse:
    """Complete language check response."""
    suggestions: list[Suggestion] = field(default_factory=list)
    quality_score: float = 0.0
    """Overall language quality (0.0-1.0)"""
    word_count: int = 0
    model_version: str = ""


# ═══════════════════════════════════════════════════════════════
# Internal DTO — Frontend Contract
# ═══════════════════════════════════════════════════════════════

@dataclass
class CheckResult:
    """Single check result in frontend format.

    Frontend renders: L{line}: {message} → {fix}  (index.html:1128-1133)
    """
    type: str
    """Check dimension: grammar | spelling | tense | logic | style"""
    line: int
    """Line number (1-based)"""
    message: str
    """Issue description"""
    fix: str = ""
    """Suggested correction"""
    severity: str = "warning"
    """error | warning | info"""
    rule_id: str = ""
    """Source identifier"""


# ═══════════════════════════════════════════════════════════════
# Academic Style Transfer Models
# ═══════════════════════════════════════════════════════════════

@dataclass
class AcademizerChange:
    """A single change made during style transfer."""
    original: str
    replacement: str
    rationale: str = ""


@dataclass
class AcademizerResponse:
    """Complete style transfer response."""
    academized_text: str
    changes: list[AcademizerChange] = field(default_factory=list)
    discipline: str = "general"
    style_strength: str = "moderate"


# ═══════════════════════════════════════════════════════════════
# Title & Abstract Generation Models
# ═══════════════════════════════════════════════════════════════

@dataclass
class TitleCandidate:
    """A single candidate title with its focus angle.

    Focus types:
      method      — Emphasizes technical innovation
      conclusion  — Leads with the main finding
      question    — Engaging research question format
      concise     — Shortest direct expression
      descriptive — Comprehensive scope coverage
    """
    text: str
    focus: str
    """method | conclusion | question | concise | descriptive"""
    rationale: str = ""


@dataclass
class AbstractResult:
    """B-M-R-C structured abstract.

    B (Background) → M (Methods) → R (Results) → C (Conclusion)
    """
    abstract: str = ""
    """Full abstract text (B+M+R+C combined)"""
    background: str = ""
    methods: str = ""
    results: str = ""
    conclusion: str = ""
    word_count: int = 0


# ═══════════════════════════════════════════════════════════════
# Paragraph Rewriting Models
# ═══════════════════════════════════════════════════════════════

@dataclass
class ParaphraseChange:
    """A single change in the rewritten paragraph."""
    original: str
    replacement: str
    reason: str = ""


@dataclass
class ParaphraseResult:
    """Complete paragraph rewrite result.

    Five optimization dimensions:
      1. sentence_order  — Logical flow reordering
      2. coherence       — Connective and transition additions
      3. redundancy      — Duplicate content removal
      4. topic_sentence  — Opening sentence strengthening
      5. long_sentence   — Complex sentence splitting
    """
    rewritten_text: str = ""
    changes: list[ParaphraseChange] = field(default_factory=list)
    triggered_dimensions: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════
# Citation Check Models
# ═══════════════════════════════════════════════════════════════

@dataclass
class CitationIssue:
    """A single citation completeness issue.

    Three-stage audit pipeline:
      1. LLM claim identification (high recall)
      2. Regex citation-marker filter
      3. Semantic Scholar literature recommendation
    """
    sentence: str
    line: int
    reason: str
    risk_level: str = "medium"
    """high | medium | low"""
    confidence: float = 0.0
    suggested_action: str = ""
    recommended_citations: list[str] = field(default_factory=list)


@dataclass
class CiteCheckResult:
    """Complete citation check results."""
    issues: list[CitationIssue] = field(default_factory=list)
    total_sentences: int = 0
    cited_sentences: int = 0
    uncited_claims: int = 0


# ═══════════════════════════════════════════════════════════════
# Format Converters — Dataclass → Frontend JSON (dict)
# ═══════════════════════════════════════════════════════════════

def suggestion_to_check_result(sug: Suggestion, text: str, source: str = "deepseek") -> CheckResult:
    """Convert a backend Suggestion to a frontend CheckResult.

    Computes line numbers from character offsets. Falls back to text search
    if offsets are invalid.
    """
    # Compute 1-based line number
    if sug.start > 0 and sug.end > sug.start:
        line = text[:sug.start].count('\n') + 1
    elif sug.original:
        pos = text.find(sug.original)
        line = text[:pos].count('\n') + 1 if pos >= 0 else 1
    else:
        line = 1

    # Map backend type → frontend type
    type_map = {
        "grammar": "grammar", "spelling": "spelling",
        "tense": "tense", "style": "style", "logic": "logic",
    }
    frontend_type = type_map.get(sug.type, "style")

    # Severity mapping
    severity_map = {
        "grammar": "error", "spelling": "error",
        "tense": "warning", "logic": "warning",
        "style": "info", "punctuation": "info",
    }

    return CheckResult(
        type=frontend_type,
        line=line,
        message=sug.reason,
        fix=sug.replacement,
        severity=severity_map.get(sug.type, "warning"),
        rule_id=f"{source}:{sug.type}",
    )


def check_results_to_frontend(results: list[CheckResult]) -> list[dict]:
    """Convert CheckResult list to frontend JSON format."""
    return [
        {"type": r.type, "line": r.line, "message": r.message, "fix": r.fix}
        for r in results
    ]


def title_candidates_to_frontend(candidates: list[TitleCandidate]) -> list[dict]:
    """Convert TitleCandidate list to frontend JSON format."""
    return [
        {"text": c.text, "focus": c.focus, "rationale": c.rationale}
        for c in candidates
    ]


def abstract_result_to_frontend(result: AbstractResult) -> dict:
    """Convert AbstractResult to frontend JSON format."""
    return {
        "abstract": result.abstract,
        "background": result.background,
        "methods": result.methods,
        "results": result.results,
        "conclusion": result.conclusion,
        "word_count": result.word_count,
    }


def paraphrase_result_to_frontend(result: ParaphraseResult) -> dict:
    """Convert ParaphraseResult to frontend JSON format."""
    return {
        "rewritten_text": result.rewritten_text,
        "changes": [
            {"original": c.original, "replacement": c.replacement, "reason": c.reason}
            for c in result.changes
        ],
        "triggered_dimensions": result.triggered_dimensions,
    }


def cite_check_to_frontend(result: CiteCheckResult) -> list[dict]:
    """Convert CiteCheckResult to frontend JSON format.

    Frontend format: {sentence, line, reason, risk_level, confidence,
                      suggested_action, recommended_citations}
    """
    return [
        {
            "sentence": iss.sentence,
            "line": iss.line,
            "reason": iss.reason,
            "risk_level": iss.risk_level,
            "confidence": iss.confidence,
            "suggested_action": iss.suggested_action,
            "recommended_citations": iss.recommended_citations,
        }
        for iss in result.issues
    ]
