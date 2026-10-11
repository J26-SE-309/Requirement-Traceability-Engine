"""Python AST Parser for Requirement Traceability Engine.

Extracts functions, async functions, methods, signatures, docstrings,
call-graph invocations, explicit '# Trace: <STORY-ID>' comment directives,
and classifies symbols into production code vs. test fixtures with verifiable assertions.
"""

from __future__ import annotations

import ast
import io
import logging
from dataclasses import dataclass, field
from pathlib import Path
import re
import tokenize
from typing import Literal

logger = logging.getLogger(__name__)

# Regex for explicit traceability comment directives
# Matches:
#   # Trace: STORY-101
#   # @trace STORY-102
#   # trace: S-1, S-2
#   # @trace: STORY_3
TRACE_DIRECTIVE_PATTERN = re.compile(
    r"#\s*(?:@trace|Trace|trace):?\s*([A-Za-z0-9_,\s\-]+)",
    re.IGNORECASE,
)

TEST_FILE_PATTERN = re.compile(
    r"(^|[/\\])(tests?|unit_tests?|integration_tests?)[/\\]|(^|[/\\])test_.*\.py$|_test\.py$",
    re.IGNORECASE,
)


def split_identifier(name: str) -> str:
    """Split snake_case and camelCase identifiers into space-delimited natural words.

    Examples:
        'verify_jwt_token' -> 'verify jwt token'
        'calculateStateTax' -> 'calculate state tax'
        'HTTPResponseHandler' -> 'http response handler'
    """
    # 1. Handle consecutive uppercase abbreviations: 'HTTPResponse' -> 'HTTP Response'
    s1 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", name)
    # 2. Handle standard camelCase transitions: 'stateTax' -> 'state Tax'
    s2 = re.sub(r"([a-z\d])([A-Z])", r"\1 \2", s1)
    # 3. Replace underscores with spaces and normalize casing
    return s2.replace("_", " ").strip().lower()


