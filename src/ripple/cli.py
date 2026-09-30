from __future__ import annotations

import argparse
import sys

from ripple import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ripple",
        description="Test impact analysis: slect only the tests a diff can affect.",
    )

    parser.add_argument(
        "--version", action="version", version=f"ripple {__version__}"
    )

    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.add_parser("graph", help="build and print the dependency graph")
    sub.add_parser("select", help="select tests affected by a diff")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    print(f"ripple {args.command}: not implemented yet", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())