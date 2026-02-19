from __future__ import annotations

import io
import json
import re
import threading
import tkinter as tk
import urllib.request
from queue import Queue, Empty
from tkinter import ttk, messagebox, filedialog, simpledialog
from collections import Counter

from PIL import Image, ImageTk

from yt_radar.config import get_api_key, save_api_key, load_setting, save_setting
from yt_radar.models import Video
from yt_radar.services.filtering import Filters, VideoFilter
from yt_radar.services.ranker import Ranker
from yt_radar.services.search_service import SearchService
from yt_radar.services.comment_terms_service import CommentTermsService, CommentTermsResult
from yt_radar.services.term_matcher import TermMatcher, TermQuery
from yt_radar.youtube_client import YouTubeClient


def run_gui() -> None:
    app = YTRadarApp()
    app.mainloop()


_UNI_ESC_RE = re.compile(r"\\u([0-9a-fA-F]{4})|\\U([0-9a-fA-F]{8})")

def decode_unicode_escapes(s: str) -> str:
    if not s:
        return s

    def repl(m: re.Match) -> str:
        hex4 = m.group(1)
        hex8 = m.group(2)
        codepoint = int(hex4 or hex8, 16)
        try:
            return chr(codepoint)
        except Exception:
            return m.group(0)

    # Only converts *literal* backslash-u sequences; leaves real emojis alone.
    return _UNI_ESC_RE.sub(repl, s)




class HelpDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, on_close) -> None:
        super().__init__(parent)
        self.title("yt-radar help")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()  # modal

        self._dont_show = tk.BooleanVar(value=False)
        self._on_close = on_close

        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)

        help_text = (
            "What the controls mean:\n\n"
            "Search:\n"
            "  Query: What you want to search on YouTube.\n"
            "  Pages / Per page: How many candidates to pull from YouTube.\n"
            "  Sort: How to rank candidates (views or comments).\n"
            "  Top Results (display): How many ranked videos you keep/show in the table.\n\n"
            "Filters:\n"
            "  Min Views / Min Comments: Remove low-signal videos before ranking.\n"
            "  Since: Only keep videos newer than N days (e.g. 30d).\n\n"
            "Comment analysis:\n"
            "  Terms: Comma-separated keywords to look for in comments.\n"
            "  Match: any = at least one term, all = must contain all terms.\n"
            "  Videos to Analyze: How many of the top results to crawl comments for.\n"
            "  Comments/video: Max comments to fetch per video.\n\n"
            "Term totals (unique comments):\n"
            "  Show term totals: Toggles the totals panel.\n"
            "  Counts are 'unique comments' per term:\n"
            "    - If a term appears anywhere in a comment, it counts as 1 for that comment.\n"
            "    - Example: a comment saying 'amazing' 20 times still counts as 1.\n"
            "  Interaction:\n"
            "    - Click a result row to show totals for that selected video.\n"
            "    - Click empty space in the results table to reset back to global totals.\n\n"
            "Bottom panel (sample matching comments):\n"
            "  Samples to show: How many sample matching comments to display for the selected row.\n"
            "  (This only affects display; fetching is controlled by Comments/video.)\n\n"
            "Results columns:\n"
            "  Hits = total term occurrences.\n"
            "  Matched comments = number of comments containing your terms.\n\n"
            "Tips:\n"
            "- Start small (e.g. 2 pages, 5 videos, 100 comments) to save quota.\n"
            "- Double-click a row to copy the URL.\n"
        )

        text = tk.Text(frame, width=72, height=20, wrap="word", font="TkTextFont")
        text.insert("1.0", help_text)
        text.configure(state="disabled")
        text.grid(row=0, column=0, columnspan=3, sticky="nsew", pady=(0, 10))

        # Left: checkbox
        chk = ttk.Checkbutton(frame, text="Do not show this again", variable=self._dont_show)
        chk.grid(row=1, column=0, sticky="w")

        # Middle: reset button (icon-style)
        reset_btn = ttk.Button(frame, text="Reset help tips", command=self._reset_help_tips)
        reset_btn.grid(row=1, column=1, sticky="e", padx=(8, 8))

        # Right: close button
        btn = ttk.Button(frame, text="Close", command=self._close)
        btn.grid(row=1, column=2, sticky="e")

        frame.columnconfigure(0, weight=1)

        # center dialog on parent
        self.update_idletasks()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        w = self.winfo_width()
        h = self.winfo_height()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{x}+{y}")

        self.protocol("WM_DELETE_WINDOW", self._close)

    def _reset_help_tips(self) -> None:
        # Make sure the next app launch shows help again
        save_setting("hide_help_on_start", False)

        # Also uncheck this in the current dialog so it's consistent
        self._dont_show.set(False)

        messagebox.showinfo("Help tips reset", "Help will show again next time you start the app.")

    def _close(self) -> None:
        self.grab_release()
        self.destroy()
        self._on_close(bool(self._dont_show.get()))



