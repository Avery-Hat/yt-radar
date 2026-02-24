# yt-radar

**yt-radar** is a desktop YouTube analysis tool that ranks videos by engagement and explores comments to find well developed videos beyond raw view counts.

It helps answer questions like:

* Which videos actually generate discussion?
* Which videos mention specific keywords in comments?
* How often do certain terms appear — across all videos or within a single video?

All data is fetched via the **YouTube Data API v3**.

---

## Motivation

Most YouTube tools focus on views or subscriber counts. But views don’t tell you:

* Is there engagement?
* Is a video taking positive or negative reception? 
* Are there certain qualities or issues with the video? 

`yt-radar` was built to explore **comment based reception**:

* Rank by views *or* comments
* Filter low-signal content (min views, min comments)
* Analying and comparing comments between videos.
* Count keyword presence per comment (unique comment counts)
* Surface sample comments for qualitative insight

The goal is research and exploration. Analyzing reception. 

---

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/Avery-Hat/yt-radar.git
cd yt-radar
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv .venv
source .venv/bin/activate   # Linux / macOS
.venv\Scripts\activate      # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the app

```bash
python main.py
```

On first launch, you’ll be prompted for a **YouTube Data API key**.
It will be stored locally for future runs. Location: %APPDATA%/yt-radar/.

---

## Usage

### Search & Ranking

* **Query** – What to search for
* **Pages / Per Page** – How many results to fetch from YouTube
* **Top Results (display)** – How many ranked videos to show
* **Min Views / Min Comments** – Filter low-signal content
* **Since (e.g. 30d)** – Only include recent uploads

You can run:

* **Run Query Only** → Search + rank only
* **Run Full Analysis** → Search + comment keyword analysis

---

### Comment Keyword Analysis

* **Terms** – Comma-separated keywords
* **Match**:

  * `any` → at least one term must appear
  * `all` → all terms must appear
* **Videos to Analyze** – How many top videos to fetch comments from
* **Comments/video** – Maximum comments to fetch per video
* **Samples to show** – How many sample matching comments to display
* **Show term totals** – Displays per-term unique comment counts

#### Term Totals (Unique Comments)

Each term counts **once per comment**, even if repeated.

Example:

> "amazing amazing amazing" → counts as 1 unique comment for "amazing"

You can:

* Click a row → view term totals for that video
* Click empty space → reset to global totals
* Select a row then double click it to copy the youtube link
---

### Export

* **Export JSON** saves search + analysis results for further processing.

---

## Contributing

Contributions are welcome.

### Areas for improvement

* Performance optimization
* Better quota usage

### How to contribute

1. Fork the repository
2. Create a feature branch
3. Make changes with clear commit messages
4. Open a pull request describing the improvement

---
