from __future__ import annotations

import json
import threading
import tkinter as tk
from queue import Queue, Empty
from tkinter import ttk, messagebox, filedialog

# gui api implementation 
from tkinter import simpledialog
from yt_radar.config import get_api_key, save_api_key


from yt_radar.config import get_api_key
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


def decode_unicode_escapes(s: str) -> str:
    """
    Decodes literal unicode escape sequences like '\\u2019' into real characters.
    Leaves normal Unicode strings unchanged.
    """
    if not s:
        return s

    # Only attempt decoding if it actually looks escaped
    if "\\u" not in s and "\\U" not in s:
        return s

    try:
        return s.encode("utf-8").decode("unicode_escape")
    except Exception:
        return s


class YTRadarApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("yt-radar")
        self.geometry("1280x720")

        # ---- API key (inside __init__) ----
        try:
            api_key = get_api_key()
        except Exception:
            api_key = simpledialog.askstring(
                "YouTube API Key Required",
                "Enter your YouTube Data API key.\n\n"
                "It will be saved on this computer for next time.",
                show="*",
            )
            if not api_key:
                messagebox.showerror("Missing API Key", "No API key provided. Exiting.")
                self.destroy()
                return

            save_api_key(api_key)

        # ---- always run initialization after we have api_key ----
        self._yt = YouTubeClient(api_key=api_key)
        self._ranker = Ranker()

        self._search_service = SearchService(yt=self._yt, ranker=self._ranker, vfilter=VideoFilter())
        self._comment_terms_service = CommentTermsService(yt=self._yt, ranker=self._ranker, matcher=TermMatcher())

        self._q: Queue = Queue()

        # current data
        self._videos: list[Video] = []
        self._comment_results: list[CommentTermsResult] = []
        self._combined_results: list[CommentTermsResult] = []

        self._build_ui()
        self.after(100, self._poll_queue)

        self.after(100, self._poll_queue)

    # -----------------------------
    # UI
    # -----------------------------
    def _build_ui(self) -> None:
        # Single unified params panel
        self.params = UnifiedParamsFrame(
            self,
            on_run_search=self._run_search_only,
            on_run_comment_terms=self._run_comment_terms_only,
            on_run_combined=self._run_combined,
            on_export=self._export_search_json,
        )
        self.params.pack(fill="x", padx=10, pady=(10, 6))

        # Results
        self._build_results_area()

        # Samples viewer (always visible)
        self.sample_box = tk.Text(self, height=9, wrap="word")
        self.sample_box.insert("1.0", "Select a row to view sample matching comments (when available).\n")
        self.sample_box.configure(state="disabled")
        self.sample_box.pack(fill="x", padx=10, pady=(0, 10))

        # Status bar
        self._status = tk.StringVar(value="Ready")
        status_bar = ttk.Label(self, textvariable=self._status, anchor="w")
        status_bar.pack(side="bottom", fill="x")

        # Stable columns (no UI jumping)
        self._configure_results_stable()

    def _build_results_area(self) -> None:
        self.results_frame = ttk.LabelFrame(self, text="Results (double-click row to copy URL)")
        self.results_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.tree = ttk.Treeview(self.results_frame, columns=(), show="headings")
        yscroll = ttk.Scrollbar(self.results_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)

        self.tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")

        self.tree.bind("<Double-1>", self._copy_selected_url)
        self.tree.bind("<<TreeviewSelect>>", self._on_select_row)

    def _set_status(self, msg: str) -> None:
        self._status.set(msg)

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
                if status == "ok":
                    if task_name == "search_only":
                        self._videos = data
                        self._render_search_as_stable(self._videos)
                        self._set_status("Search complete.")
                        self._set_samples("Select a row to view sample matching comments (when available).\n")

                    elif task_name == "comment_terms_only":
                        self._comment_results = data
                        self._render_comment_results_as_stable(self._comment_results)
                        self._set_status("Comment terms complete.")

                    elif task_name == "combined":
                        videos, results = data
                        self._videos = videos
                        self._combined_results = results
                        self._render_comment_results_as_stable(self._combined_results)
                        self._set_status("Combined complete.")

                else:
                    self._set_status("Error.")
                    messagebox.showerror(f"{task_name} failed", data)
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

    def _run_comment_terms_only(self, params: dict) -> None:
        payload = {
            "query": params["query"],
            "pages": params["pages"],
            "per_page": params["per_page"],
            "top_videos": params["top_videos"],
            "terms": self._make_term_query(params),
            "comments_per_video": params["comments_per_video"],
        }
        self._run_in_thread(self._comment_terms_service.run, payload, "comment_terms_only")

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

            results = self._comment_terms_service.run_on_videos(
                videos=picked,
                terms=tq,
                comments_per_video=params["comments_per_video"],
            )
            return videos, results

        def worker():
            try:
                out = combined_worker()
                self._q.put(("ok", "combined", out))
            except Exception as e:
                self._q.put(("err", "combined", str(e)))

        self._set_status("Running combined...")
        threading.Thread(target=worker, daemon=True).start()


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

        # Prefer combined results if present and last action was combined;
        # otherwise comment-only; otherwise none.
        backing: list[CommentTermsResult] | None = None
        # Heuristic: if combined_results currently rendered, it should match row count
        if self._combined_results and len(self._combined_results) == len(self.tree.get_children()):
            backing = self._combined_results
        elif self._comment_results and len(self._comment_results) == len(self.tree.get_children()):
            backing = self._comment_results

        if not backing or idx < 0 or idx >= len(backing):
            self._set_samples("No matching comment samples for this row.\n")
            return

        r = backing[idx]
        text = f"{r.video.title}\n{r.video.url}\n\n"
        if not r.samples:
            text += "(No samples captured.)\n"
        else:
            for s in r.samples:
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
            messagebox.showinfo("No Results", "Run a search first.")
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            title="Save results.json",
        )
        if not path:
            return

        payload = [
            {
                "video_id": v.video_id,
                "title": v.title,
                "channel_title": v.channel_title,
                "published_at": v.published_at,
                "view_count": v.view_count,
                "comment_count": v.comment_count,
                "url": v.url,
            }
            for v in self._videos
        ]

        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

        messagebox.showinfo("Saved", f"Saved {len(self._videos)} results to:\n{path}")


