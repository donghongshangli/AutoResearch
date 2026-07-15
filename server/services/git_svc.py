"""
git_svc.py — Git 版本管理服务

用法:
    from server.services.git_svc import git_commit, git_log, git_diff, git_revert
"""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger("autoresearch.git")


def _run(cwd: Path, *args: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(
            ["git"] + list(args),
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        logger.warning("Git 未安装或不在 PATH 中")
        return None
    except Exception as e:
        logger.warning(f"Git 命令执行失败: {e}")
        return None


def git_init(proj_dir: Path) -> None:
    """初始化 Git 仓库。"""
    result = _run(proj_dir, "init")
    if result is None:
        return
    # 创建 .gitignore
    gitignore = proj_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("build/\n__pycache__/\n*.aux\n*.log\n*.out\n*.toc\n*.pdf\n")


def git_commit(proj_dir: Path, message: str) -> dict:
    """提交所有更改。"""
    add_result = _run(proj_dir, "add", "-A")
    if add_result is None:
        return {"status": "error", "message": "Git 不可用"}
    result = _run(proj_dir, "commit", "-m", message)
    if result is None:
        return {"status": "error", "message": "Git 不可用"}
    if result.returncode != 0 and "nothing to commit" in (result.stdout + result.stderr):
        return {"status": "no_changes"}
    return {
        "status": "ok",
        "output": result.stdout.strip()[-200:],
    }


def git_log(proj_dir: Path, max_count: int = 20) -> list[dict]:
    """获取提交历史。"""
    result = _run(
        proj_dir, "log",
        f"--max-count={max_count}",
        "--format=%H|%ai|%s",
    )
    if result is None or result.returncode != 0:
        return []
    commits = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("|", 2)
        if len(parts) == 3:
            commits.append({"hash": parts[0], "date": parts[1], "message": parts[2]})
    return commits


def git_diff(proj_dir: Path, commit_hash: str = "HEAD") -> str:
    """获取某次 commit 的 diff。"""
    result = _run(proj_dir, "show", "--stat", commit_hash)
    if result is None:
        return ""
    return result.stdout.strip()


def git_revert(proj_dir: Path, commit_hash: str) -> dict:
    """回退到指定 commit。"""
    result = _run(proj_dir, "reset", "--hard", commit_hash)
    if result is None:
        return {"status": "error", "message": "Git 不可用"}
    if result.returncode != 0:
        return {"status": "error", "message": result.stderr.strip()}
    return {"status": "ok", "reverted_to": commit_hash[:8]}
