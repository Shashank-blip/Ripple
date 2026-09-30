"""Map parsed imports onto files inside the repo.

Pure module: works from a list of repo-relative posix paths and never touches the disk.

Safety rules:
- `import a.b.c` depends on a, a.b AND a.b.c (Python runs each package __init__.py).
- Every module implicitly depends on the __init__.py of each parent package.
- `from pkg import name` also depends on `pkg.name` when that is a submodule.
- `from pkg import *` depends on pkg and all its direct submodules (via __all__).
- Imports whose top-level package isn't ours are external and ignored. A missing module
  *inside* one of our packages is "unresolved" and makes the file uncertain.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

from ripple.graph.parser import ImportRef, ParseResult

INIT_FILE = "__init__.py"


def _prefixes(dotted: str) -> list[str]:
    parts = dotted.split(".")
    return [".".join(parts[: i + 1]) for i in range(len(parts))]


def _normalize_root(root: str) -> str:
    return PurePosixPath(root).as_posix()  # "" and "./" both become "."


def _depth(root: str) -> int:
    return 0 if root == "." else len(PurePosixPath(root).parts)


def _root_for(rel_path: str, roots: Iterable[str]) -> str:
    best = "."
    for root in roots:
        if root != "." and rel_path.startswith(root + "/") and _depth(root) > _depth(best):
            best = root
    return best


def _module_parts(rel_path: str, root: str) -> tuple[str, ...] | None:
    """Dotted-name parts for a file under a source root, or None if it isn't importable."""
    path = PurePosixPath(rel_path)
    if path.suffix != ".py":
        return None
    if root != ".":
        path = path.relative_to(root)
    parts = list(path.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    if not parts or not all(p.isidentifier() for p in parts):
        return None
    return tuple(parts)


@dataclass(frozen=True)
class ModuleIndex:
    modules: dict[str, str]  # dotted name -> file that defines it
    file_modules: dict[str, str]  # file -> dotted name (importable files only)
    known: frozenset[str]  # every module name plus every ancestor (incl. namespace dirs)
    children: dict[str, tuple[str, ...]]  # dotted name -> direct child names
    top_levels: frozenset[str]  # first components of our own packages

    @classmethod
    def from_paths(
        cls, paths: Iterable[str], source_roots: Sequence[str] = (".",)
    ) -> ModuleIndex:
        roots = {_normalize_root(r) for r in source_roots} | {"."}
        # packages first, so `a/__init__.py` wins over `a.py` like the real import system
        ordered = sorted(paths, key=lambda p: (PurePosixPath(p).name != INIT_FILE, p))

        modules: dict[str, str] = {}
        file_modules: dict[str, str] = {}
        for rel in ordered:
            parts = _module_parts(rel, _root_for(rel, roots))
            if parts is None:
                continue
            name = ".".join(parts)
            file_modules[rel] = name
            modules.setdefault(name, rel)

        known = {prefix for name in file_modules.values() for prefix in _prefixes(name)}
        children: dict[str, list[str]] = {}
        for name in known:
            parent = name.rpartition(".")[0]
            if parent:
                children.setdefault(parent, []).append(name)

        return cls(
            modules=modules,
            file_modules=file_modules,
            known=frozenset(known),
            children={k: tuple(sorted(v)) for k, v in children.items()},
            top_levels=frozenset(n for n in known if "." not in n),
        )

    def package_of(self, path: str) -> str | None:
        """The package a file lives in (what `.` means in its relative imports)."""
        name = self.file_modules.get(path)
        if name is None:
            return None
        if PurePosixPath(path).name == INIT_FILE:
            return name
        return name.rpartition(".")[0] or None

    def relative_base(self, importer: str, level: int, module: str | None) -> str | None:
        """Absolute dotted name a relative import points at, or None if it escapes the top."""
        package = self.package_of(importer)
        if not package:
            return None
        parts = package.split(".")
        if level > len(parts):
            return None
        base = parts[: len(parts) - (level - 1)]
        if module:
            base += module.split(".")
        return ".".join(base)

    def parent_inits(self, path: str) -> set[str]:
        name = self.file_modules.get(path)
        if name is None:
            return set()
        found = set()
        for prefix in _prefixes(name)[:-1]:
            file = self.modules.get(prefix)
            if file is not None and PurePosixPath(file).name == INIT_FILE:
                found.add(file)
        return found


@dataclass(frozen=True)
class FileEdges:
    path: str
    targets: frozenset[str]  # repo files this file depends on
    unresolved: tuple[ImportRef, ...]  # imports into our own packages we couldn't map
    uncertain: bool  # True if selection must treat this file conservatively


def _resolve_ref(index: ModuleIndex, importer: str, ref: ImportRef) -> tuple[set[str], bool]:
    """Return (files depended on, resolved_ok)."""
    if ref.is_relative:
        dotted = index.relative_base(importer, ref.level, ref.module)
    else:
        dotted = ref.module
    if not dotted:
        return set(), False

    files = {index.modules[p] for p in _prefixes(dotted) if p in index.modules}
    ok = dotted in index.known or dotted.split(".")[0] not in index.top_levels

    for name in ref.names:
        if name == "*":
            for child in index.children.get(dotted, ()):
                if child in index.modules:
                    files.add(index.modules[child])
        elif f"{dotted}.{name}" in index.modules:
            files.add(index.modules[f"{dotted}.{name}"])
    return files, ok


def resolve_file(index: ModuleIndex, path: str, parsed: ParseResult) -> FileEdges:
    targets = index.parent_inits(path)
    unresolved: list[ImportRef] = []
    for ref in parsed.imports:
        files, ok = _resolve_ref(index, path, ref)
        targets |= files
        if not ok:
            unresolved.append(ref)
    targets.discard(path)
    return FileEdges(
        path=path,
        targets=frozenset(targets),
        unresolved=tuple(unresolved),
        uncertain=parsed.uncertain or bool(unresolved),
    )