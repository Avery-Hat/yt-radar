from __future__ import annotations

import json
from typing import List

from yt_radar.models import Video


class JsonPrinter:
    def print(self, videos: List[Video]) -> None:
        payload = [
            {
                "video_id": v.video_id,
                "title": v.title,
                "channel_title": v.channel_title,
                "published_at": v.published_at,
                "view_count": v.view_count,
                "comment_count": v.comment_count,
                "url": v.url,
            }
            for v in videos
        ]
        print(json.dumps(payload, indent=2, ensure_ascii=False))
