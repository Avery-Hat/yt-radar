from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List
from collections import Counter
from typing import Iterable, List, Dict

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
    per_term_unique_comments: Dict[str, int]  # NEW

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

        results, _term_totals = self.run_on_videos(
            videos=ranked,
            terms=terms,
            comments_per_video=comments_per_video,
        )
        return results


    def run_on_videos(
        self,
        videos: Iterable[Video],
        terms: TermQuery,
        comments_per_video: int,
    ) -> tuple[List[CommentTermsResult], dict[str, int]]:
        """
        Term-match comments for a provided set of Video objects (no searching, no refetching).
        Returns:
        - per-video results (sorted)
        - global term totals: "unique comments containing term" counts
        """
        results: List[CommentTermsResult] = []

        term_totals: Counter[str] = Counter()
        needle_terms = [t.strip() for t in terms.terms if t and t.strip()]
        needle_terms_lc = [(t, t.lower()) for t in needle_terms]

        for v in videos:
            comments = self._yt.fetch_comment_text(v.video_id, max_comments=comments_per_video)

            # added: count each term at most once per comment (global totals)
            per_video_totals: Counter[str] = Counter()

            for c in comments:
                text_lc = (c or "").lower()
                for original, t_lc in needle_terms_lc:
                    if t_lc and t_lc in text_lc:
                        per_video_totals[original] += 1
                        term_totals[original] += 1


            total_hits, matched_count, samples = self._matcher.match(comments, terms)

            if matched_count > 0:
                results.append(
                    CommentTermsResult(
                        video=v,
                        total_term_hits=total_hits,
                        matched_comments=matched_count,
                        samples=samples,
                        per_term_unique_comments=dict(per_video_totals),
                    )
                )

        results.sort(key=lambda r: (r.total_term_hits, r.matched_comments), reverse=True)
        return results, dict(term_totals)