@dataclass
class ParsedSymbol:
    """Represents an extracted Python function, method, or test block."""

    name: str
    line_start: int = 1
    line_end: int = 1
    docstring: str | None = None
    code_snippet: str = ""
    kind: Literal["code", "test"] = "code"
    explicit_traces: list[str] = field(default_factory=list)
    signature: str = ""
    qualified_name: str = ""
    semantic_text: str = ""
    has_assertions: bool = False
    file_path: str = ""
    called_symbols: list[str] = field(default_factory=list)

    def __init__(
        self,
        name: str,
        line_start: int | None = None,
        line_end: int | None = None,
        docstring: str | None = None,
        code_snippet: str = "",
        kind: Literal["code", "test"] = "code",
        explicit_traces: list[str] | None = None,
        signature: str = "",
        qualified_name: str = "",
        semantic_text: str = "",
        has_assertions: bool = False,
        file_path: str = "",
        called_symbols: list[str] | None = None,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> None:
        self.name = name
        self.line_start = line_start if line_start is not None else (start_line if start_line is not None else 1)
        self.line_end = line_end if line_end is not None else (end_line if end_line is not None else self.line_start)
        self.docstring = docstring
        self.code_snippet = code_snippet
        self.kind = kind
        self.explicit_traces = explicit_traces if explicit_traces is not None else []
        self.signature = signature
        self.qualified_name = qualified_name or name
        self.semantic_text = semantic_text
        self.has_assertions = has_assertions
        self.file_path = file_path
        self.called_symbols = called_symbols if called_symbols is not None else []

    @property
    def start_line(self) -> int:
        """Alias for backward compatibility."""
        return self.line_start

    @start_line.setter
    def start_line(self, val: int) -> None:
        self.line_start = val

    @property
    def end_line(self) -> int:
        """Alias for backward compatibility."""
        return self.line_end

    @end_line.setter
    def end_line(self, val: int) -> None:
        self.line_end = val

    def contains_line(self, line_number: int) -> bool:
        """Check if 1-indexed line_number is within symbol span."""
        return self.line_start <= line_number <= self.line_end


# Backward-compatible alias
ParsedFunction = ParsedSymbol


def _extract_comments(source_code: str) -> list[tuple[int, str]]:
    """Extract line-numbered comments using Python's tokenizer."""
    comments: list[tuple[int, str]] = []
    try:
        reader = io.StringIO(source_code).readline
        for tok in tokenize.generate_tokens(reader):
            if tok.type == tokenize.COMMENT:
                comments.append((tok.start[0], tok.string))
    except (tokenize.TokenError, IndentationError, Exception) as e:
        logger.debug("Tokenize failed during comment extraction: %s", e)
    return comments


def _extract_story_ids_from_comment(comment_text: str) -> list[str]:
    """Parse story IDs from a single comment line if it matches trace directive."""
    match = TRACE_DIRECTIVE_PATTERN.search(comment_text)
    if not match:
        return []
    raw_payload = match.group(1)
    parts = re.split(r"[,\s]+", raw_payload.strip())
    return [p.strip() for p in parts if p.strip()]


def _has_test_assertions(node: ast.AST) -> bool:
    """Check if AST subtree contains assert statements or test assertion calls."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Assert):
            return True
        if isinstance(sub, ast.Call):
            func = sub.func
            if isinstance(func, ast.Attribute):
                if func.attr.startswith("assert"):
                    return True
                if func.attr in ("raises", "fail"):
                    return True
            elif isinstance(func, ast.Name):
                if func.id.startswith("assert"):
                    return True
    return False


def _extract_called_symbols(node: ast.AST) -> list[str]:
    """Traverse AST to extract all function and method invocations called inside body."""
    calls: list[str] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            if isinstance(func, ast.Name):
                calls.append(func.id)
            elif isinstance(func, ast.Attribute):
                # Captures method calls: obj.verify_jwt_token() -> 'verify_jwt_token'
                calls.append(func.attr)

    seen: set[str] = set()
    return [c for c in calls if not (c in seen or seen.add(c))]


def _build_signature(node: ast.FunctionDef | ast.AsyncFunctionDef, source_lines: list[str]) -> str:
    """Extract or rebuild the function signature string."""
    try:
        def_line = source_lines[node.lineno - 1].strip()
        if ":" in def_line:
            return def_line.split(":", 1)[0]
    except Exception:
        pass

    args = [a.arg for a in node.args.args]
    prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
    return f"{prefix}{node.name}({', '.join(args)})"


def _build_semantic_text(
    name: str,
    docstring: str | None,
    signature: str,
    code_snippet: str,
    args: list[str],
    called_symbols: list[str],
) -> str:
    """Formulate high-density semantic text for INT8 Sentence-BERT embedding.

    Normalizes identifiers and focuses on domain vocabulary to maximize cosine similarity.
    """
    natural_name = split_identifier(name)
    parts: list[str] = [f"Function {natural_name}"]

    # Include parameter terms
    clean_params = [
        split_identifier(arg)
        for arg in args
        if arg not in ("self", "cls", "args", "kwargs")
    ]
    if clean_params:
        parts.append(f"Parameters: {', '.join(clean_params)}")

    if docstring:
        clean_doc = " ".join(docstring.split())
        parts.append(f"Description: {clean_doc}")

    # Include called dependencies (adds contextual domain terms)
    domain_calls = [
        split_identifier(c)
        for c in called_symbols[:6]
        if not c.startswith("_") and c not in ("print", "len", "range", "isinstance", "int", "str")
    ]
    if domain_calls:
        parts.append(f"Invocations: {', '.join(domain_calls)}")

    parts.append(f"Signature: {signature}")

    # Extract non-comment executable implementation lines
    snippet_lines = [
        line.strip()
        for line in code_snippet.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    summary_code = " ".join(snippet_lines[:5])
    if summary_code:
        parts.append(f"Implementation: {summary_code}")

    return " | ".join(parts)


def parse_python_symbols(
    file_path: Path | str = "",
    source_code: str | None = None,
) -> list[ParsedSymbol]:
    """Parse Python source or file into AST symbols safely.

    Catches SyntaxError gracefully so in-progress edits don't crash callers.
    """
    file_str = str(file_path) if file_path else ""

    if source_code is None:
        path = Path(file_path)
        if not path.exists():
            logger.warning("File not found for AST parsing: %s", path)
            return []
        try:
            source_code = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.error("Failed to read %s: %s", path, e)
            return []

    source_lines = source_code.splitlines()
    comments = _extract_comments(source_code)

    is_test_file = bool(TEST_FILE_PATTERN.search(file_str)) if file_str else False

    parsed_symbols: list[ParsedSymbol] = []

    # Map line number to comments
    comment_map: dict[int, list[str]] = {}
    for lineno, comment in comments:
        comment_map.setdefault(lineno, []).append(comment)

    class FunctionVisitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.class_stack: list[str] = []

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self.class_stack.append(node.name)
            self.generic_visit(node)
            self.class_stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._handle_function(node)
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._handle_function(node)
            self.generic_visit(node)

        def _handle_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            start_line = node.lineno
            if node.decorator_list:
                start_line = min(d.lineno for d in node.decorator_list)
            end_line = getattr(node, "end_lineno", start_line)

            qualname = (
                f"{'.'.join(self.class_stack)}.{node.name}" if self.class_stack else node.name
            )
            docstring = ast.get_docstring(node)

            slice_lines = source_lines[start_line - 1 : end_line]
            code_snippet = "\n".join(slice_lines)
            sig = _build_signature(node, source_lines)

            # Explicit trace directives
            explicit_traces: list[str] = []

            # 1. Comments immediately above the function header (up to 3 lines above start_line)
            for line_idx in range(max(1, start_line - 3), start_line):
                for comm in comment_map.get(line_idx, []):
                    traces = _extract_story_ids_from_comment(comm)
                    explicit_traces.extend(traces)

            # 2. Comments within the function body
            for line_idx in range(start_line, end_line + 1):
                for comm in comment_map.get(line_idx, []):
                    traces = _extract_story_ids_from_comment(comm)
                    explicit_traces.extend(traces)

            seen = set()
            unique_traces = [t for t in explicit_traces if not (t in seen or seen.add(t))]

            # Kind classification: test vs code
            is_test_symbol = (
                node.name.startswith("test_")
                or node.name.endswith("_test")
                or is_test_file
                or any(
                    "fixture" in getattr(d, "id", "") or "test" in getattr(d, "id", "")
                    for d in node.decorator_list
                    if isinstance(d, ast.Name)
                )
            )
            kind: Literal["code", "test"] = "test" if is_test_symbol else "code"
            has_assertions = _has_test_assertions(node)

            # Extract called functions and method names for call-graph linking
            called_symbols = _extract_called_symbols(node)

            args = [a.arg for a in node.args.args]
            semantic_text = _build_semantic_text(
                name=node.name,
                docstring=docstring,
                signature=sig,
                code_snippet=code_snippet,
                args=args,
                called_symbols=called_symbols,
            )

            parsed_symbols.append(
                ParsedSymbol(
                    name=node.name,
                    line_start=start_line,
                    line_end=end_line,
                    docstring=docstring,
                    code_snippet=code_snippet,
                    kind=kind,
                    explicit_traces=unique_traces,
                    signature=sig,
                    qualified_name=qualname,
                    semantic_text=semantic_text,
                    has_assertions=has_assertions,
                    file_path=file_str,
                    called_symbols=called_symbols,
                )
            )

    visitor = FunctionVisitor()
    try:
        tree = ast.parse(source_code)
        visitor.visit(tree)
    except SyntaxError as e:
        logger.warning("SyntaxError parsing %s: %s (initiating resilient symbol recovery)", file_str or "<source>", e)
        # Resilient block-by-block parsing for in-progress edits
        top_indices: list[int] = []
        for idx, line in enumerate(source_lines):
            if (line.startswith("def ") or line.startswith("async def ") or line.startswith("class ") or line.startswith("@")) and not line.startswith(" "):
                top_indices.append(idx)

        if not top_indices:
            for idx, line in enumerate(source_lines):
                if re.match(r"^\s*(?:async\s+)?def\s+([a-zA-Z0-9_]+)", line):
                    top_indices.append(idx)

        if top_indices:
            top_indices.append(len(source_lines))
            for i in range(len(top_indices) - 1):
                start_idx = top_indices[i]
                end_idx = top_indices[i + 1]
                padded_block = ("\n" * start_idx) + "\n".join(source_lines[start_idx:end_idx])
                try:
                    block_tree = ast.parse(padded_block)
                    visitor.visit(block_tree)
                except Exception:
                    # Regex fallback for the specific block containing the syntax error
                    first_line = source_lines[start_idx].strip()
                    m = re.match(r"^(?:async\s+)?def\s+([a-zA-Z0-9_]+)\s*\((.*?)\)", first_line)
                    if m:
                        fn_name = m.group(1)
                        block_slice = source_lines[start_idx:end_idx]
                        snippet = "\n".join(block_slice)
                        doc = None
                        for bl in block_slice[1:min(6, len(block_slice))]:
                            if '"""' in bl or "'''" in bl:
                                doc = bl.replace('"""', '').replace("'''", '').strip()
                                break
                        explicit_traces: list[str] = []
                        for line_idx in range(max(1, start_idx - 2), start_idx + 1):
                            for comm in comment_map.get(line_idx + 1, []):
                                explicit_traces.extend(_extract_story_ids_from_comment(comm))
                        is_test_sym = fn_name.startswith("test_") or fn_name.endswith("_test") or is_test_file
                        has_assert = any("assert " in bl for bl in block_slice)
                        parsed_symbols.append(
                            ParsedSymbol(
                                name=fn_name,
                                line_start=start_idx + 1,
                                line_end=end_idx,
                                docstring=doc,
                                code_snippet=snippet,
                                kind="test" if is_test_sym else "code",
                                explicit_traces=explicit_traces,
                                signature=first_line,
                                qualified_name=fn_name,
                                semantic_text=f"Function: {fn_name}. {doc or ''}",
                                has_assertions=has_assert,
                                file_path=file_str,
                                called_symbols=[],
                            )
                        )
    except Exception as e:
        logger.warning("AST parse failure for %s: %s", file_str or "<source>", e)

    parsed_symbols.sort(key=lambda s: s.line_start)
    return parsed_symbols


def parse_python_source(source_code: str, file_path: str = "") -> list[ParsedSymbol]:
    """Backward-compatible helper to parse raw Python source string."""
    return parse_python_symbols(file_path=file_path, source_code=source_code)


def parse_python_file(file_path: Path | str) -> list[ParsedSymbol]:
    """Backward-compatible helper to parse Python file from disk."""
    return parse_python_symbols(file_path=file_path)