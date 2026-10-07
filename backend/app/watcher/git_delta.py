"""Git Delta Extractor for Real-Time Save Events.

Executes `git diff -U0 <file>` to isolate modified line ranges,
filtering AST symbol extraction to ONLY dirty functions.
Preserves sub-350ms save latency budget on Ctrl+S.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Sequence

from app.parsers.python_ast import (
    ParsedFunction,
    ParsedSymbol,
    parse_python_file,
    parse_python_source,
    parse_python_symbols,
)

logger = logging.getLogger(__name__)

# Unified diff hunk regex: @@ -old_start[,old_count] +new_start[,new_count] @@
HUNK_PATTERN = re.compile(r"^@@\s+-(?:\d+)(?:,\d+)?\s+\+(\d+)(?:,(\d+))?\s+@@")


def get_delta_ranges_from_diff(diff_output: str) -> list[tuple[int, int]]:
    """Parse unified diff text (-U0) and extract (start_line, end_line) intervals in new file.

    Returns:
        List of 1-indexed inclusive (start_line, end_line) tuples.
    """
    ranges: list[tuple[int, int]] = []
    for line in diff_output.splitlines():
        if not line.startswith("@@"):
            continue
        match = HUNK_PATTERN.match(line)
        if not match:
            continue
        new_start = int(match.group(1))
        count_str = match.group(2)
        new_count = int(count_str) if count_str is not None else 1

        if new_count == 0:
            # Deletion at new_start; flag single surrounding point
            ranges.append((max(1, new_start), max(1, new_start)))
        else:
            ranges.append((new_start, new_start + new_count - 1))

    return ranges


def get_dirty_lines_from_diff(diff_output: str) -> set[int]:
    """Parse unified diff text (-U0) and extract all modified line numbers in the new file."""
    ranges = get_delta_ranges_from_diff(diff_output)
    dirty_lines: set[int] = set()
    for start, end in ranges:
        for l in range(start, end + 1):
            dirty_lines.add(l)
    return dirty_lines


def get_git_delta_ranges(
    file_path: Path | str,
    repo_root: Path | str | None = None,
    timeout_sec: float = 0.25,
) -> list[tuple[int, int]]:
    """Execute git diff -U0 to determine modified line intervals (start_line, end_line) in file_path.

    Checks both unstaged changes and staged changes.
    """
    path = Path(file_path).resolve()
    cwd = Path(repo_root).resolve() if repo_root else path.parent

    if not repo_root:
        cur = path.parent
        while cur != cur.parent:
            if (cur / ".git").exists():
                cwd = cur
                break
            cur = cur.parent

    all_ranges: list[tuple[int, int]] = []

    # 1. Unstaged diff
    try:
        proc = subprocess.run(
            ["git", "diff", "-U0", "--", str(path)],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout:
            all_ranges.extend(get_delta_ranges_from_diff(proc.stdout))
    except Exception as e:
        logger.debug("git diff failed for %s: %s", path, e)

    # 2. Staged diff (cached)
    try:
        proc_cached = subprocess.run(
            ["git", "diff", "--cached", "-U0", "--", str(path)],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        if proc_cached.returncode == 0 and proc_cached.stdout:
            all_ranges.extend(get_delta_ranges_from_diff(proc_cached.stdout))
    except Exception as e:
        logger.debug("git diff --cached failed for %s: %s", path, e)

    return all_ranges


def get_git_diff_dirty_lines(
    file_path: Path | str,
    repo_root: Path | str | None = None,
    timeout_sec: float = 0.25,
) -> set[int]:
    """Execute git diff -U0 to determine modified lines set."""
    ranges = get_git_delta_ranges(file_path, repo_root=repo_root, timeout_sec=timeout_sec)
    dirty_lines: set[int] = set()
    for start, end in ranges:
        for l in range(start, end + 1):
            dirty_lines.add(l)
    return dirty_lines


def filter_symbols_by_delta(
    symbols: Sequence[ParsedSymbol],
    delta_ranges: list[tuple[int, int]],
) -> list[ParsedSymbol]:
    """Filter symbols returning only those intersecting the delta line intervals.

    Includes function header comment bounds (up to 3 lines above start).
    """
    if not delta_ranges:
        return []

    modified: list[ParsedSymbol] = []
    for sym in symbols:
        expanded_start = max(1, sym.line_start - 3)
        # Check intersection between [expanded_start, sym.line_end] and [d_start, d_end]
        intersects = any(
            max(expanded_start, d_start) <= min(sym.line_end, d_end)
            for d_start, d_end in delta_ranges
        )
        if intersects:
            modified.append(sym)

    return modified


def filter_functions_by_dirty_lines(
    functions: Sequence[ParsedFunction],
    dirty_lines: set[int],
) -> list[ParsedFunction]:
    """Backward-compatible helper filtering by a set of dirty line integers."""
    if not dirty_lines:
        return []

    modified: list[ParsedFunction] = []
    for func in functions:
        expanded_start = max(1, func.start_line - 3)
        func_lines = range(expanded_start, func.end_line + 1)
        if any(line in dirty_lines for line in func_lines):
            modified.append(func)

    return modified


def get_modified_functions(
    file_path: Path | str,
    repo_root: Path | str | None = None,
    source_code: str | None = None,
) -> tuple[list[ParsedSymbol], float]:
    """Execute git delta and AST parse to retrieve ONLY modified functions."""
    t0 = time.perf_counter()
    path = Path(file_path)

    symbols = parse_python_symbols(path, source_code=source_code)
    delta_ranges = get_git_delta_ranges(path, repo_root=repo_root)

    if not delta_ranges:
        modified = symbols
    else:
        modified = filter_symbols_by_delta(symbols, delta_ranges)

    elapsed_ms = (time.perf_counter() - t0) * 1000
    logger.debug("Git delta + AST for %s: %d modified functions in %.2fms", path.name, len(modified), elapsed_ms)
    return modified, elapsed_ms
