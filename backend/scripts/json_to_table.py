"""
Convert raw JSON input into an aligned terminal table.

Usage examples:
  python scripts/json_to_table.py --file sample.json
  echo '[{"name":"Google","count":10}]' | python scripts/json_to_table.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.terminal_table import render_table


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render JSON as aligned ASCII table")
    parser.add_argument(
        "--file",
        type=str,
        default="",
        help="Path to JSON file. If omitted, reads JSON from stdin.",
    )
    parser.add_argument(
        "--columns",
        type=str,
        default="",
        help="Optional comma-separated column order (e.g. id,name,score).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    raw = ""

    if args.file:
        raw = Path(args.file).read_text(encoding="utf-8")
    else:
        raw = sys.stdin.read()

    if not raw.strip():
        raise SystemExit("No JSON input received.")

    data = json.loads(raw)
    headers = [col.strip() for col in args.columns.split(",") if col.strip()] or None
    print(render_table(data, headers=headers))


if __name__ == "__main__":
    main()
