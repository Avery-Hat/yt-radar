# yt-radar

**yt-radar** is a Python tool for exploring YouTube search results using *real engagement data* — and digging into **comment text** to surface signals that views alone don’t show.

It helps answer questions like:

* *Which videos actually have meaningful discussion?*
* *Which videos mention specific terms in their comments?*

This project is designed for **research, analysis, and curiosity** — not scraping or automation abuse. Uses the Youtube API.

---

## Features

### Search & Rank Videos

* Search YouTube across multiple result pages
* Rank results by:

  * view count
  * comment count
* Filter by:

  * minimum views
  * minimum comments
  * recency (e.g. `--since 30d`)
* Output results as:

  * readable tables (default)
  * JSON for further analysis

### Comment Keyword Analysis

* Fetch real comment text from top-ranked videos
* Search for **custom keywords** you provide
* Match:

  * **any** term
  * **all** terms
* Rank videos by keyword activity
* Display sample matching comments for context

### GUI (Optional)

* A Tkinter-based GUI is included for interactive exploration
* Combines search + comment analysis in one view
* Designed for manual analysis and iteration

---

## Requirements

* Python **3.10+** (tested on 3.10 and 3.12)

  * Note: Google has announced Python 3.10 support will end after **Oct 2026**
* A **YouTube Data API v3** key
* Internet connection

---

## Installation

### 1) Clone the repository

```bash
git clone https://github.com/Avery-Hat/yt-radar.git
cd yt-radar
```

---

### 2) (Optional) Create & activate a virtual environment

Using `uv` (recommended if you have it):

```bash
uv venv .venv
source .venv/bin/activate
```

Or using standard Python:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

---

### 3) Install dependencies

```bash
python -m pip install -r requirements.txt
```

(If you’re not using a requirements file yet, install the main dependency directly:)

```bash
python -m pip install google-api-python-client
```

---

## API Key Setup

yt-radar uses the **YouTube Data API v3** and requires an API key.

### Steps

1. Create a project in **Google Cloud Console**
2. Enable **YouTube Data API v3**
3. Create an **API key**

### Provide the key (recommended options)

#### Option A: Environment variable (.env file in root)

```bash
export YOUTUBE_API_KEY="YOUR_API_KEY_HERE"
```

#### Option B: Enter via GUI (if using the GUI)

* The app will prompt for a key on first launch
* The key is saved locally per-user (not committed, not shared)

---

## Usage (CLI)

All CLI commands are run via `main.py`:

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
--top N              # number of results to keep
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
