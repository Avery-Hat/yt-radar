# yt-radar

**yt-radar** is a Python tool for exploring YouTube search results using *engagement data* — and digging into **comment text** to surface signals that views alone don’t show.

It helps answer questions like:

- *Which videos actually have meaningful discussion?*
- *Which videos mention specific terms in their comments?*
- *Does this video actually have positive response? negative?*

This project is designed for **research, analysis, and curiosity** — not scraping or automation abuse.  
All data is fetched via the **YouTube Data API v3**.

---

## Features

### Search & Rank Videos

- Search YouTube across multiple result pages
- Rank results by:
  - view count
  - comment count
- Filter by:
  - minimum views
  - minimum comments
  - recency (e.g. `30d`)
- Output results as:
  - interactive tables (GUI)
  - JSON for further analysis

### Comment Keyword Analysis

- Fetch real comment text from top-ranked videos
- Search for **custom keywords** you provide
- Match:
  - **any** term
  - **all** terms
- Rank videos by keyword activity
- Display **sample matching comments** for context
- Show **unique comment counts per term**
  - A comment counts once per term (even if the word appears multiple times)
- Toggle a **Term Totals panel** to see keyword distribution per video
- Control how many sample comments are displayed (display-only limit)

#### Term Counting Model

Keyword counts are based on **unique comments**:

- If a keyword appears anywhere in a comment, it counts as 1.
- Repeating the same word multiple times in a single comment does not increase the count.
- This prevents spam or repeated phrases from inflating term totals.

### GUI (Primary Interface)

- Tkinter-based desktop GUI
- Combines search + comment analysis in one view
- Hover thumbnails, copy-to-clipboard URLs
- Built for **manual exploration and iteration**
- Windows `.exe` build supported
- Toggleable **Term Totals panel**
- Adjustable number of sample comments shown
- Hover video thumbnails
- Double-click to copy URL

### CLI (Shell and testing area)
- Read for_cli.txt on how to enable.
---

## Requirements

### Runtime

- **Windows** (for the `.exe`)
- Internet connection
- A **YouTube Data API v3** key

### Development (if running from source)

- Python **3.10+** (tested on 3.10 and 3.12)
  - Note: Google has announced Python 3.10 support will end after **Oct 2026**

---

## Installation

### Option A: Windows executable (recommended)

1. Download `yt-radar.exe` from the releases page
2. Double-click to launch
3. On first run, you’ll be prompted for your **own YouTube API key**

No Python installation required.

---

### Option B: Run from source (development)

#### 1) Clone the repository

```bash
git clone https://github.com/Avery-Hat/yt-radar.git
cd yt-radar
```

#### 2) Install dependencies

```bash
python -m pip install -r requirements.txt
```

---

## API Key Setup

yt-radar uses the **YouTube Data API v3** and requires an API key.

### How it works

* The API key is **never bundled** in the exe
* Each user provides **their own key**
* The key is stored locally per-user (not shared, not committed)

### Steps to get a key

1. Create a project in **Google Cloud Console**
2. Enable **YouTube Data API v3**
3. Create an **API key**

### Providing the key

#### GUI (recommended)

* On first launch, yt-radar will prompt for a key
* The key is saved locally and reused on future launches

#### Environment variable (source / CLI use)

```bash
export YOUTUBE_API_KEY="YOUR_API_KEY_HERE"
```

---

## Usage

### GUI

Launch the app (exe or source):

```bash
yt-radar.exe
# or
python main.py
```

The GUI allows you to:

* run searches
* analyze comment terms
* browse results interactively
* export JSON

---

### CLI (optional / advanced)

All CLI commands are run via `main.py`, but currently stored as `for_cli.txt`:

```bash
python cli.py <command> [options]
```

#### `search`

Search YouTube and rank videos by engagement.

```bash
python cli.py search "path of exile 3.21 builds"
```

Common options:

```bash
--pages N
--per-page N
--top N
--sort views|comments
--min-views N
--min-comments N
--since 30d
--format table|json
```

#### `comment-terms`

Search **comment text** for keywords you specify.

```bash
python cli.py comment-terms "path of exile 3.21 builds" --terms "pob,league start"
```

Options:

```bash
--terms "a,b,c"
--match any|all
--top-videos N
--comments N
```

---

## Notes on Quota & Performance

* YouTube API quotas apply
* `search` is relatively cheap
* Comment analysis is more expensive:

  * cost scales with `top-videos × comments`
* Start small and increase gradually

---

## Project Status

Stable and feature-complete. Minor things may be added in the future.

```
