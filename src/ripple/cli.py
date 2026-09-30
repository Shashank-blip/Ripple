from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ripple import __version__
from ripple.graph.builder import build_graph
from ripple.graph.model import Graph


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ripple",
        description="Test impact analysis: select only the tests a diff can affect.",
    )
    parser.add_argument("--version", action="version", version=f"ripple {__version__}")

    sub = parser.add_subparsers(dest="command", metavar="<command>")

    graph = sub.add_parser("graph", help="build and print the dependency graph")
    graph.add_argument("--root", default=".", help="repository root (default: .)")
    graph.add_argument("--format", choices=("text", "json"), default="text")

    sub.add_parser("select", help="select tests affected by a diff")
    return parser


def format_graph_text(graph: Graph) -> str:
    n_edges = sum(len(targets) for targets in graph.edges.values())
    counts = f"{len(graph.files)} files, {n_edges} edges, {len(graph.uncertain)} uncertain"
    lines = [f"ripple graph: {counts}"]
    for path in sorted(graph.edges):
        targets = sorted(graph.edges[path])
        if targets:
            lines.append(f"  {path} -> {', '.join(targets)}")
    if graph.uncertain:
        lines.append("uncertain (selection will treat these conservatively):")
        for path in sorted(graph.uncertain):
            lines.append(f"  {path}")
            lines.extend(f"    {reason}" for reason in graph.uncertain[path])
    return "\n".join(lines)


def cmd_graph(args: argparse.Namespace) -> int:
    root = Path(args.root)
    if not root.is_dir():
        print(f"ripple: not a directory: {root}", file=sys.stderr)
        return 2
    graph = build_graph(root)
    if args.format == "json":
        print(json.dumps(graph.to_json_dict(), indent=2))
    else:
        print(format_graph_text(graph))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "graph":
        return cmd_graph(args)

    print(f"ripple {args.command}: not implemented yet", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())