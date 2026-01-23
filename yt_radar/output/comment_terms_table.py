from __future__ import annotations
from typing import List
from yt_radar.services.comment_terms_service import CommentTermsResult

class CommentTermsTablePrinter:
    def print(self, results: List[CommentTermsResult]) -> None:
        if not results:
            print("No keyword matches found in fetched comments.")
            return

        headers = ["#", "hits", "matched_comments", "title", "url"]
        rows = []
        for i, r in enumerate(results, start=1):
            rows.append([
                str(i),
                str(r.total_term_hits),
                str(r.matched_comments),
                (r.video.title[:60] + "…") if len(r.video.title) > 60 else r.video.title,
                r.video.url,
            ])

        _print_table(headers, rows)

        # show samples under each result (v0: 1–3)
        for r in results[:5]:
            print("\n---")
            print(r.video.title)
            for s in r.samples:
                print(f"- {s.strip()[:200]}{'…' if len(s) > 200 else ''}")

def _print_table(headers, rows):
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
