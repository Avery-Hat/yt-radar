# yt-radar

**yt-radar** is a Python CLI for exploring YouTube search results using real engagement data — and digging into comment text for keywords you care about.

It helps answer questions like:
- *Which videos actually have the most discussion?*
- *What videos mention specific terms in their comments?*
- *Which results are high-signal vs just popular?*

This tool is designed for research, analysis, and curiosity — not scraping or automation abuse.

---

## Features

### Search & Rank Videos
- Search YouTube across multiple pages
- Rank results by:
  - view count
  - comment count
- Filter by:
  - minimum views
  - minimum comments
  - recency (`--since 30d`)
- Output as:
  - readable tables (default)
  - JSON for further analysis

### Comment Keyword Search
- Fetch real comment text from top videos
- Search for **custom keywords** you provide
- Match:
  - **any** term
  - **all** terms
- Rank videos by keyword activity
- Show sample matching comments

---

## Requirements

- Python **3.12+** (tested, and works on 3.10, 3.12)
- Google noted py3.10 will not run after Oct 2026.
- A **YouTube Data API v3** key
- Internet connection

---

## Installation

### 1) Clone the repo
```bash
git clone https://github.com/Avery-Hat/yt-radar.git
cd yt-radar
````

### 2) Create & activate a virtual environment

Using `uv` (recommended if you have it):

```bash
uv venv .venv
source .venv/bin/activate
```

Or standard Python:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3) Install dependencies

```bash
uv pip install google-api-python-client
```

(or)

```bash
python -m pip install google-api-python-client
```

---

## API Key Setup

yt-radar uses the **YouTube Data API** and requires an API key.

1. Create a project in Google Cloud Console
2. Enable **YouTube Data API v3**
3. Create an **API key**
4. Set it as an environment variable:

```bash
export YOUTUBE_API_KEY="YOUR_API_KEY_HERE"
```

---

## Usage

All commands are run via `main.py`:

```bash
python main.py <command> [options]
```

---

## Commands

### `search`

Search YouTube and rank videos by engagement.

```bash
python main.py search "path of exile 3.21 builds"
```

**Common options:**

```bash
--pages N            # number of result pages to scan
--per-page N         # results per page (max 50)
--top N              # number of results to show
--sort views|comments
--min-views N
--min-comments N
--since 30d
--format table|json
```

**Examples:**

```bash
python main.py search "path of exile 3.21 builds" --pages 5 --top 5 --sort comments
python main.py search "path of exile 3.21 builds" --since 60d --min-views 10000
python main.py search "path of exile 3.21 builds" --format json > results.json
```

---

### `comment-terms`

Search **comment text** for keywords you specify.

```bash
python main.py comment-terms "path of exile 3.21 builds" --terms "pob,league start"
```

**Options:**

```bash
--terms "a,b,c"      # comma-separated keywords (required)
--match any|all      # match any term or all terms
--pages N            # pages of candidate videos
--per-page N         # results per page
--top-videos N       # number of videos to scan comments for
--comments N         # comments fetched per video
```

**Examples:**

```bash
python main.py comment-terms "path of exile 3.21 builds" \
  --terms "pob,league start" \
  --top-videos 10 \
  --comments 200

python main.py comment-terms "path of exile 3.21 builds" \
  --terms "nerf,buff" \
  --match all
```

---

## Notes on Quota & Performance

* YouTube API quotas apply
* `search` is relatively cheap
* `comment-terms` is more expensive:

  * cost scales with `top-videos × comments`
* Start small and increase gradually

---

## Project Status

This project is under active development.

Planned improvements:

* weighted engagement scores
* comment caching
* progress indicators
* GUI? QnA style formatting for searching instead?

---
