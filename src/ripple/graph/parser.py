"""Extract import statements from Python source.

Design rule: never guess silently. Anything we cannot fully understand (syntax errors,
unreadable files, dynamic imports with computed names) marks the result `uncertain`,
and downstream selection treats uncertain files conservatively.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

_DYNAMIC_IMPORT_FUNCS = {"__import__", "import_module"}


@dataclass(frozen=True)
class ImportRef:
    """One imported module reference, exactly as written in the source.

    `module` is None for `from . import x` (the target is named only by `names`).
    For `from pkg import a`, the resolver later decides whether `a` is a submodule
    or just an attribute of `pkg`.
    """

    module: str | None
    names: tuple[str, ...] = ()
    level: int = 0
    lineno: int = 0

    @property
    def is_relative(self) -> bool:
        return self.level > 0

    @property
    def is_star(self) -> bool:
        return self.names == ("*",)


@dataclass(frozen=True)
class ParseResult:
    imports: tuple[ImportRef, ...] = ()
    dynamic_import_lines: tuple[int, ...] = ()
    error: str | None = None

    @property
    def uncertain(self) -> bool:
        return bool(self.dynamic_import_lines) or self.error is not None


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _literal_module_name(node: ast.Call, func_name: str) -> str | None:
    """Return the module name if this dynamic import is fully static, else None."""
    if func_name == "__import__" and (
        len(node.args) >= 5 or any(kw.arg == "level" for kw in node.keywords)
    ):
        return None  # explicit level means a relative import, which we don't resolve here
    if not node.args:
        return None
    first = node.args[0]
    if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
        return None
    name = first.value
    if not name or name.startswith("."):
        return None
    return name


class _Collector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.imports: list[ImportRef] = []
        self.dynamic_lines: list[int] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(ImportRef(module=alias.name, lineno=node.lineno))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.imports.append(
            ImportRef(
                module=node.module,
                names=tuple(alias.name for alias in node.names),
                level=node.level,
                lineno=node.lineno,
            )
        )

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node)
        if name in _DYNAMIC_IMPORT_FUNCS:
            target = _literal_module_name(node, name)
            if target is None:
                self.dynamic_lines.append(node.lineno)
            else:
                self.imports.append(ImportRef(module=target, lineno=node.lineno))
        self.generic_visit(node)


def parse_source(source: str | bytes, filename: str = "<unknown>") -> ParseResult:
    try:
        tree = ast.parse(source, filename=filename)
    except (SyntaxError, ValueError, RecursionError) as exc:
        return ParseResult(error=f"{type(exc).__name__}: {exc}")

    collector = _Collector()
    collector.visit(tree)
    return ParseResult(
        imports=tuple(collector.imports),
        dynamic_import_lines=tuple(collector.dynamic_lines),
    )


def parse_file(path: str | Path) -> ParseResult:
    path = Path(path)
    try:
        source = path.read_bytes()  # bytes, so ast honours PEP 263 encoding cookies
    except OSError as exc:
        return ParseResult(error=f"{type(exc).__name__}: {exc}")
    return parse_source(source, filename=str(path))