class UnifiedParamsFrame(ttk.LabelFrame):
    """
    One panel containing everything:
    - Search params (query/pages/per_page/sort/top + filters)
    - Comment terms params (terms/match/top_videos/comments_per_video)
    """

    def __init__(self, parent, on_run_search, on_run_comment_terms, on_run_combined, on_export) -> None:
        super().__init__(parent, text="Query Parameters")
        self._on_run_search = on_run_search
        self._on_run_comment_terms = on_run_comment_terms
        self._on_run_combined = on_run_combined
        self._on_export = on_export

        # shared
        self.query_var = tk.StringVar()
        self.pages_var = tk.IntVar(value=3)
        self.per_page_var = tk.IntVar(value=50)

        # search behavior
        self.top_var = tk.IntVar(value=5)
        self.sort_var = tk.StringVar(value="views")

        # filters
        self.min_views_var = tk.IntVar(value=0)
        self.min_comments_var = tk.IntVar(value=0)
        self.since_var = tk.StringVar(value="")  # "30d"

        # comment terms
        self.terms_var = tk.StringVar()
        self.match_var = tk.StringVar(value="any")
        self.top_videos_var = tk.IntVar(value=10)
        self.comments_per_video_var = tk.IntVar(value=200)

        self._build()

    def _build(self) -> None:
        # Row 0 - Query
        ttk.Label(self, text="Query").grid(row=0, column=0, sticky="w", padx=6, pady=6)
        ttk.Entry(self, textvariable=self.query_var, width=60).grid(
            row=0, column=1, columnspan=9, sticky="we", padx=6, pady=6
        )

        # Row 1 - Search pagination + ranking
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

        # Row 2 - Filters
        ttk.Label(self, text="Min Views").grid(row=2, column=0, sticky="w", padx=6, pady=6)
        ttk.Entry(self, textvariable=self.min_views_var, width=10).grid(row=2, column=1, sticky="w", padx=6, pady=6)

        ttk.Label(self, text="Min Comments").grid(row=2, column=2, sticky="w", padx=6, pady=6)
        ttk.Entry(self, textvariable=self.min_comments_var, width=10).grid(row=2, column=3, sticky="w", padx=6, pady=6)

        ttk.Label(self, text='Since (e.g. "30d")').grid(row=2, column=4, sticky="w", padx=6, pady=6)
        ttk.Entry(self, textvariable=self.since_var, width=12).grid(row=2, column=5, sticky="w", padx=6, pady=6)

        # Row 3 - Comment term controls
        ttk.Label(self, text="Terms (comma-separated)").grid(row=3, column=0, sticky="w", padx=6, pady=6)
        ttk.Entry(self, textvariable=self.terms_var, width=40).grid(
            row=3, column=1, columnspan=5, sticky="we", padx=6, pady=6
        )

        ttk.Label(self, text="Match").grid(row=3, column=6, sticky="w", padx=6, pady=6)
        ttk.Combobox(self, textvariable=self.match_var, values=["any", "all"], width=10, state="readonly").grid(
            row=3, column=7, sticky="w", padx=6, pady=6
        )

        # Row 4 - Comment term limits
        ttk.Label(self, text="Videos to Analyze (comments)").grid(row=4, column=0, sticky="w", padx=6, pady=6)
        ttk.Spinbox(self, from_=1, to=200, textvariable=self.top_videos_var, width=8).grid(
            row=4, column=1, sticky="w", padx=6, pady=6
        )

        ttk.Label(self, text="Comments/video").grid(row=4, column=2, sticky="w", padx=6, pady=6)
        ttk.Spinbox(self, from_=1, to=2000, textvariable=self.comments_per_video_var, width=8).grid(
            row=4, column=3, sticky="w", padx=6, pady=6
        )

        # Row 5 - Buttons
        ttk.Button(self, text="Run Search Only", command=self._run_search).grid(
            row=5, column=7, sticky="e", padx=6, pady=6
        )
        ttk.Button(self, text="Run Comment Terms Only", command=self._run_comment_terms).grid(
            row=5, column=8, sticky="e", padx=6, pady=6
        )
        ttk.Button(self, text="Run Combined", command=self._run_combined).grid(
            row=5, column=9, sticky="e", padx=6, pady=6
        )
        ttk.Button(self, text="Export JSON", command=self._on_export).grid(
            row=5, column=6, sticky="e", padx=6, pady=6
        )

        self.columnconfigure(1, weight=1)

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
        }

    def _run_search(self) -> None:
        if not self._base_validate():
            return
        params = self.collect_params()
        self._on_run_search(params)

    def _run_comment_terms(self) -> None:
        if not self._base_validate():
            return
        if not self._terms_validate():
            return
        params = self.collect_params()
        self._on_run_comment_terms(params)

    def _run_combined(self) -> None:
        if not self._base_validate():
            return
        if not self._terms_validate():
            return
        params = self.collect_params()
        self._on_run_combined(params)