class ThumbnailHover:
    """
    Hover tooltip that shows a YouTube thumbnail for the row under the mouse.
    Caches thumbnails by video_id to avoid re-downloading.
    """

    _YOUTUBE_ID_RE = re.compile(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})")

    def __init__(self, root: tk.Tk, tree: ttk.Treeview, get_video_id_from_row) -> None:
        self.root = root
        self.tree = tree
        self.get_video_id_from_row = get_video_id_from_row

        self._tip: tk.Toplevel | None = None
        self._label: tk.Label | None = None

        self._current_row: str | None = None
        self._after_id: str | None = None

        self._cache: dict[str, ImageTk.PhotoImage] = {}
        self._pending: set[str] = set()

        self.tree.bind("<Motion>", self._on_motion, add=True)
        self.tree.bind("<Leave>", self._on_leave, add=True)
        self.tree.bind("<ButtonPress>", self._on_leave, add=True)  # hide on click/selection

    def _on_motion(self, event) -> None:
        row = self.tree.identify_row(event.y)

        if row != self._current_row:
            self._current_row = row
            self._cancel_scheduled()
            self._hide_tip()

            if row:
                self._after_id = self.root.after(350, lambda: self._show_for_row(row, event))

    def _on_leave(self, _event=None) -> None:
        self._current_row = None
        self._cancel_scheduled()
        self._hide_tip()

    def _cancel_scheduled(self) -> None:
        if self._after_id is not None:
            try:
                self.root.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show_for_row(self, row: str, event) -> None:
        vid = self.get_video_id_from_row(row)
        if not vid:
            return

        if self._tip is None or not self._tip.winfo_exists():
            self._tip = tk.Toplevel(self.root)
            self._tip.wm_overrideredirect(True)
            self._tip.attributes("-topmost", True)

            self._label = tk.Label(self._tip, text="Loading…", relief="solid", borderwidth=1)
            self._label.pack()

        x = self.root.winfo_pointerx() + 15
        y = self.root.winfo_pointery() + 15
        self._tip.geometry(f"+{x}+{y}")

        if vid in self._cache:
            self._label.configure(image=self._cache[vid], text="")
            self._label.image = self._cache[vid]
            return

        if vid in self._pending:
            return

        self._pending.add(vid)
        self._label.configure(text="Loading…", image="")

        def worker():
            try:
                url = f"https://img.youtube.com/vi/{vid}/hqdefault.jpg"
                with urllib.request.urlopen(url, timeout=8) as resp:
                    data = resp.read()

                img = Image.open(io.BytesIO(data))
                img.thumbnail((320, 180))
                photo = ImageTk.PhotoImage(img)

                def on_main():
                    self._cache[vid] = photo
                    self._pending.discard(vid)
                    if self._tip and self._tip.winfo_exists() and self._label:
                        self._label.configure(image=photo, text="")
                        self._label.image = photo

                self.root.after(0, on_main)
            except Exception:

                def on_main_fail():
                    self._pending.discard(vid)
                    if self._tip and self._tip.winfo_exists() and self._label:
                        self._label.configure(text="(thumbnail unavailable)", image="")

                self.root.after(0, on_main_fail)

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def _extract_video_id_from_url(url: str) -> str | None:
        if not url:
            return None
        m = ThumbnailHover._YOUTUBE_ID_RE.search(url)
        return m.group(1) if m else None

    def _hide_tip(self) -> None:
        if self._tip and self._tip.winfo_exists():
            self._tip.destroy()
        self._tip = None
        self._label = None


class YTRadarApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("yt-radar")
        self.geometry("1280x720")

        # styling (kept simple, no scaling)
        self._style = ttk.Style(self)
        try:
            self._style.theme_use("clam")
        except Exception:
            pass
        self._style.configure("Treeview", rowheight=22)
        self._style.configure("Treeview.Heading", font=("TkDefaultFont", 10, "bold"))

        # ---- API key ----
        try:
            api_key = get_api_key()
        except Exception:
            api_key = simpledialog.askstring(
                "YouTube API Key Required",
                "Enter your YouTube Data API key.\n\nIt will be saved on this computer for next time.",
                show="*",
            )
            if not api_key:
                messagebox.showerror("Missing API Key", "No API key provided. Exiting.")
                self.destroy()
                return
            save_api_key(api_key)

        self._yt = YouTubeClient(api_key=api_key)
        self._ranker = Ranker()
        self._search_service = SearchService(yt=self._yt, ranker=self._ranker, vfilter=VideoFilter())
        self._comment_terms_service = CommentTermsService(yt=self._yt, ranker=self._ranker, matcher=TermMatcher())
        self._last_term_totals: dict[str, int] = {} #new: comment total

        self._q: Queue = Queue()

        self._videos: list[Video] = []
        self._comment_results: list[CommentTermsResult] = []
        self._combined_results: list[CommentTermsResult] = []
        self._analysis_by_video_id: dict[str, CommentTermsResult] = {}

        # Header (help only; scaling buttons removed)
        header = ttk.Frame(self)
        header.pack(fill="x", padx=10, pady=(10, 0))
        ttk.Button(header, text="?", width=3, command=self._open_help).pack(side="right", padx=(0, 8))

        self._build_ui()

        self.after(0, self._maybe_show_help_on_start)
        self.after(100, self._poll_queue)

    # -----------------------------
    # UI
    # -----------------------------
    def _build_ui(self) -> None:
        content = ttk.Frame(self)
        content.pack(fill="both", expand=True)

        self.params = UnifiedParamsFrame(
            content,
            on_run_search=self._run_search_only,
            on_run_combined=self._run_combined,
            on_export=self._export_search_json,
        )
        self.params.pack(fill="x", padx=10, pady=(6, 6))

        self._build_results_area(parent=content)

        # start of new code: for comment unique terms counter
        self.term_totals_frame = ttk.LabelFrame(content, text="Term totals (unique comments)")
        self.term_totals_frame.pack(fill="x", padx=10, pady=(0, 6))

        self.term_totals_tree = ttk.Treeview(
            self.term_totals_frame,
            columns=("term", "count"),
            show="headings",
            height=4,
        )
        self.term_totals_tree.heading("term", text="term")
        self.term_totals_tree.heading("count", text="unique comments")
        self.term_totals_tree.column("term", width=200)
        self.term_totals_tree.column("count", width=140, anchor="e")
        self.term_totals_tree.pack(fill="x", padx=6, pady=6)
        # end of new code 

        self.sample_box = tk.Text(content, height=9, wrap="word")
        self.sample_box.insert("1.0", "Select a row to view sample matching comments (when available).\n")
        self.sample_box.configure(state="disabled")
        self.sample_box.pack(fill="x", padx=10, pady=(0, 10))

        self._status = tk.StringVar(value="Ready")
        status_bar = ttk.Label(self, textvariable=self._status, anchor="w")
        status_bar.pack(side="bottom", fill="x")

        self._configure_results_stable()

    def _build_results_area(self, parent) -> None:
        self.results_frame = ttk.LabelFrame(parent, text="Results (double-click row to copy URL)")
        self.results_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.tree = ttk.Treeview(self.results_frame, columns=(), show="headings")

        yscroll = ttk.Scrollbar(self.results_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)

        self.tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")

        self.tree.bind("<Double-1>", self._copy_selected_url)
        self.tree.bind("<<TreeviewSelect>>", self._on_select_row)
        self.tree.bind("<Button-1>", self._on_tree_click, add=True)


        def get_video_id_for_row(row_id: str) -> str | None:
            values = self.tree.item(row_id, "values")
            if not values:
                return None
            url = values[-1]
            return ThumbnailHover._extract_video_id_from_url(url)

        self._thumb_hover = ThumbnailHover(self, self.tree, get_video_id_for_row)

    def _open_help(self) -> None:
        def on_close(dont_show_again: bool) -> None:
            if dont_show_again:
                save_setting("hide_help_on_start", True)

        HelpDialog(self, on_close=on_close)

    def _maybe_show_help_on_start(self) -> None:
        hide = bool(load_setting("hide_help_on_start", False))
        if not hide:
            self._open_help()

    def _set_status(self, msg: str) -> None:
        if hasattr(self, "_status") and self._status is not None:
            self._status.set(msg)

    # -----------------------------
    # reset selection on click
    # -----------------------------

    def _on_tree_click(self, event) -> None:
        row = self.tree.identify_row(event.y)
        if row:
            return  # normal selection will happen and _on_select_row will fire

        # clicked empty area -> reset to global totals + clear samples
        self.tree.selection_remove(self.tree.selection())
        self._set_samples("Select a row to view sample matching comments (when available).\n")

        show = bool(self.params.show_term_totals_var.get())
        self._set_term_totals_visible(show)
        if show and self._last_term_totals:
            self._render_term_totals(self._last_term_totals)
        else:
            self._clear_term_totals()


    # -----------------------------
    # Background runner
    # -----------------------------
    def _run_in_thread(self, fn, payload: dict, task_name: str) -> None:
        def worker():
            try:
                result = fn(**payload)
                self._q.put(("ok", task_name, result))
            except Exception as e:
                self._q.put(("err", task_name, str(e)))

        self._set_status(f"Running {task_name}…")
        threading.Thread(target=worker, daemon=True).start()

    def _poll_queue(self) -> None:
        try:
            while True:
                status, task_name, data = self._q.get_nowait()

                if status != "ok":
                    self._set_status("Error.")
                    messagebox.showerror(f"{task_name} failed", data)
                    continue

                if task_name == "search_only":
                    self._videos = data
                    self._combined_results = []
                    self._analysis_by_video_id = {}
                    self._last_term_totals = {}

                    self._render_search_as_stable(self._videos)
                    self._set_samples("Select a row to view sample matching comments (when available).\n")

                    # hide/clear term totals for search-only
                    self._set_term_totals_visible(False)
                    self._clear_term_totals()

                    self._set_status("Search complete.")

                elif task_name == "combined":
                    term_totals: dict[str, int] = {}

                    if isinstance(data, tuple) and len(data) == 3:
                        videos, results, term_totals = data
                    else:
                        videos, results = data

                    self._videos = videos
                    self._combined_results = results
                    self._analysis_by_video_id = {r.video.video_id: r for r in results}

                    self._render_comment_results_as_stable(self._combined_results)

                    self._last_term_totals = dict(term_totals or {})
                    show = bool(self.params.show_term_totals_var.get())
                    self._set_term_totals_visible(show)

                    if show and self._last_term_totals:
                        self._render_term_totals(self._last_term_totals)
                    else:
                        self._clear_term_totals()

                    self._set_status("Analysis complete.")

        except Empty:
            pass

        self.after(100, self._poll_queue)


    # -----------------------------
    # Parameter parsing + service calls
    # -----------------------------
    def _get_filters(self, params: dict) -> Filters:
        return Filters(
            min_views=params["min_views"],
            min_comments=params["min_comments"],
            since_days=params["since_days"],
        )

    def _make_term_query(self, params: dict) -> TermQuery:
        terms = tuple(t.strip() for t in params["terms"].split(",") if t.strip())
        return TermQuery(terms=terms, mode=params["match"])

    def _run_search_only(self, params: dict) -> None:
        payload = {
            "query": params["query"],
            "pages": params["pages"],
            "per_page": params["per_page"],
            "top": params["top"],
            "sort": params["sort"],
            "filters": self._get_filters(params),
        }
        self._run_in_thread(self._search_service.search, payload, "search_only")

    def _run_combined(self, params: dict) -> None:
        """
        Combined = Search (filters+sort+top) -> pick top_videos -> term match on those videos.
        """

        def combined_worker():
            videos = self._search_service.search(
                query=params["query"],
                pages=params["pages"],
                per_page=params["per_page"],
                top=params["top"],
                sort=params["sort"],
                filters=self._get_filters(params),
            )

            picked = videos[: max(1, min(params["top_videos"], len(videos)))]
            tq = self._make_term_query(params)

            results, term_totals = self._comment_terms_service.run_on_videos(
                videos=picked,
                terms=tq,
                comments_per_video=params["comments_per_video"],
            )

            return videos, results, term_totals

        def worker():
            try:
                out = combined_worker()
                self._q.put(("ok", "combined", out))
            except Exception as e:
                self._q.put(("err", "combined", str(e)))

        self._set_status("Running analysis...")
        threading.Thread(target=worker, daemon=True).start()

    # -----------------------------
    # NEW: adding comment counter
    # -----------------------------
    def _clear_term_totals(self) -> None:
        if hasattr(self, "term_totals_tree"):
            for row in self.term_totals_tree.get_children():
                self.term_totals_tree.delete(row)

    def _render_term_totals(self, totals: dict[str, int]) -> None:
        self._clear_term_totals()
        # sorted: highest first
        for term, n in sorted(totals.items(), key=lambda kv: (-kv[1], kv[0].lower())):
            self.term_totals_tree.insert("", "end", values=(term, f"{n:,}"))

    def _set_term_totals_visible(self, visible: bool) -> None:
        if not hasattr(self, "term_totals_frame"):
            return
        if visible:
            self.term_totals_frame.pack(fill="x", padx=10, pady=(0, 6))
        else:
            self.term_totals_frame.pack_forget()


    # -----------------------------
    # Results table (stable columns)
    # -----------------------------
    def _clear_tree(self) -> None:
        for row in self.tree.get_children():
            self.tree.delete(row)

    def _configure_results_stable(self) -> None:
        cols = ("hits", "matched_comments", "views", "comments", "title", "url")
        self.tree["columns"] = cols
        for c in cols:
            self.tree.heading(c, text=c)

        # fixed widths (no scaling)
        self.tree.column("hits", width=80, anchor="e")
        self.tree.column("matched_comments", width=130, anchor="e")
        self.tree.column("views", width=90, anchor="e")
        self.tree.column("comments", width=90, anchor="e")
        self.tree.column("title", width=420)
        self.tree.column("url", width=420)

    def _render_search_as_stable(self, videos: list[Video]) -> None:
        self._clear_tree()
        for v in videos:
            self.tree.insert(
                "",
                "end",
                values=(
                    "",  # hits
                    "",  # matched_comments
                    f"{v.view_count:,}",
                    f"{v.comment_count:,}",
                    v.title,
                    v.url,
                ),
            )

    def _render_comment_results_as_stable(self, results: list[CommentTermsResult]) -> None:
        self._clear_tree()
        for r in results:
            v = r.video
            self.tree.insert(
                "",
                "end",
                values=(
                    r.total_term_hits,
                    r.matched_comments,
                    f"{v.view_count:,}",
                    f"{v.comment_count:,}",
                    v.title,
                    v.url,
                ),
            )

    # -----------------------------
    # Interactions: copy URL, show samples
    # -----------------------------
    def _copy_selected_url(self, _evt=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return

        values = self.tree.item(sel[0], "values")
        if not values:
            return

        url = values[-1]
        if not url:
            messagebox.showinfo("No URL", "No URL found for selected row.")
            return

        self.clipboard_clear()
        self.clipboard_append(url)
        self.update()
        messagebox.showinfo("Copied", f"URL copied to clipboard:\n{url}")

    def _on_select_row(self, _evt=None) -> None:
        """
        Samples exist for comment term results (comment-only and combined).
        If the current table was a search-only run, samples won't exist.
        """
        sel = self.tree.selection()
        if not sel:
            return

        idx = self.tree.index(sel[0])

        backing: list[CommentTermsResult] | None = None
        if self._combined_results and len(self._combined_results) == len(self.tree.get_children()):
            backing = self._combined_results
        elif self._comment_results and len(self._comment_results) == len(self.tree.get_children()):
            backing = self._comment_results

        if not backing or idx < 0 or idx >= len(backing):
            self._set_samples("No matching comment samples for this row.\n")
            return

        r = backing[idx]

        show = bool(self.params.show_term_totals_var.get())
        if show and getattr(r, "per_term_unique_comments", None):
            self._set_term_totals_visible(True)
            self._render_term_totals(r.per_term_unique_comments)

        text = f"{r.video.title}\n{r.video.url}\n\n"
        if not r.samples:
            text += "(No samples captured.)\n"
        else:
            limit = self.params.get_samples_to_show()
            samples = r.samples if limit <= 0 else r.samples[:limit]

            for s in samples:
                s = decode_unicode_escapes(s)
                text += f"- {s.strip()}\n\n"

        self._set_samples(text)

    def _set_samples(self, text: str) -> None:
        self.sample_box.configure(state="normal")
        self.sample_box.delete("1.0", "end")
        self.sample_box.insert("1.0", text or "")
        self.sample_box.configure(state="disabled")

    # -----------------------------
    # Export (search results only)
    # -----------------------------
    def _export_search_json(self) -> None:
        if not self._videos:
            messagebox.showinfo("No Results", "Run a search or analysis first.")
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            title="Save results.json",
        )
        if not path:
            return

        payload = []
        for v in self._videos:
            item = {
                "video_id": v.video_id,
                "title": v.title,
                "channel_title": v.channel_title,
                "published_at": v.published_at,
                "view_count": v.view_count,
                "comment_count": v.comment_count,
                "url": v.url,
            }

            r = self._analysis_by_video_id.get(v.video_id)
            if r:
                item["comment_analysis"] = {
                    "term_hits": r.total_term_hits,
                    "matched_comments": r.matched_comments,
                    "samples": r.samples,
                }

            payload.append(item)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

        messagebox.showinfo("Saved", f"Saved {len(payload)} results to:\n{path}")


