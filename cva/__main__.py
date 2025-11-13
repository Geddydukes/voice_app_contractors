"""Entry point for the CVA command line interface."""

from __future__ import annotations

import argparse
import sys

from .infra.cli import run_cli


def parse_args(argv: list[str]) -> tuple[str | None, list[str]]:
    """Return the primary command token and remaining arguments."""

    if not argv:
        return None, []
    first, *rest = argv
    if ":" in first:
        namespace, action = first.split(":", 1)
        return f"{namespace}:{action}".strip(), rest
    return first.strip(), rest


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    token, remaining = parse_args(argv)
    if token is None:
        parser = argparse.ArgumentParser(prog="cva")
        parser.add_argument("command", help="Command to execute, e.g. admin:new-tenant")
        parser.print_help()
        return 1
    return run_cli(token, remaining)


if __name__ == "__main__":
    sys.exit(main())
