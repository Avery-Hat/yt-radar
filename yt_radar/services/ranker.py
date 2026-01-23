from __future__ import annotations

from typing import List

from yt_radar.models import Video


class Ranker:
    """
    Sorting/scoring policy lives here.
    Keep it small now; expand later (ratios, weighted score, etc.)
    """

    VALID_SORTS = {"views", "comments"}

    def sort(self, videos: List[Video], sort_key: str) -> List[Video]:
        key = (sort_key or "").strip().lower()
        if key not in self.VALID_SORTS:
            key = "views"

        if key == "comments":
            return sorted(videos, key=lambda v: v.comment_count, reverse=True)

        # default views
        return sorted(videos, key=lambda v: v.view_count, reverse=True)
