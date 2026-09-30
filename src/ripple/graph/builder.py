"""Walk a repo and build its import dependency graph."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

from ripple.graph.model import Graph
from ripple.graph.parser import ImportRef, ParseResult, parse_file
from ripple.graph.resolver import FileEdges, ModuleIndex, resolve_file

IGNORED_DIRS = frozenset(
    {
        ".git", ".hg", ".svn", "venv", ".venv", "node_modules", "__pycache__",
        "build", "dist", ".tox", ".nox", ".eggs", "site-packages",
        ".mypy_cache", ".ruff_cache", ".pytest_cache", ".ripple-cache",
    }
)  # fmt: skip


def _is_ignored_dir(path: Path, name: str) -> bool:
    # pyvenv.cfg catches virtualenvs with any name
    return name in IGNORED_DIRS or name.endswith(".egg-info") or (path / "pyvenv.cfg").is_file()


def discover_python_files(root: Path) -> list[str]:
    """Repo-relative, forward-slash paths of every .py file, sorted."""
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        dirnames[:] = sorted(d for d in dirnames if not _is_ignored_dir(current / d, d))
        found.extend(
            (current / name).relative_to(root).as_posix()
            for name in filenames
            if name.endswith(".py")
        )
    return sorted(found)


def _describe(ref: ImportRef) -> str:
    return "." * ref.level + (ref.module or "")


def _reasons(parsed: ParseResult, resolved: FileEdges) -> tuple[str, ...]:
    reasons: list[str] = []
    if parsed.error:
        reasons.append(f"could not parse: {parsed.error}")
    reasons.extend(
        f"line {n}: dynamic import with a computed name" for n in parsed.dynamic_import_lines
    )
    reasons.extend(
        f"line {r.lineno}: unresolved import '{_describe(r)}'" for r in resolved.unresolved
    )
    return tuple(reasons)


def build_graph(root: str | Path, source_roots: Sequence[str] = (".",)) -> Graph:
    root = Path(root).resolve()
    paths = discover_python_files(root)
    index = ModuleIndex.from_paths(paths, source_roots)

    edges: dict[str, frozenset[str]] = {}
    uncertain: dict[str, tuple[str, ...]] = {}
    for rel in paths:
        parsed = parse_file(root / rel)
        resolved = resolve_file(index, rel, parsed)
        edges[rel] = resolved.targets
        if resolved.uncertain:
            uncertain[rel] = _reasons(parsed, resolved)
    return Graph.from_edges(edges, uncertain)