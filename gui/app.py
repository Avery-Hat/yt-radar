from __future__ import annotations

import io
import json
import re
import threading
import sys
import tkinter as tk
import urllib.request
from queue import Queue, Empty
from tkinter import ttk, messagebox, filedialog, simpledialog

import customtkinter as ctk
from PIL import Image, ImageTk

from yt_radar.config import get_api_key, save_api_key, load_setting, save_setting
from yt_radar.models import Video
from yt_radar.services.filtering import Filters, VideoFilter
from yt_radar.services.search_service import SearchService
from yt_radar.services.comment_terms_service import CommentTermsService, CommentTermsResult
from yt_radar.services.term_matcher import TermMatcher, TermQuery
from yt_radar.youtube_client import YouTubeClient

ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")


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

    return _UNI_ESC_RE.sub(repl, s)


# ---------------------------------------------------------------------------
# Custom spinbox built from CTk widgets (CTk has no native Spinbox)
# ---------------------------------------------------------------------------

class CTkSpinbox(ctk.CTkFrame):
    def __init__(self, parent, from_: int = 0, to: int = 100,
                 textvariable: tk.Variable | None = None, width: int = 110, **kwargs) -> None:
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._from = from_
        self._to = to
        self._var = textvariable if textvariable is not None else tk.StringVar(value=str(from_))

        btn_w = 28
        entry_w = max(40, width - btn_w * 2 - 6)

        self._minus = ctk.CTkButton(self, text="−", width=btn_w, height=28, command=self._decrement)
        self._minus.pack(side="left")
        self._entry = ctk.CTkEntry(self, textvariable=self._var, width=entry_w, height=28, justify="center")
        self._entry.pack(side="left", padx=2)
        self._plus = ctk.CTkButton(self, text="+", width=btn_w, height=28, command=self._increment)
        self._plus.pack(side="left")

    def _decrement(self) -> None:
        try:
            self._var.set(str(max(self._from, int(str(self._var.get())) - 1)))
        except (ValueError, tk.TclError):
            self._var.set(str(self._from))

    def _increment(self) -> None:
        try:
            self._var.set(str(min(self._to, int(str(self._var.get())) + 1)))
        except (ValueError, tk.TclError):
            self._var.set(str(self._from))

    def get(self) -> str:
        return self._entry.get()


# ---------------------------------------------------------------------------
# Help dialog
# ---------------------------------------------------------------------------

class HelpDialog(ctk.CTkToplevel):
    def __init__(self, parent: ctk.CTk, on_close) -> None:
        super().__init__(parent)
        self.title("yt-radar help")
        self.resizable(False, False)
        self.transient(parent)
        self.after(100, self.grab_set)

        self._dont_show = tk.BooleanVar(value=False)
        self._on_close = on_close

        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        help_text = (
            "What the controls mean:\n\n"
            "Search:\n"
            "  Query: What you want to search on YouTube.\n"
            "  Pages / Per page: How many candidates to pull from YouTube.\n"
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

        text = ctk.CTkTextbox(frame, width=540, height=340, wrap="word")
        text.insert("1.0", help_text)
        text.configure(state="disabled")
        text.grid(row=0, column=0, columnspan=3, sticky="nsew", pady=(0, 10))

        ctk.CTkCheckBox(frame, text="Do not show this again", variable=self._dont_show).grid(
            row=1, column=0, sticky="w")
        ctk.CTkButton(frame, text="Reset help tips", width=120,
                      command=self._reset_help_tips).grid(row=1, column=1, padx=8)
        ctk.CTkButton(frame, text="Close", width=80, command=self._close).grid(
            row=1, column=2, sticky="e")

        frame.columnconfigure(0, weight=1)

        self.update_idletasks()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _reset_help_tips(self) -> None:
        save_setting("hide_help_on_start", False)
        self._dont_show.set(False)
        messagebox.showinfo("Help tips reset", "Help will show again next time you start the app.")

    def _close(self) -> None:
        self.grab_release()
        self.destroy()
        self._on_close(bool(self._dont_show.get()))


# ---------------------------------------------------------------------------
# Thumbnail hover tooltip
# ---------------------------------------------------------------------------

class ThumbnailHover:
    _YOUTUBE_ID_RE = re.compile(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})")

    def __init__(self, root: ctk.CTk, tree: ttk.Treeview, get_video_id_from_row) -> None:
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
        self.tree.bind("<ButtonPress>", self._on_leave, add=True)

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
        self._tip.geometry(f"+{self.root.winfo_pointerx() + 15}+{self.root.winfo_pointery() + 15}")
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


# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------

class YTRadarApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("yt-radar")
        self.geometry("1300x900")
        self.minsize(900, 650)

        if sys.platform == "win32":
            try:
                from ctypes import windll
                windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass

        self._setup_treeview_style()

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
        self._search_service = SearchService(yt=self._yt, vfilter=VideoFilter())
        self._comment_terms_service = CommentTermsService(yt=self._yt, matcher=TermMatcher())
        self._last_term_totals: dict[str, int] = {}

        self._q: Queue = Queue()
        self._videos: list[Video] = []
        self._comment_results: list[CommentTermsResult] = []
        self._combined_results: list[CommentTermsResult] = []
        self._analysis_by_video_id: dict[str, CommentTermsResult] = {}

        # Header bar
        header = ctk.CTkFrame(self, height=44, corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(header, text="yt-radar",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(side="left", padx=14, pady=7)
        ctk.CTkButton(header, text="?", width=36, height=30,
                      command=self._open_help).pack(side="right", padx=12, pady=7)

        self._build_ui()
        self.after(0, self._maybe_show_help_on_start)
        self.after(100, self._poll_queue)

    def _setup_treeview_style(self) -> None:
        is_dark = ctk.get_appearance_mode() == "Dark"
        bg      = "#2b2b2b" if is_dark else "#f2f2f2"
        fg      = "#dce4ee" if is_dark else "#1a1a1a"
        sel_bg  = "#1f538d" if is_dark else "#3b8ed0"
        head_bg = "#1c1c1c" if is_dark else "#d0d0d0"
        head_fg = "#dce4ee" if is_dark else "#1a1a1a"

        style = ttk.Style()
        style.configure("YTRadar.Treeview",
                        background=bg, foreground=fg, fieldbackground=bg,
                        rowheight=24, borderwidth=0)
        style.configure("YTRadar.Treeview.Heading",
                        background=head_bg, foreground=head_fg, relief="flat", padding=(4, 4))
        style.map("YTRadar.Treeview",
                  background=[("selected", sel_bg)],
                  foreground=[("selected", "white")])

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=10, pady=6)

        self.params = UnifiedParamsFrame(
            content,
            on_run_search=self._run_search_only,
            on_run_combined=self._run_combined,
            on_export=self._export_search_json,
        )
        self.params.pack(fill="x", pady=(0, 6))

        self._build_results_area(content)

        # Term totals panel (toggled via show_term_totals_var)
        self.term_totals_frame = ctk.CTkFrame(content, corner_radius=8)
        ctk.CTkLabel(self.term_totals_frame, text="Term totals (unique comments)",
                     font=ctk.CTkFont(weight="bold"), anchor="w").pack(
            fill="x", padx=8, pady=(6, 2))

        tv_wrap = ctk.CTkFrame(self.term_totals_frame, fg_color="transparent")
        tv_wrap.pack(fill="x", padx=6, pady=(0, 6))

        self.term_totals_tree = ttk.Treeview(
            tv_wrap, columns=("term", "count"), show="headings",
            height=4, style="YTRadar.Treeview",
        )
        self.term_totals_tree.heading("term", text="term")
        self.term_totals_tree.heading("count", text="unique comments")
        self.term_totals_tree.column("term", width=200)
        self.term_totals_tree.column("count", width=140, anchor="e")
        totals_yscroll = ttk.Scrollbar(tv_wrap, orient="vertical",
                                       command=self.term_totals_tree.yview)
        self.term_totals_tree.configure(yscrollcommand=totals_yscroll.set)
        self.term_totals_tree.pack(side="left", fill="x", expand=True)
        totals_yscroll.pack(side="right", fill="y")

        self.term_totals_frame.pack(fill="x", pady=(0, 6))

        # Sample comments
        ctk.CTkLabel(content, text="Sample matching comments",
                     font=ctk.CTkFont(weight="bold"), anchor="w").pack(
            fill="x", padx=4, pady=(0, 2))

        self.sample_box = ctk.CTkTextbox(content, height=160, wrap="word")
        self.sample_box.insert("1.0", "Select a row to view sample matching comments (when available).\n")
        self.sample_box.configure(state="disabled")
        self.sample_box.pack(fill="x", pady=(0, 6))

        # Status bar
        self._status_label = ctk.CTkLabel(self, text="Ready", anchor="w",
                                           font=ctk.CTkFont(size=12))
        self._status_label.pack(side="bottom", fill="x", padx=12, pady=(2, 6))

        self._configure_results_stable()

    def _build_results_area(self, parent) -> None:
        results_outer = ctk.CTkFrame(parent, corner_radius=8)
        results_outer.pack(fill="both", expand=True, pady=(0, 6))

        ctk.CTkLabel(results_outer, text="Results  (double-click row to copy URL)",
                     font=ctk.CTkFont(weight="bold"), anchor="w").pack(
            fill="x", padx=8, pady=(6, 2))

        tv_frame = ctk.CTkFrame(results_outer, fg_color="transparent")
        tv_frame.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        self.tree = ttk.Treeview(tv_frame, columns=(), show="headings",
                                  style="YTRadar.Treeview")
        yscroll = ttk.Scrollbar(tv_frame, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(tv_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

        yscroll.pack(side="right", fill="y")
        xscroll.pack(side="bottom", fill="x")
        self.tree.pack(side="left", fill="both", expand=True)

        self.tree.bind("<Double-1>", self._copy_selected_url)
        self.tree.bind("<<TreeviewSelect>>", self._on_select_row)
        self.tree.bind("<Button-1>", self._on_tree_click, add=True)

        def get_video_id_for_row(row_id: str) -> str | None:
            values = self.tree.item(row_id, "values")
            if not values:
                return None
            return ThumbnailHover._extract_video_id_from_url(values[-1])

        self._thumb_hover = ThumbnailHover(self, self.tree, get_video_id_for_row)

    # ------------------------------------------------------------------
    # Help
    # ------------------------------------------------------------------

    def _open_help(self) -> None:
        def on_close(dont_show_again: bool) -> None:
            if dont_show_again:
                save_setting("hide_help_on_start", True)
        HelpDialog(self, on_close=on_close)

    def _maybe_show_help_on_start(self) -> None:
        if not bool(load_setting("hide_help_on_start", False)):
            self._open_help()

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def _set_status(self, msg: str) -> None:
        if hasattr(self, "_status_label"):
            self._status_label.configure(text=msg)

    # ------------------------------------------------------------------
    # Tree click (reset to global totals when clicking empty space)
    # ------------------------------------------------------------------

    def _on_tree_click(self, event) -> None:
        if self.tree.identify_row(event.y):
            return
        self.tree.selection_remove(self.tree.selection())
        self._set_samples("Select a row to view sample matching comments (when available).\n")
        show = bool(self.params.show_term_totals_var.get())
        self._set_term_totals_visible(show)
        if show and self._last_term_totals:
            self._render_term_totals(self._last_term_totals)
        else:
            self._clear_term_totals()

    # ------------------------------------------------------------------
    # Background runner + queue
    # ------------------------------------------------------------------

    def _run_in_thread(self, fn, payload: dict, task_name: str) -> None:
        def worker():
            try:
                self._q.put(("ok", task_name, fn(**payload)))
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

    # ------------------------------------------------------------------
    # Service call helpers
    # ------------------------------------------------------------------

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
        self._run_in_thread(
            self._search_service.search,
            {"query": params["query"], "pages": params["pages"],
             "per_page": params["per_page"], "top": params["top"],
             "filters": self._get_filters(params)},
            "search_only",
        )

    def _run_combined(self, params: dict) -> None:
        def combined_worker():
            videos = self._search_service.search(
                query=params["query"], pages=params["pages"],
                per_page=params["per_page"], top=params["top"],
                filters=self._get_filters(params),
            )
            picked = videos[: max(1, min(params["top_videos"], len(videos)))]
            results, term_totals = self._comment_terms_service.run_on_videos(
                videos=picked, terms=self._make_term_query(params),
                comments_per_video=params["comments_per_video"],
                max_samples=params["samples_to_show"],
            )
            return videos, results, term_totals

        def worker():
            try:
                self._q.put(("ok", "combined", combined_worker()))
            except Exception as e:
                self._q.put(("err", "combined", str(e)))

        self._set_status("Running analysis...")
        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Term totals panel
    # ------------------------------------------------------------------

    def _clear_term_totals(self) -> None:
        if hasattr(self, "term_totals_tree"):
            for row in self.term_totals_tree.get_children():
                self.term_totals_tree.delete(row)

    def _render_term_totals(self, totals: dict[str, int]) -> None:
        self._clear_term_totals()
        for term, n in sorted(totals.items(), key=lambda kv: (-kv[1], kv[0].lower())):
            self.term_totals_tree.insert("", "end", values=(term, f"{n:,}"))

    def _set_term_totals_visible(self, visible: bool) -> None:
        if not hasattr(self, "term_totals_frame"):
            return
        if visible:
            self.term_totals_frame.pack(fill="x", pady=(0, 6))
        else:
            self.term_totals_frame.pack_forget()

    # ------------------------------------------------------------------
    # Results table
    # ------------------------------------------------------------------

    def _clear_tree(self) -> None:
        for row in self.tree.get_children():
            self.tree.delete(row)

    def _configure_results_stable(self) -> None:
        cols = ("hits", "matched_comments", "views", "comments", "title", "url")
        self.tree["columns"] = cols
        for c in cols:
            self.tree.heading(c, text=c)
        self.tree.column("hits",             width=80,  anchor="e", minwidth=60)
        self.tree.column("matched_comments", width=130, anchor="e", minwidth=100)
        self.tree.column("views",            width=90,  anchor="e", minwidth=70)
        self.tree.column("comments",         width=90,  anchor="e", minwidth=70)
        self.tree.column("title",            width=420,             minwidth=200)
        self.tree.column("url",              width=420,             minwidth=200)

    def _render_search_as_stable(self, videos: list[Video]) -> None:
        self._clear_tree()
        for v in videos:
            self.tree.insert("", "end", values=(
                "", "", f"{v.view_count:,}", f"{v.comment_count:,}", v.title, v.url,
            ))

    def _render_comment_results_as_stable(self, results: list[CommentTermsResult]) -> None:
        self._clear_tree()
        for r in results:
            v = r.video
            self.tree.insert("", "end", values=(
                r.total_term_hits, r.matched_comments,
                f"{v.view_count:,}", f"{v.comment_count:,}", v.title, v.url,
            ))

    # ------------------------------------------------------------------
    # Interactions
    # ------------------------------------------------------------------

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
                text += f"- {decode_unicode_escapes(s).strip()}\n\n"

        self._set_samples(text)

    def _set_samples(self, text: str) -> None:
        self.sample_box.configure(state="normal")
        self.sample_box.delete("1.0", "end")
        self.sample_box.insert("1.0", text or "")
        self.sample_box.configure(state="disabled")

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _export_search_json(self) -> None:
        if not self._videos:
            messagebox.showinfo("No Results", "Run a search or analysis first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON", "*.json")], title="Save results.json",
        )
        if not path:
            return
        payload = []
        for v in self._videos:
            item = {
                "video_id": v.video_id, "title": v.title,
                "channel_title": v.channel_title, "published_at": v.published_at,
                "view_count": v.view_count, "comment_count": v.comment_count, "url": v.url,
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


# ---------------------------------------------------------------------------
# Parameters panel
# ---------------------------------------------------------------------------

class UnifiedParamsFrame(ctk.CTkFrame):
    def __init__(self, parent, on_run_search, on_run_combined, on_export) -> None:
        super().__init__(parent, corner_radius=8)
        self._on_run_search = on_run_search
        self._on_run_combined = on_run_combined
        self._on_export = on_export

        self.query_var               = tk.StringVar()
        self.pages_var               = tk.StringVar(value="3")
        self.per_page_var            = tk.StringVar(value="50")
        self.top_var                 = tk.StringVar(value="5")
        self.min_views_var           = tk.StringVar(value="0")
        self.min_comments_var        = tk.StringVar(value="0")
        self.since_var               = tk.StringVar(value="")
        self.terms_var               = tk.StringVar()
        self.match_var               = tk.StringVar(value="any")
        self.top_videos_var          = tk.StringVar(value="10")
        self.comments_per_video_var  = tk.StringVar(value="200")
        self.show_term_totals_var    = tk.BooleanVar(value=True)
        self.samples_to_show_var     = tk.StringVar(value="10")

        self.samples_spinbox: CTkSpinbox | None = None
        self._build()

    # -- layout helpers --

    def _section(self, text: str) -> None:
        ctk.CTkLabel(self, text=text, font=ctk.CTkFont(size=12, weight="bold"),
                     anchor="w").pack(fill="x", padx=8, pady=(8, 2))

    def _row(self) -> ctk.CTkFrame:
        f = ctk.CTkFrame(self, fg_color="transparent")
        f.pack(fill="x", padx=8, pady=2)
        return f

    def _lbl(self, parent, text: str) -> ctk.CTkLabel:
        lbl = ctk.CTkLabel(parent, text=text, anchor="w")
        lbl.pack(side="left", padx=(0, 4))
        return lbl

    # -- build --

    def _build(self) -> None:
        ctk.CTkLabel(self, text="Query Parameters",
                     font=ctk.CTkFont(size=13, weight="bold"), anchor="w").pack(
            fill="x", padx=8, pady=(8, 4))

        # Search
        self._section("Search")

        r = self._row()
        self._lbl(r, "Query")
        ctk.CTkEntry(r, textvariable=self.query_var,
                     placeholder_text="e.g. best budget laptops 2024").pack(
            side="left", fill="x", expand=True)

        r = self._row()
        self._lbl(r, "Pages")
        CTkSpinbox(r, from_=1, to=50,   textvariable=self.pages_var,    width=110).pack(side="left", padx=(0, 16))
        self._lbl(r, "Per Page")
        CTkSpinbox(r, from_=1, to=50,   textvariable=self.per_page_var, width=110).pack(side="left", padx=(0, 16))
        self._lbl(r, "Top Results")
        CTkSpinbox(r, from_=1, to=200,  textvariable=self.top_var,      width=110).pack(side="left")

        # Filters
        self._section("Filters")

        r = self._row()
        self._lbl(r, "Min Views")
        ctk.CTkEntry(r, textvariable=self.min_views_var, width=100).pack(side="left", padx=(0, 16))
        self._lbl(r, "Min Comments")
        ctk.CTkEntry(r, textvariable=self.min_comments_var, width=100).pack(side="left", padx=(0, 16))
        self._lbl(r, 'Since (e.g. "30d")')
        ctk.CTkEntry(r, textvariable=self.since_var, width=100, placeholder_text="30d").pack(side="left")

        # Comment analysis
        self._section("Comment Analysis")

        r = self._row()
        self._lbl(r, "Terms")
        ctk.CTkEntry(r, textvariable=self.terms_var,
                     placeholder_text="comma-separated, e.g.  good,value,recommended").pack(
            side="left", fill="x", expand=True)

        r = self._row()
        self._lbl(r, "Match")
        ctk.CTkComboBox(r, variable=self.match_var, values=["any", "all"],
                        width=90, state="readonly").pack(side="left", padx=(0, 16))
        self._lbl(r, "Videos to Analyze")
        CTkSpinbox(r, from_=1, to=200,  textvariable=self.top_videos_var,         width=110).pack(side="left", padx=(0, 16))
        self._lbl(r, "Comments/video")
        CTkSpinbox(r, from_=1, to=2000, textvariable=self.comments_per_video_var, width=110).pack(side="left", padx=(0, 16))
        self._lbl(r, "Samples to show")
        self.samples_spinbox = CTkSpinbox(r, from_=0, to=200,
                                           textvariable=self.samples_to_show_var, width=110)
        self.samples_spinbox.pack(side="left")

        # Actions row
        r = self._row()
        r.pack(pady=(8, 10))
        ctk.CTkCheckBox(r, text="Show term totals",
                        variable=self.show_term_totals_var).pack(side="left", padx=(0, 16))
        ctk.CTkButton(r, text="Export JSON",      width=110, command=self._on_export).pack(side="left", padx=(0, 8))
        ctk.CTkButton(r, text="Run Query Only",   width=130, command=self._run_search).pack(side="left", padx=(0, 8))
        ctk.CTkButton(r, text="Run Full Analysis", width=140,
                      fg_color="#1f538d", hover_color="#173f6b",
                      command=self._run_combined).pack(side="left")

    # -- param helpers --

    def _safe_int(self, var: tk.Variable, default: int = 0) -> int:
        try:
            return int(str(var.get()))
        except (ValueError, tk.TclError):
            return default

    def _parse_days(self, s: str):
        s = (s or "").strip().lower().rstrip("d")
        try:
            return int(s) if s else None
        except ValueError:
            return None

    def collect_params(self) -> dict:
        return {
            "samples_to_show":      self.get_samples_to_show(),
            "query":                self.query_var.get().strip(),
            "pages":                self._safe_int(self.pages_var, 3),
            "per_page":             self._safe_int(self.per_page_var, 50),
            "top":                  self._safe_int(self.top_var, 5),
            "min_views":            max(0, self._safe_int(self.min_views_var, 0)),
            "min_comments":         max(0, self._safe_int(self.min_comments_var, 0)),
            "since_days":           self._parse_days(self.since_var.get()),
            "terms":                self.terms_var.get().strip(),
            "match":                self.match_var.get(),
            "top_videos":           self._safe_int(self.top_videos_var, 10),
            "comments_per_video":   self._safe_int(self.comments_per_video_var, 200),
            "show_term_totals":     bool(self.show_term_totals_var.get()),
        }

    def get_samples_to_show(self) -> int:
        if self.samples_spinbox is not None:
            try:
                return max(0, int(self.samples_spinbox.get().strip()))
            except (ValueError, TypeError):
                pass
        try:
            return max(0, int(str(self.samples_to_show_var.get())))
        except (ValueError, tk.TclError):
            return 10

    def _base_validate(self) -> bool:
        if not self.query_var.get().strip():
            messagebox.showwarning("Missing Query", "Please enter a search query.")
            return False
        return True

    def _terms_validate(self) -> bool:
        if not self.terms_var.get().strip():
            messagebox.showwarning("Missing Terms", "Please enter comma-separated keywords.")
            return False
        return True

    def _run_search(self) -> None:
        if self._base_validate():
            self._on_run_search(self.collect_params())

    def _run_combined(self) -> None:
        if self._base_validate() and self._terms_validate():
            self._on_run_combined(self.collect_params())
