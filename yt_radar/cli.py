import argparse

from yt_radar.config import (
    DEFAULT_PAGES,
    DEFAULT_PER_PAGE,
    DEFAULT_SORT,
    DEFAULT_TOP,
    get_api_key,
)
from yt_radar.output.table import TablePrinter
from yt_radar.services.ranker import Ranker
from yt_radar.services.search_service import SearchService
from yt_radar.youtube_client import YouTubeClient
# for jsonout located in output
from yt_radar.output.json_out import JsonPrinter
from yt_radar.services.filtering import Filters, VideoFilter
# for searching comments by terms
from yt_radar.services.comment_terms_service import CommentTermsService
from yt_radar.services.term_matcher import TermMatcher, TermQuery
from yt_radar.output.comment_terms_table import CommentTermsTablePrinter




def run() -> None:
    parser = argparse.ArgumentParser(
        prog="yt-radar",
        description="Search YouTube and rank results by engagement (views/comments).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search", help="Search YouTube and print top results.")
    search.add_argument("query", help="Search query string.")
    search.add_argument("--pages", type=int, default=DEFAULT_PAGES, help="Number of pages to scan.")
    search.add_argument("--per-page", type=int, default=DEFAULT_PER_PAGE, help="Results per page (max 50).")
    search.add_argument("--top", type=int, default=DEFAULT_TOP, help="How many results to print.")
    search.add_argument(
        "--sort",
        choices=["views", "comments"],
        default=DEFAULT_SORT,
        help="Sort results by this field.",
    )
    search.add_argument("--min-views", type=int, default=0, help="Filter out videos with fewer views.")
    search.add_argument("--min-comments", type=int, default=0, help="Filter out videos with fewer comments.")
    search.add_argument("--since", type=str, default="", help='Only include videos from the last N days (e.g. "30d").')
    search.add_argument("--format", choices=["table", "json"], default="table", help="Output format.")

    ct = sub.add_parser("comment-terms", help="Search comment text for keywords.")
    ct.add_argument("query", help="Search query string (used to find candidate videos).")
    ct.add_argument("--terms", required=True, help='Comma-separated keywords, e.g. "pob,league start"')
    ct.add_argument("--match", choices=["any", "all"], default="any", help="Match any term or all terms.")
    ct.add_argument("--pages", type=int, default=2)
    ct.add_argument("--per-page", type=int, default=25)
    ct.add_argument("--top-videos", type=int, default=10, help="How many videos to scan comments for.")
    ct.add_argument("--comments", type=int, default=200, help="How many comments to fetch per video.")



    args = parser.parse_args()

    if args.command == "search":
        _handle_search(args)
    elif args.command == "comment-terms":
        _handle_comment_terms(args)



def _handle_search(args: argparse.Namespace) -> None:
    api_key = get_api_key()
    yt = YouTubeClient(api_key=api_key)
    ranker = Ranker()
    svc = SearchService(yt=yt, ranker=ranker, vfilter=VideoFilter())

    since_days = _parse_days(args.since)  # implement below
    filters = Filters(
        min_views=max(0, args.min_views),
        min_comments=max(0, args.min_comments),
        since_days=since_days,
    )

    videos = svc.search(
        query=args.query,
        pages=args.pages,
        per_page=args.per_page,
        top=args.top,
        sort=args.sort,
        filters=filters,
    )

    if args.format == "json":
        JsonPrinter().print(videos)
    else:
        TablePrinter().print(videos)

def _parse_days(s: str):
    s = (s or "").strip().lower()
    if not s:
        return None
    if s.endswith("d"):
        s = s[:-1]
    try:
        return int(s)
    except Exception:
        return None

def _handle_comment_terms(args: argparse.Namespace) -> None:
    api_key = get_api_key()
    yt = YouTubeClient(api_key=api_key)

    terms = tuple(t.strip() for t in args.terms.split(",") if t.strip())
    tq = TermQuery(terms=terms, mode=args.match)

    svc = CommentTermsService(yt=yt, ranker=Ranker(), matcher=TermMatcher())
    results = svc.run(
        query=args.query,
        pages=args.pages,
        per_page=args.per_page,
        top_videos=args.top_videos,
        terms=tq,
        comments_per_video=args.comments,
    )

    CommentTermsTablePrinter().print(results)
