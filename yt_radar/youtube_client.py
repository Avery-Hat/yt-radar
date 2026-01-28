from __future__ import annotations

from typing import Iterable, List, Optional

from googleapiclient.discovery import build

from yt_radar.models import Video


class YouTubeClient:
    """
    Thin wrapper around YouTube Data API v3 calls.
    Responsibilities:
      - search for video IDs
      - fetch video stats in batches
    """

    def __init__(self, api_key: str) -> None:
        self._service = build("youtube", "v3", developerKey=api_key)

    def search_video_ids(self, query: str, pages: int, per_page: int) -> List[str]:
        if pages < 1:
            pages = 1
        if per_page < 1:
            per_page = 1
        if per_page > 50:
            per_page = 50

        ids: list[str] = []
        page_token: Optional[str] = None

        for _ in range(pages):
            req = (
                self._service.search()
                .list(
                    part="id",
                    q=query,
                    type="video",
                    maxResults=per_page,
                    pageToken=page_token,
                )
            )
            resp = req.execute()

            for item in resp.get("items", []):
                vid = item.get("id", {}).get("videoId")
                if vid:
                    ids.append(vid)

            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        # dedupe while preserving order
        seen = set()
        unique = []
        for vid in ids:
            if vid not in seen:
                seen.add(vid)
                unique.append(vid)
        return unique

    def fetch_videos(self, video_ids: Iterable[str]) -> List[Video]:
        vids = list(video_ids)
        if not vids:
            return []

        videos: list[Video] = []

        # videos.list accepts up to 50 IDs per request
        for chunk in _chunks(vids, 50):
            req = (
                self._service.videos()
                .list(part="snippet,statistics", id=",".join(chunk))
            )
            resp = req.execute()

            for item in resp.get("items", []):
                video_id = item.get("id", "")
                snippet = item.get("snippet", {}) or {}
                stats = item.get("statistics", {}) or {}

                title = snippet.get("title", "")
                channel_title = snippet.get("channelTitle", "")
                published_at = snippet.get("publishedAt", "")

                view_count = _safe_int(stats.get("viewCount"))
                comment_count = _safe_int(stats.get("commentCount"))

                # Some videos may have comments disabled -> commentCount missing
                videos.append(
                    Video(
                        video_id=video_id,
                        title=title,
                        channel_title=channel_title,
                        published_at=published_at,
                        view_count=view_count,
                        comment_count=comment_count,
                    )
                )

        return videos

    def fetch_comment_text(self, video_id: str, max_comments: int) -> List[str]:
        """
        Fetch up to max_comments top-level comments for a video.
        Note: comments may be disabled; returns [] then.
        """
        if max_comments < 1:
            return []

        texts: List[str] = []
        page_token: Optional[str] = None

        # API maxResults up to 100 per request for commentThreads.list
        while len(texts) < max_comments:
            batch = min(100, max_comments - len(texts))

            req = self._service.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=batch,
                pageToken=page_token,
                textFormat="plainText",
                order="relevance",  # maybe time in the futre
            )

            try:
                resp = req.execute()
            except Exception:
                # comments disabled, video unavailable, etc.
                return texts

            for item in resp.get("items", []):
                snippet = (
                    item.get("snippet", {})
                        .get("topLevelComment", {})
                        .get("snippet", {})
                )
                text = snippet.get("textDisplay")
                if text:
                    texts.append(text)

            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        return texts

def _safe_int(value) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _chunks(items: List[str], size: int) -> List[List[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]
