from __future__ import annotations
from dataclasses import dataclass
from typing import List

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

        # limit how many videos we do comment crawling on (cost control)
        ranked = self._ranker.sort(videos, sort_key="views")
        ranked = ranked[: max(1, top_videos)]

        results: List[CommentTermsResult] = []
        for v in ranked:
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

        # sort results by term hits then matched comments
        results.sort(key=lambda r: (r.total_term_hits, r.matched_comments), reverse=True)
        return results
