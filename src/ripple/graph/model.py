"""The dependency graph: forward edges, reverse index, and uncertainty notes."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Graph:
    edges: dict[str, frozenset[str]]  # file -> files it depends on
    reverse: dict[str, frozenset[str]]  # file -> files that depend on it
    uncertain: dict[str, tuple[str, ...]]  # file -> why its edges can't be fully trusted

    @property
    def files(self) -> frozenset[str]:
        return frozenset(self.edges)

    @classmethod
    def from_edges(
        cls,
        edges: Mapping[str, Iterable[str]],
        uncertain: Mapping[str, Sequence[str]] | None = None,
    ) -> Graph:
        forward = {path: frozenset(targets) for path, targets in edges.items()}
        reverse: dict[str, set[str]] = {path: set() for path in forward}
        for path, targets in forward.items():
            for target in targets:
                reverse.setdefault(target, set()).add(path)
        return cls(
            edges=forward,
            reverse={path: frozenset(v) for path, v in reverse.items()},
            uncertain={path: tuple(r) for path, r in (uncertain or {}).items()},
        )

    def to_json_dict(self) -> dict:
        return {
            "files": sorted(self.edges),
            "edges": {path: sorted(t) for path, t in sorted(self.edges.items()) if t},
            "uncertain": {path: list(r) for path, r in sorted(self.uncertain.items())},
        }