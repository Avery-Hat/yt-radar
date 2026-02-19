from __future__ import annotations

from typing import List, Optional

from yt_radar.models import Video
from yt_radar.youtube_client import YouTubeClient
from yt_radar.services.filtering import Filters, VideoFilter


class SearchService:
    def __init__(self, yt: YouTubeClient, vfilter: VideoFilter | None = None) -> None:
        self._yt = yt
        self._filter = vfilter or VideoFilter()

    def search(
        self,
        query: str,
        pages: int,
        per_page: int,
        top: int,
        filters: Optional[Filters] = None,
    ) -> List[Video]:
        video_ids = self._yt.search_video_ids(query=query, pages=pages, per_page=per_page)
        videos = self._yt.fetch_videos(video_ids)

        if filters:
            videos = self._filter.apply(videos, filters)

        if top < 1:
            top = 1
        return videos[:top]