class UnifiedParamsFrame(ttk.LabelFrame):
    """
    One panel containing everything:
    - Search params (query/pages/per_page/sort/top + filters)
    - Comment terms params (terms/match/top_videos/comments_per_video)
    """

    def __init__(self, parent, on_run_search, on_run_combined, on_export) -> None:
        super().__init__(parent, text="Query Parameters")
        self._on_run_search = on_run_search
        self._on_run_combined = on_run_combined
        self._on_export = on_export

        self.query_var = tk.StringVar()
        self.pages_var = tk.IntVar(value=3)
        self.per_page_var = tk.IntVar(value=50)

        self.top_var = tk.IntVar(value=5)
        self.sort_var = tk.StringVar(value="views")

        self.min_views_var = tk.IntVar(value=0)
        self.min_comments_var = tk.IntVar(value=0)
        self.since_var = tk.StringVar(value="")  # "30d"

        self.terms_var = tk.StringVar()
        self.match_var = tk.StringVar(value="any")
        self.top_videos_var = tk.IntVar(value=10)
        self.comments_per_video_var = tk.IntVar(value=200)

        self.show_term_totals_var = tk.BooleanVar(value=True) #creating counter for comment terms (limited 1 per comment)
        self.samples_to_show_var = tk.IntVar(value=10) #added variable for modifiable sample comments shown.

        self.samples_spinbox: ttk.Spinbox | None = None

        self._build()

    def _build(self) -> None:
        #new: allowing total comment samples to be modifiable
        ttk.Label(self, text="Samples to show").grid(row=4, column=4, sticky="w", padx=6, pady=6)

        self.samples_spinbox = ttk.Spinbox(
            self,
            from_=0,
            to=200,
            textvariable=self.samples_to_show_var,
            width=8,
        )
        self.samples_spinbox.grid(row=4, column=5, sticky="w", padx=6, pady=6)


        ttk.Label(self, text="Query").grid(row=0, column=0, sticky="w", padx=6, pady=6)
        ttk.Entry(self, textvariable=self.query_var, width=60).grid(
            row=0, column=1, columnspan=9, sticky="we", padx=6, pady=6
        )

        ttk.Label(self, text="Pages").grid(row=1, column=0, sticky="w", padx=6, pady=6)
        ttk.Spinbox(self, from_=1, to=50, textvariable=self.pages_var, width=6).grid(
            row=1, column=1, sticky="w", padx=6, pady=6
        )

        ttk.Label(self, text="Per Page").grid(row=1, column=2, sticky="w", padx=6, pady=6)
        ttk.Spinbox(self, from_=1, to=50, textvariable=self.per_page_var, width=6).grid(
            row=1, column=3, sticky="w", padx=6, pady=6
        )

        ttk.Label(self, text="Top Results (display)").grid(row=1, column=4, sticky="w", padx=6, pady=6)
        ttk.Spinbox(self, from_=1, to=200, textvariable=self.top_var, width=6).grid(
            row=1, column=5, sticky="w", padx=6, pady=6
        )

        ttk.Label(self, text="Sort").grid(row=1, column=6, sticky="w", padx=6, pady=6)
        ttk.Combobox(self, textvariable=self.sort_var, values=["views", "comments"], width=10, state="readonly").grid(
            row=1, column=7, sticky="w", padx=6, pady=6
        )

        ttk.Label(self, text="Min Views").grid(row=2, column=0, sticky="w", padx=6, pady=6)
        ttk.Entry(self, textvariable=self.min_views_var, width=10).grid(row=2, column=1, sticky="w", padx=6, pady=6)

        ttk.Label(self, text="Min Comments").grid(row=2, column=2, sticky="w", padx=6, pady=6)
        ttk.Entry(self, textvariable=self.min_comments_var, width=10).grid(row=2, column=3, sticky="w", padx=6, pady=6)

        ttk.Label(self, text='Since (e.g. "30d")').grid(row=2, column=4, sticky="w", padx=6, pady=6)
        ttk.Entry(self, textvariable=self.since_var, width=12).grid(row=2, column=5, sticky="w", padx=6, pady=6)

        ttk.Label(self, text="Terms (comma-separated)").grid(row=3, column=0, sticky="w", padx=6, pady=6)
        ttk.Entry(self, textvariable=self.terms_var, width=40).grid(
            row=3, column=1, columnspan=5, sticky="we", padx=6, pady=6
        )

        ttk.Label(self, text="Match").grid(row=3, column=6, sticky="w", padx=6, pady=6)
        ttk.Combobox(self, textvariable=self.match_var, values=["any", "all"], width=10, state="readonly").grid(
            row=3, column=7, sticky="w", padx=6, pady=6
        )

        ttk.Label(self, text="Videos to Analyze (comments)").grid(row=4, column=0, sticky="w", padx=6, pady=6)
        ttk.Spinbox(self, from_=1, to=200, textvariable=self.top_videos_var, width=8).grid(
            row=4, column=1, sticky="w", padx=6, pady=6
        )

        ttk.Label(self, text="Comments/video").grid(row=4, column=2, sticky="w", padx=6, pady=6)
        ttk.Spinbox(self, from_=1, to=2000, textvariable=self.comments_per_video_var, width=8).grid(
            row=4, column=3, sticky="w", padx=6, pady=6
        )

        ttk.Button(self, text="Run Query Only", command=self._run_search).grid(
            row=5, column=7, sticky="e", padx=6, pady=6
        )
        ttk.Button(self, text="Run Full Analysis", command=self._run_combined).grid(
            row=5, column=9, sticky="e", padx=6, pady=6
        )
        ttk.Button(self, text="Export JSON", command=self._on_export).grid(
            row=5, column=6, sticky="e", padx=6, pady=6
        )
        # adding button for comments terms amount (1 per comment)
        ttk.Checkbutton(
            self,
            text="Show term totals",
            variable=self.show_term_totals_var,
        ).grid(row=5, column=0, sticky="w", padx=6, pady=6)


        self.columnconfigure(1, weight=1)
        self.columnconfigure(9, weight=1)

    def _parse_days(self, s: str):
        s = (s or "").strip().lower()
        if not s:
            return None
        if s.endswith("d"):
            s = s[:-1]
        try:
            return int(s)
        except Exception:
            return None

    def _base_validate(self) -> bool:
        query = self.query_var.get().strip()
        if not query:
            messagebox.showwarning("Missing Query", "Please enter a search query.")
            return False
        return True

    def _terms_validate(self) -> bool:
        terms = self.terms_var.get().strip()
        if not terms:
            messagebox.showwarning("Missing Terms", "Please enter comma-separated keywords.")
            return False
        return True

    def collect_params(self) -> dict:
        return {
            "samples_to_show": int(self.samples_to_show_var.get()), #new: adding sample comments to be modifiable
            "query": self.query_var.get().strip(),
            "pages": int(self.pages_var.get()),
            "per_page": int(self.per_page_var.get()),
            "top": int(self.top_var.get()),
            "sort": self.sort_var.get(),
            "min_views": max(0, int(self.min_views_var.get())),
            "min_comments": max(0, int(self.min_comments_var.get())),
            "since_days": self._parse_days(self.since_var.get()),
            "terms": self.terms_var.get().strip(),
            "match": self.match_var.get(),
            "top_videos": int(self.top_videos_var.get()),
            "comments_per_video": int(self.comments_per_video_var.get()),
            "show_term_totals": bool(self.show_term_totals_var.get()),
        }

    def get_samples_to_show(self) -> int:
        # Read the widget text directly (more reliable than IntVar for ttk.Spinbox)
        if self.samples_spinbox is None:
            return int(self.samples_to_show_var.get() or 0)

        raw = (self.samples_spinbox.get() or "").strip()
        try:
            return max(0, int(raw))
        except Exception:
            return max(0, int(self.samples_to_show_var.get() or 0))


    def _run_search(self) -> None:
        if not self._base_validate():
            return
        params = self.collect_params()
        self._on_run_search(params)

    def _run_combined(self) -> None:
        if not self._base_validate():
            return
        if not self._terms_validate():
            return
        params = self.collect_params()
        self._on_run_combined(params)
