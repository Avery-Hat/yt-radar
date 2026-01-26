from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

from yt_radar.models import Video
from yt_radar.youtube_client import YouTubeClient
from yt_radar.services.ranker import Ranker
from yt_radar.services.term_matcher import TermMatcher, TermQuery


@dataclass(frozen=True)
class CommentTermsResult:
    video: Video
    total_term_hits: int
    matched_comments: int
    samples: List[str]


class CommentTermsService:
    def __init__(self, yt: YouTubeClient, ranker: Ranker, matcher: TermMatcher) -> None:
        self._yt = yt
        self._ranker = ranker
        self._matcher = matcher

    def run(
        self,
        query: str,
        pages: int,
        per_page: int,
        top_videos: int,
        terms: TermQuery,
        comments_per_video: int,
    ) -> List[CommentTermsResult]:
        video_ids = self._yt.search_video_ids(query=query, pages=pages, per_page=per_page)
        videos = self._yt.fetch_videos(video_ids)

        # NOTE: your run() always ranks by views, independent of any GUI "sort"
        ranked = self._ranker.sort(videos, sort_key="views")
        ranked = ranked[: max(1, top_videos)]

        return self.run_on_videos(
            videos=ranked,
            terms=terms,
            comments_per_video=comments_per_video,
        )

    def run_on_videos(
        self,
        videos: Iterable[Video],
        terms: TermQuery,
        comments_per_video: int,
    ) -> List[CommentTermsResult]:
        """
        Term-match comments for a provided set of Video objects (no searching, no refetching).
        """
        results: List[CommentTermsResult] = []

        for v in videos:
            comments = self._yt.fetch_comment_text(v.video_id, max_comments=comments_per_video)
            total_hits, matched_count, samples = self._matcher.match(comments, terms)

            if matched_count > 0:
                results.append(
                    CommentTermsResult(
                        video=v,
                        total_term_hits=total_hits,
                        matched_comments=matched_count,
                        samples=samples,
                    )
                )

        results.sort(key=lambda r: (r.total_term_hits, r.matched_comments), reverse=True)
        return results
