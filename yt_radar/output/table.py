from __future__ import annotations

from typing import List

from yt_radar.models import Video


class TablePrinter:
    def print(self, videos: List[Video]) -> None:
        if not videos:
            print("No results.")
            return

        rows = []
        for i, v in enumerate(videos, start=1):
            rows.append(
                [
                    str(i),
                    _truncate(v.title, 60),
                    f"{v.view_count:,}",
                    f"{v.comment_count:,}",
                    v.url,
                ]
            )

        headers = ["#", "title", "views", "comments", "url"]
        _print_table(headers, rows)


def _truncate(text: str, max_len: int) -> str:
    t = (text or "").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


def _print_table(headers: List[str], rows: List[List[str]]) -> None:
    # basic table printer (no deps)
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(row):
        return " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))

    print(fmt_row(headers))
    print("-+-".join("-" * w for w in widths))
    for row in rows:
        print(fmt_row(row))
