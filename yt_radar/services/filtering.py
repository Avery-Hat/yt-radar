from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional

from yt_radar.models import Video


@dataclass(frozen=True)
class Filters:
    min_views: int = 0
    min_comments: int = 0
    since_days: Optional[int] = None  # e.g. 30 means only videos published in last 30 days


class VideoFilter:
    def apply(self, videos: Iterable[Video], f: Filters) -> List[Video]:
        out: List[Video] = []
        cutoff = _since_cutoff(f.since_days)

        for v in videos:
            if v.view_count < f.min_views:
                continue
            if v.comment_count < f.min_comments:
                continue
            if cutoff and not _published_after(v.published_at, cutoff):
                continue
            out.append(v)

        return out


def _since_cutoff(days: Optional[int]) -> Optional[datetime]:
    if days is None:
        return None
    if days < 0:
        days = 0
    return datetime.now(timezone.utc) - timedelta(days=days)


def _published_after(published_at: str, cutoff: datetime) -> bool:
    # publishedAt is ISO like "2025-01-20T12:34:56Z"
    try:
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except Exception:
        return False
    return dt >= cutoff
