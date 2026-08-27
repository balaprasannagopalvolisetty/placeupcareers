"""
Render raw list/dict data as aligned ASCII tables for terminal output.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence


def _stringify(value: object) -> str:
    """Convert Python values to compact table-safe strings."""
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, (list, tuple, set)):
        return ", ".join(_stringify(item) for item in value) or "-"
    if isinstance(value, Mapping):
        return ", ".join(f"{k}={_stringify(v)}" for k, v in value.items()) or "-"
    return str(value)


def _normalize_rows(data: object) -> list[dict[str, object]]:
    """
    Normalize input into tabular rows.

    Accepted:
    - list[dict]
    - dict (single row)
    - list[primitive] -> {"value": primitive}
    """
    if isinstance(data, Mapping):
        return [dict(data)]

    if isinstance(data, Sequence) and not isinstance(data, (str, bytes, bytearray)):
        rows: list[dict[str, object]] = []
        for item in data:
            if isinstance(item, Mapping):
                rows.append(dict(item))
            else:
                rows.append({"value": item})
        return rows

    return [{"value": data}]


def render_table(data: object, headers: list[str] | None = None) -> str:
    """
    Return a neatly aligned ASCII table string for terminal usage.
    """
    rows = _normalize_rows(data)
    if not rows:
        return "No rows to display."

    ordered_columns: list[str] = []
    if headers:
        ordered_columns = list(headers)
    else:
        seen = set()
        for row in rows:
            for key in row.keys():
                if key not in seen:
                    seen.add(key)
                    ordered_columns.append(key)

    if not ordered_columns:
        return "No columns to display."

    rendered_rows = []
    for row in rows:
        rendered_rows.append([_stringify(row.get(column, "-")) for column in ordered_columns])

    widths = [len(column) for column in ordered_columns]
    for row in rendered_rows:
        for idx, value in enumerate(row):
            widths[idx] = max(widths[idx], len(value))

    def _render_separator(char: str = "-") -> str:
        return "+" + "+".join(char * (width + 2) for width in widths) + "+"

    header_row = "| " + " | ".join(
        ordered_columns[idx].ljust(widths[idx]) for idx in range(len(ordered_columns))
    ) + " |"

    body_rows = [
        "| " + " | ".join(row[idx].ljust(widths[idx]) for idx in range(len(row))) + " |"
        for row in rendered_rows
    ]

    lines = [_render_separator(), header_row, _render_separator("="), *body_rows, _render_separator()]
    return "\n".join(lines)
