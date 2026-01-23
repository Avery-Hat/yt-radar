import os

DEFAULT_PAGES = 3
DEFAULT_PER_PAGE = 50  # YouTube max is 50 for search.list
DEFAULT_TOP = 5
DEFAULT_SORT = "views"  # views | comments


def get_api_key() -> str:
    key = os.getenv("YOUTUBE_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "Missing YOUTUBE_API_KEY. Set it in your environment, e.g.\n"
            'export YOUTUBE_API_KEY="YOUR_KEY_HERE"'
        )
    return key
