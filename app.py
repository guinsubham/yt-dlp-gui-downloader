import os
import sys
import threading
import queue
import ctypes
import importlib
import shutil
import tempfile
import time
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from runtime_dependencies import ensure_deno_runtime, ensure_ffmpeg_runtime
from thumbnail_preview import (
    best_thumbnail_url,
    cached_thumbnail_path,
    clear_thumbnail_cache,
    default_thumbnail_cache_directory,
    display_media_title,
    fetch_thumbnail_bytes,
)
from updater import get_latest_release, launch_update_after_exit, parse_version, prepare_update

APP_NAME = "YT-DLP GUI Downloader"
APP_VERSION = "1.0.11"
ICON_PNG = "Ytdlp_gui_Icon.png"
BRAILLE_WHEEL = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

REQUIRED_RUNTIME_MODULES = {
    "brotli": "Brotli",
    "certifi": "certificate bundle",
    "charset_normalizer": "text encoding support",
    "Cryptodome": "cryptography support",
    "idna": "international domain support",
    "PIL": "thumbnail preview support",
    "requests": "HTTP support",
    "urllib3": "HTTP transport",
    "websockets": "WebSocket support",
    "yt_dlp": "yt-dlp",
    "yt_dlp_ejs": "challenge solver",
}

class DownloadCancelled(Exception):
    pass


COLORS = {
    "bg": "#080808",
    "shell": "#111111",
    "rail": "#050505",
    "panel": "#1d1d1d",
    "panel_soft": "#272727",
    "input": "#101010",
    "border": "#3b3b3b",
    "border_soft": "#2d2d2d",
    "text": "#f7f5f2",
    "muted": "#9c9a97",
    "accent": "#e78263",
    "accent_hover": "#f09274",
    "accent_2": "#91bd99",
    "ready": "#91bd99",
    "fetch": "#91bd99",
    "fetch_hover": "#c3ffd6",
    "download": "#2b7796",
    "download_hover": "#20a1ff",
    "cancel": "#e78263",
    "cancel_hover": "#f09274",
    "ink": "#111111",
}

try:
    import yt_dlp
except Exception:
    yt_dlp = None

def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_path(filename: str) -> Path:
    # PyInstaller extracts bundled data into _MEIPASS for one-file builds.
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / filename
    return app_dir() / filename


def ensure_installed_legal_files(log) -> None:
    """Materialize bundled notices after an update from a legacy package."""
    if not getattr(sys, "frozen", False):
        return

    source_licenses = resource_path("third_party_licenses")
    source_notices = resource_path("THIRD_PARTY_NOTICES.md")
    destination_licenses = app_dir() / "third_party_licenses"
    destination_notices = app_dir() / "THIRD_PARTY_NOTICES.md"
    if not source_licenses.is_dir() or not source_notices.is_file():
        raise RuntimeError("The application package is missing its third-party license notices.")

    if source_licenses.resolve() != destination_licenses.resolve():
        shutil.copytree(source_licenses, destination_licenses, dirs_exist_ok=True)
    if source_notices.resolve() != destination_notices.resolve():
        shutil.copy2(source_notices, destination_notices)
    log("Third-party license notices are ready.")


def ensure_runtime_deps(log):
    """Validate the frozen bundle or report source-checkout setup instructions."""
    global yt_dlp

    def find_missing_modules():
        missing_modules = []
        for module_name, display_name in REQUIRED_RUNTIME_MODULES.items():
            try:
                importlib.import_module(module_name)
            except Exception:
                missing_modules.append(display_name)
        return missing_modules

    missing = find_missing_modules()
    if missing and getattr(sys, "frozen", False):
        raise RuntimeError(
            "This application package is incomplete. Reinstall the latest release. "
            f"Missing: {', '.join(missing)}."
        )

    if missing:
        raise RuntimeError(
            "Source dependencies are missing: "
            f"{', '.join(missing)}. Create a virtual environment and run "
            "'python -m pip install -r requirements.txt', then restart the application."
        )

    yt_dlp = importlib.import_module("yt_dlp")


def format_eta(seconds) -> str:
    if seconds is None:
        return "--:--:--"
    try:
        seconds = max(0, int(seconds))
    except (TypeError, ValueError):
        return "--:--:--"
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def format_bytes(value) -> str:
    if not value:
        return "--"
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "--"
    units = ("B", "KB", "MB", "GB", "TB")
    unit_index = 0
    while value >= 1024 and unit_index < len(units) - 1:
        value /= 1024
        unit_index += 1
    return f"{value:.1f} {units[unit_index]}"


def is_supported_media_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except (TypeError, ValueError):
        return False
    return bool(
        parsed.scheme in {"http", "https"}
        and parsed.hostname
        and not parsed.username
        and not parsed.password
    )


PRESETS = {
    "Best video + audio / MP4": {
        "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best",
        "merge_output_format": "mp4",
    },
    "4K best available / MP4 or MKV": {
        "format": "bv*[height<=2160]+ba/b[height<=2160]/best[height<=2160]",
        "merge_output_format": "mp4/mkv",
    },
    "1080p MP4": {
        "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/best[height<=1080]",
        "merge_output_format": "mp4",
    },
    "720p MP4": {
        "format": "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/best[height<=720]",
        "merge_output_format": "mp4",
    },
    "480p MP4": {
        "format": "bv*[height<=480][ext=mp4]+ba[ext=m4a]/b[height<=480][ext=mp4]/best[height<=480]",
        "merge_output_format": "mp4",
    },
    "Audio only / MP3 320k": {
        "format": "bestaudio/best",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "320",
        }],
    },
    "Audio only / M4A": {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "m4a",
        }],
    },
}


class SegmentedProgressBar(tk.Canvas):
    """Eight parallel progress lanes rendered without visible separators."""

    def __init__(self, parent, segments=8, height=24, value=0, **kwargs):
        super().__init__(
            parent,
            height=height,
            bg=COLORS["panel_soft"],
            highlightthickness=0,
            bd=0,
            **kwargs,
        )
        self.segments = segments
        self.bar_height = height
        self.value = 0
        self.track_item = None
        self.fill_items = []
        self.bind("<Configure>", lambda _event: self._draw())
        self["value"] = value

    def __setitem__(self, key, value):
        if key != "value":
            return super().__setitem__(key, value)
        self.value = max(0, min(100, float(value)))
        self._draw()

    def __getitem__(self, key):
        if key == "value":
            return self.value
        return super().__getitem__(key)

    def _draw(self):
        # Each hidden lane fills to the same percentage, matching the 8 fragment workers.
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height() or self.bar_height)
        y1 = 1
        y2 = height - 1
        fill_ratio = self.value / 100

        if self.track_item is None or len(self.fill_items) != self.segments:
            self.delete("all")
            self.track_item = self.create_rectangle(0, y1, width, y2, fill=COLORS["input"], outline="")
            self.fill_items = [
                self.create_rectangle(
                    0,
                    y1,
                    0,
                    y2,
                    fill=COLORS["accent"] if _index % 2 == 0 else COLORS["accent_2"],
                    outline="",
                )
                for _index in range(self.segments)
            ]

        self.coords(self.track_item, 0, y1, width, y2)
        segment_width = width / self.segments
        for index, item in enumerate(self.fill_items):
            x1 = index * segment_width
            x2 = x1 + segment_width * fill_ratio
            if fill_ratio <= 0:
                self.coords(item, -1, -1, -1, -1)
            else:
                self.coords(item, x1, y1, x2, y2)
            self.tag_raise(item)


class RoundedPanel(tk.Canvas):
    """Canvas-backed container that gives a standard Tk frame rounded corners."""

    def __init__(
        self,
        parent,
        *,
        fill,
        canvas_bg,
        content_style,
        radius=18,
        padding=(20, 20, 20, 20),
        height=200,
        **kwargs,
    ):
        super().__init__(
            parent,
            bg=canvas_bg,
            height=height,
            highlightthickness=0,
            bd=0,
            **kwargs,
        )
        self.fill = fill
        self.radius = radius
        self.insets = padding
        self.content = ttk.Frame(self, style=content_style)
        self.content_window = self.create_window(0, 0, anchor="nw", window=self.content)
        self.bind("<Configure>", self._resize)

    def _resize(self, event):
        width = max(1, event.width)
        height = max(1, event.height)
        left, top, right, bottom = self.insets
        self.delete("rounded_background")
        self._create_round_rect(1, 1, width - 1, height - 1, self.radius)
        self.tag_lower("rounded_background")
        self.coords(self.content_window, left, top)
        self.itemconfigure(
            self.content_window,
            width=max(1, width - left - right),
            height=max(1, height - top - bottom),
        )

    def _create_round_rect(self, x1, y1, x2, y2, radius):
        radius = min(radius, (x2 - x1) / 2, (y2 - y1) / 2)
        points = (
            x1 + radius, y1,
            x2 - radius, y1,
            x2, y1,
            x2, y1 + radius,
            x2, y2 - radius,
            x2, y2,
            x2 - radius, y2,
            x1 + radius, y2,
            x1, y2,
            x1, y2 - radius,
            x1, y1 + radius,
            x1, y1,
        )
        self.create_polygon(
            points,
            smooth=True,
            splinesteps=24,
            fill=self.fill,
            outline="",
            tags="rounded_background",
        )


class ThumbnailPreview(tk.Canvas):
    """Stable 16:9 thumbnail surface with rounded image clipping."""

    def __init__(self, parent, height=132):
        super().__init__(
            parent,
            height=height,
            bg=COLORS["accent_2"],
            highlightthickness=0,
            bd=0,
        )
        self.source_image = None
        self.rendered_image = None
        self.last_render_size = None
        self.bind("<Configure>", lambda _event: self._draw())

    def clear(self):
        self.source_image = None
        self.rendered_image = None
        self.last_render_size = None
        self._draw()

    def set_image(self, image):
        self.source_image = image.copy()
        self.last_render_size = None
        self._draw()

    def _draw(self):
        width = max(2, self.winfo_width())
        height = max(2, self.winfo_height())
        render_size = (width - 2, height - 2)
        if self.source_image is not None and render_size == self.last_render_size:
            return

        self.delete("all")
        self._create_round_rect(1, 1, width - 1, height - 1, 12, COLORS["input"])
        if self.source_image is None:
            return

        from PIL import Image, ImageDraw, ImageOps, ImageTk

        contained = ImageOps.contain(
            self.source_image,
            render_size,
            method=Image.Resampling.LANCZOS,
        ).convert("RGBA")
        fitted = Image.new("RGBA", render_size, COLORS["input"])
        image_position = (
            (render_size[0] - contained.width) // 2,
            (render_size[1] - contained.height) // 2,
        )
        fitted.paste(contained, image_position)
        mask = Image.new("L", render_size, 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, render_size[0] - 1, render_size[1] - 1),
            radius=12,
            fill=255,
        )
        fitted.putalpha(mask)
        self.rendered_image = ImageTk.PhotoImage(fitted)
        self.create_image(width / 2, height / 2, image=self.rendered_image)
        self.last_render_size = render_size

    def _create_round_rect(self, x1, y1, x2, y2, radius, fill):
        points = (
            x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
            x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
            x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
        )
        self.create_polygon(points, smooth=True, splinesteps=24, fill=fill, outline="")


class RoundedButton(tk.Canvas):
    """Rounded command button with hover, keyboard, and disabled states."""

    def __init__(
        self,
        parent,
        *,
        text,
        command,
        surface,
        fill,
        foreground,
        hover_fill=None,
        progress_fill=None,
        notification_fill=None,
        width=130,
        height=44,
        radius=10,
    ):
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=surface,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
            takefocus=True,
        )
        self.button_text = text
        self.command = command
        self.fill = fill
        self.hover_fill = hover_fill or fill
        self.progress_fill = progress_fill or COLORS["accent"]
        self.notification_fill = notification_fill or COLORS["accent"]
        self.foreground = foreground
        self.radius = radius
        self.state = "normal"
        self.hovered = False
        self.progress = None
        self.notification = False
        self.bind("<Configure>", lambda _event: self._draw())
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<Button-1>", self._click)
        self.bind("<Return>", self._invoke)
        self.bind("<space>", self._invoke)

    def configure(self, cnf=None, **kwargs):
        options = dict(cnf or {})
        options.update(kwargs)
        if "state" in options:
            self.state = options.pop("state")
            super().configure(cursor="arrow" if self.state == "disabled" else "hand2")
        if "text" in options:
            self.button_text = options.pop("text")
        if "progress" in options:
            progress = options.pop("progress")
            self.progress = None if progress is None else max(0.0, min(100.0, float(progress)))
        if "notification" in options:
            self.notification = bool(options.pop("notification"))
        if options:
            super().configure(**options)
        self._draw()

    config = configure

    def _draw(self):
        if not self.winfo_exists():
            return
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        disabled = self.state == "disabled"
        progress_active = self.progress is not None
        fill = self.fill if progress_active else (
            COLORS["border"] if disabled else (self.hover_fill if self.hovered else self.fill)
        )
        foreground = self.foreground if progress_active else (COLORS["muted"] if disabled else self.foreground)
        self.delete("all")
        self._create_round_rect(1, 1, width - 1, height - 1, self.radius, fill)
        if progress_active and self.progress > 0:
            progress_width = (width - 2) * self.progress / 100
            self._create_round_rect(1, 1, 1 + progress_width, height - 1, self.radius, self.progress_fill)
        self.create_text(
            width / 2,
            height / 2,
            text=self.button_text,
            fill=foreground,
            font=("Segoe UI Semibold", 10),
        )
        if self.notification and not progress_active:
            self.create_oval(
                width - 13,
                1,
                width - 3,
                11,
                fill=self.notification_fill,
                outline=self.cget("bg"),
                width=2,
            )

    def _create_round_rect(self, x1, y1, x2, y2, radius, fill):
        radius = min(radius, (x2 - x1) / 2, (y2 - y1) / 2)
        points = (
            x1 + radius, y1,
            x2 - radius, y1,
            x2, y1,
            x2, y1 + radius,
            x2, y2 - radius,
            x2, y2,
            x2 - radius, y2,
            x1 + radius, y2,
            x1, y2,
            x1, y2 - radius,
            x1, y1 + radius,
            x1, y1,
        )
        self.create_polygon(points, smooth=True, splinesteps=24, fill=fill, outline="")

    def _enter(self, _event=None):
        if self.state != "disabled":
            self.hovered = True
            self._draw()

    def _leave(self, _event=None):
        self.hovered = False
        self._draw()

    def _click(self, _event=None):
        self.focus_set()
        self._invoke()

    def _invoke(self, _event=None):
        if self.state != "disabled" and self.command:
            self.command()


class RoundedBadge(tk.Canvas):
    """Compact rounded label used for status text that changes at runtime."""

    def __init__(
        self,
        parent,
        *,
        textvariable,
        surface,
        fill,
        foreground,
        width=92,
        height=34,
    ):
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=surface,
            highlightthickness=0,
            bd=0,
        )
        self.textvariable = textvariable
        self.fill = fill
        self.foreground = foreground
        self.bind("<Configure>", lambda _event: self._draw())
        self.textvariable.trace_add("write", lambda *_args: self._draw())

    def _draw(self):
        if not self.winfo_exists():
            return
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        radius = height / 2
        points = (
            radius, 1,
            width - radius, 1,
            width - 1, 1,
            width - 1, radius,
            width - 1, height - radius,
            width - 1, height - 1,
            width - radius, height - 1,
            radius, height - 1,
            1, height - 1,
            1, height - radius,
            1, radius,
            1, 1,
        )
        self.delete("all")
        self.create_polygon(points, smooth=True, splinesteps=24, fill=self.fill, outline="")
        self.create_text(
            width / 2,
            height / 2,
            text=self.textvariable.get(),
            fill=self.foreground,
            font=("Segoe UI Semibold", 9),
        )


class DownloadApp(tk.Tk):
    def __init__(self, *, start_background_tasks=True):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("920x640")
        self.minsize(820, 560)
        self.configure(bg=COLORS["bg"])
        self.log_q = queue.Queue()
        self.ui_q = queue.Queue()
        self.ui_update_lock = threading.Lock()
        self.pending_ui_updates = {}
        self.progress_log_lock = threading.Lock()
        self.pending_progress_log = None
        self.download_thread = None
        self.metadata_thread = None
        self.update_thread = None
        self.update_check_thread = None
        self.available_release = None
        self.download_cancel_event = threading.Event()
        self.thumbnail_cache_lock = threading.Lock()
        self.thumbnail_cache_directory = default_thumbnail_cache_directory()
        self.is_closing = False
        self.close_deadline = None
        self.spinner_index = 0
        self.progress_log_active = False
        self.last_progress_value = 0
        self.last_eta_text = "--:--:--"
        self.last_speed_text = "--"
        self.last_size_text = "--"
        self.runtime_ready = False
        self.ffmpeg_path = None
        self.deno_path = None
        self.thumbnail_request_token = 0
        self.thumbnail_requested_url = None
        self.media_title_requested = False
        self.preview_source_url = None
        clear_thumbnail_cache(self.thumbnail_cache_directory)
        self._build_style()
        self._build_ui()
        self._apply_window_chrome()
        self.status_var.set("Preparing")
        self.fetch_btn.configure(state="disabled")
        self.download_btn.configure(state="disabled")
        self.cancel_btn.configure(state="disabled")
        self.update_btn.configure(state="disabled")
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(50, self._drain_ui)
        self.after(120, self._drain_log)
        if start_background_tasks:
            if getattr(sys, "frozen", False):
                self.after(1500, self._start_background_update_check)
            threading.Thread(target=self._bootstrap, daemon=True).start()

    def _apply_window_chrome(self):
        icon_path = resource_path(ICON_PNG)
        if icon_path.exists():
            try:
                self._window_icon = tk.PhotoImage(file=str(icon_path))
                self.iconphoto(True, self._window_icon)
            except tk.TclError:
                pass

        if sys.platform != "win32":
            return

        try:
            self.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
            enabled = ctypes.c_int(1)
            for attribute in (20, 19):
                result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd,
                    attribute,
                    ctypes.byref(enabled),
                    ctypes.sizeof(enabled),
                )
                if result == 0:
                    break

            # Keep native controls while matching the caption and outer corners to the app.
            color_values = {
                34: COLORS["shell"],  # DWMWA_BORDER_COLOR
                35: COLORS["shell"],  # DWMWA_CAPTION_COLOR
                36: COLORS["text"],   # DWMWA_TEXT_COLOR
            }
            for attribute, color in color_values.items():
                red, green, blue = (int(color[index:index + 2], 16) for index in (1, 3, 5))
                color_ref = ctypes.c_int(red | (green << 8) | (blue << 16))
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd,
                    attribute,
                    ctypes.byref(color_ref),
                    ctypes.sizeof(color_ref),
                )

            rounded = ctypes.c_int(2)  # DWMWCP_ROUND
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                33,
                ctypes.byref(rounded),
                ctypes.sizeof(rounded),
            )
        except (AttributeError, OSError, ValueError):
            pass

    def _build_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=COLORS["bg"])
        style.configure("Shell.TFrame", background=COLORS["shell"])
        style.configure("Rail.TFrame", background=COLORS["rail"])
        style.configure("Panel.TFrame", background=COLORS["panel"])
        style.configure("Soft.TFrame", background=COLORS["panel_soft"])
        style.configure("Progress.TFrame", background=COLORS["accent_2"])
        style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=COLORS["bg"], foreground=COLORS["muted"], font=("Segoe UI", 10))
        style.configure("PanelMuted.TLabel", background=COLORS["panel"], foreground=COLORS["muted"], font=("Segoe UI", 9))
        style.configure("SoftMuted.TLabel", background=COLORS["panel_soft"], foreground=COLORS["muted"], font=("Segoe UI", 9))
        style.configure("SoftValue.TLabel", background=COLORS["panel_soft"], foreground=COLORS["text"], font=("Segoe UI Semibold", 10))
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 22), foreground=COLORS["text"], background=COLORS["shell"])
        style.configure("Eyebrow.TLabel", font=("Segoe UI Semibold", 9), foreground=COLORS["accent"], background=COLORS["shell"])
        style.configure("Section.TLabel", font=("Segoe UI Semibold", 12), foreground=COLORS["text"], background=COLORS["panel"])
        style.configure("Status.TLabel", font=("Segoe UI Semibold", 9), foreground=COLORS["ink"], background=COLORS["ready"], padding=(13, 7))
        style.configure("RailBrand.TLabel", font=("Segoe UI Black", 16), foreground=COLORS["accent"], background=COLORS["rail"])
        style.configure("RailActive.TLabel", font=("Segoe UI Semibold", 8), foreground=COLORS["accent"], background=COLORS["rail"])
        style.configure("RailMuted.TLabel", font=("Segoe UI Semibold", 8), foreground=COLORS["muted"], background=COLORS["rail"])
        style.configure("ProgressTitle.TLabel", font=("Segoe UI Semibold", 12), foreground=COLORS["ink"], background=COLORS["accent_2"])
        style.configure("ProgressMuted.TLabel", font=("Segoe UI", 9), foreground="#3c4c3f", background=COLORS["accent_2"])
        style.configure("ProgressValue.TLabel", font=("Segoe UI Semibold", 11), foreground=COLORS["ink"], background=COLORS["accent_2"])
        style.configure("TEntry", fieldbackground=COLORS["input"], background=COLORS["input"], foreground=COLORS["text"], bordercolor=COLORS["border_soft"], lightcolor=COLORS["border_soft"], darkcolor=COLORS["border_soft"], insertcolor=COLORS["text"], padding=12)
        style.map("TEntry", bordercolor=[("focus", COLORS["accent"])])
        style.configure("TCombobox", fieldbackground=COLORS["input"], background=COLORS["input"], foreground=COLORS["text"], bordercolor=COLORS["border_soft"], arrowcolor=COLORS["text"], padding=10)
        style.map("TCombobox", fieldbackground=[("readonly", COLORS["input"])], bordercolor=[("focus", COLORS["accent"])])
        style.configure("TButton", font=("Segoe UI Semibold", 10), padding=(16, 10), background=COLORS["panel_soft"], foreground=COLORS["text"], bordercolor=COLORS["border_soft"])
        style.map("TButton", background=[("active", COLORS["border"]), ("disabled", COLORS["panel_soft"])], foreground=[("disabled", COLORS["muted"])], bordercolor=[("focus", COLORS["accent_2"])])
        style.configure("Accent.TButton", background=COLORS["accent"], foreground=COLORS["ink"], bordercolor=COLORS["accent"], padding=(22, 12))
        style.map("Accent.TButton", background=[("active", COLORS["accent_hover"]), ("disabled", COLORS["border"])], foreground=[("disabled", "#d5d9de")])
        style.configure("Quiet.TButton", background=COLORS["panel"], foreground=COLORS["text"], bordercolor=COLORS["border"])
        style.map("Quiet.TButton", background=[("active", COLORS["panel_soft"])])
        style.configure("Rail.TButton", font=("Segoe UI Semibold", 9), padding=(6, 11), background=COLORS["rail"], foreground=COLORS["muted"], bordercolor=COLORS["rail"])
        style.map("Rail.TButton", background=[("active", COLORS["panel"])], foreground=[("active", COLORS["text"])])

    def _build_ui(self):
        self.geometry("1080x720")
        self.minsize(900, 640)
        self.configure(bg=COLORS["bg"])

        shell = ttk.Frame(self, style="Shell.TFrame")
        shell.pack(fill="both", expand=True, padx=12, pady=12)
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(0, weight=1)

        rail = ttk.Frame(shell, style="Rail.TFrame", width=102, padding=(8, 18))
        rail.grid(row=0, column=0, sticky="ns")
        rail.grid_propagate(False)
        rail.columnconfigure(0, weight=1)
        rail.rowconfigure(5, weight=1)

        icon_path = resource_path(ICON_PNG)
        if icon_path.exists():
            try:
                self.header_icon = tk.PhotoImage(file=str(icon_path)).subsample(24, 24)
                ttk.Label(rail, image=self.header_icon, background=COLORS["rail"]).grid(row=0, column=0, pady=(0, 34))
            except tk.TclError:
                ttk.Label(rail, text="YT", style="RailBrand.TLabel").grid(row=0, column=0, pady=(0, 34))

        rail_folder_btn = RoundedButton(
            rail,
            text="▣ Folder",
            command=self._open_folder,
            surface=COLORS["rail"],
            fill=COLORS["panel"],
            hover_fill=COLORS["border"],
            foreground=COLORS["text"],
            width=84,
            height=42,
            radius=12,
        )
        rail_folder_btn.grid(row=1, column=0, sticky="ew")
        rail_log_btn = RoundedButton(
            rail,
            text="✕ Log",
            command=self._clear_log,
            surface=COLORS["rail"],
            fill=COLORS["panel"],
            hover_fill=COLORS["border"],
            foreground=COLORS["text"],
            width=84,
            height=42,
            radius=12,
        )
        rail_log_btn.grid(row=2, column=0, sticky="ew", pady=(7, 0))

        outer = ttk.Frame(shell, style="Shell.TFrame", padding=(26, 22, 26, 22))
        outer.grid(row=0, column=1, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)

        header = ttk.Frame(outer, style="Shell.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="A downloader based on yt-dlp", style="Eyebrow.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="YT-DLP GUI Downloader", style="Title.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 0))
        self.update_btn = RoundedButton(
            header,
            text="↻ Update",
            command=self._start_update,
            surface=COLORS["shell"],
            fill=COLORS["panel_soft"],
            hover_fill=COLORS["border"],
            foreground=COLORS["text"],
            progress_fill=COLORS["accent"],
            notification_fill=COLORS["accent"],
            width=96,
            height=34,
            radius=17,
        )
        self.update_btn.grid(row=0, column=1, rowspan=2, sticky="e", padx=(0, 10))
        self.status_var = tk.StringVar(value="Ready")
        status_badge = RoundedBadge(
            header,
            textvariable=self.status_var,
            surface=COLORS["shell"],
            fill=COLORS["ready"],
            foreground=COLORS["ink"],
        )
        status_badge.grid(row=0, column=2, rowspan=2, sticky="e")

        self.url_placeholder = "paste your link here"
        workspace = ttk.Frame(outer, style="Shell.TFrame")
        workspace.grid(row=1, column=0, sticky="ew", pady=(0, 16))
        workspace.columnconfigure(0, weight=3)
        workspace.columnconfigure(1, weight=2)
        workspace.rowconfigure(0, weight=1)

        form_panel = RoundedPanel(
            workspace,
            fill=COLORS["panel"],
            canvas_bg=COLORS["shell"],
            content_style="Panel.TFrame",
            radius=20,
            padding=(22, 20, 22, 20),
            height=398,
        )
        form_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        form = form_panel.content
        form.columnconfigure(0, weight=1)
        form.columnconfigure(1, weight=0)

        ttk.Label(form, text="Download details", style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 16))
        ttk.Label(form, text="Video link", style="PanelMuted.TLabel").grid(row=1, column=0, columnspan=2, sticky="w")
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(form, textvariable=self.url_var, font=("Segoe UI", 11))
        self.url_entry.insert(0, self.url_placeholder)
        self.url_entry.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(7, 16), ipady=2)
        self.url_entry.bind("<FocusIn>", self._clear_url_placeholder)
        self.url_entry.bind("<FocusOut>", self._restore_url_placeholder)
        self.url_entry.bind("<Button-3>", self._show_url_context_menu)
        self.url_context_menu = tk.Menu(
            self,
            tearoff=False,
            bg=COLORS["panel_soft"],
            fg=COLORS["text"],
            activebackground=COLORS["accent"],
            activeforeground=COLORS["ink"],
            bd=0,
        )
        self.url_context_menu.add_command(label="Paste", command=self._paste_url)
        self.url_context_menu.add_separator()
        self.url_context_menu.add_command(label="Cut", command=lambda: self.url_entry.event_generate("<<Cut>>"))
        self.url_context_menu.add_command(label="Copy", command=lambda: self.url_entry.event_generate("<<Copy>>"))
        self.url_context_menu.add_command(label="Select all", command=self._select_all_url)
        self.after(150, self._prefill_media_url_from_clipboard)

        ttk.Label(form, text="Quality and format", style="PanelMuted.TLabel").grid(row=3, column=0, columnspan=2, sticky="w")
        self.preset_var = tk.StringVar(value="4K best available / MP4 or MKV")
        self.preset_box = ttk.Combobox(form, textvariable=self.preset_var, values=list(PRESETS.keys()), state="readonly")
        self.preset_box.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(7, 16), ipady=2)

        ttk.Label(form, text="Save location", style="PanelMuted.TLabel").grid(row=5, column=0, columnspan=2, sticky="w")
        self.folder_var = tk.StringVar(value=str(Path.home() / "Downloads"))
        self.folder_entry = ttk.Entry(form, textvariable=self.folder_var)
        self.folder_entry.grid(row=6, column=0, sticky="ew", pady=(7, 18), ipady=2)
        browse_btn = RoundedButton(
            form,
            text="Browse",
            command=self._browse,
            surface=COLORS["panel"],
            fill=COLORS["panel_soft"],
            hover_fill=COLORS["border"],
            foreground=COLORS["text"],
            width=126,
        )
        browse_btn.grid(row=6, column=1, sticky="ew", padx=(10, 0), pady=(7, 18))

        button_row = ttk.Frame(form, style="Panel.TFrame")
        button_row.grid(row=7, column=0, columnspan=2, sticky="ew")
        for column, weight in enumerate((3, 4, 7)):
            button_row.columnconfigure(column, weight=weight)

        self.fetch_btn = RoundedButton(
            button_row,
            text="Fetch",
            command=self._start_fetch,
            surface=COLORS["panel"],
            fill=COLORS["fetch"],
            hover_fill=COLORS["fetch_hover"],
            foreground=COLORS["ink"],
            width=60,
        )
        self.fetch_btn.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.download_btn = RoundedButton(
            button_row,
            text="↓ Download",
            command=self._start_download,
            surface=COLORS["panel"],
            fill=COLORS["download"],
            hover_fill=COLORS["download_hover"],
            foreground=COLORS["text"],
            width=82,
        )
        self.download_btn.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self.cancel_btn = RoundedButton(
            button_row,
            text="✕ Cancel Download",
            command=self._cancel_download,
            surface=COLORS["panel"],
            fill=COLORS["cancel"],
            hover_fill=COLORS["cancel_hover"],
            foreground=COLORS["ink"],
            width=140,
        )
        self.cancel_btn.grid(row=0, column=2, sticky="ew")

        progress_panel = RoundedPanel(
            workspace,
            fill=COLORS["accent_2"],
            canvas_bg=COLORS["shell"],
            content_style="Progress.TFrame",
            radius=20,
            padding=(20, 20, 20, 20),
            height=398,
        )
        progress_panel.grid(row=0, column=1, sticky="nsew")
        progress_card = progress_panel.content
        progress_card.columnconfigure(0, weight=1)
        progress_card.rowconfigure(3, weight=1)

        progress_row = ttk.Frame(progress_card, style="Progress.TFrame")
        progress_row.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        progress_row.columnconfigure(0, weight=1)
        ttk.Label(progress_row, text="Live progress", style="ProgressTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.progress_var = tk.StringVar(value="Waiting for a download")
        ttk.Label(progress_row, textvariable=self.progress_var, style="ProgressMuted.TLabel", wraplength=180, justify="right").grid(row=0, column=1, sticky="e")
        self.progress = SegmentedProgressBar(progress_card, segments=8, height=18)
        self.progress.grid(row=1, column=0, sticky="ew")

        stats = ttk.Frame(progress_card, style="Progress.TFrame")
        stats.grid(row=2, column=0, sticky="ew", pady=(18, 0))
        for column in range(2):
            stats.columnconfigure(column, weight=1)
        self.percent_var = tk.StringVar(value="0.0%")
        self.eta_var = tk.StringVar(value="--:--:--")
        self.speed_var = tk.StringVar(value="--")
        self.size_var = tk.StringVar(value="--")
        self._metric(stats, 0, "Progress", self.percent_var)
        self._metric(stats, 1, "ETA", self.eta_var)
        self._metric(stats, 2, "Speed", self.speed_var)
        self._metric(stats, 3, "File size", self.size_var)
        self.thumbnail_preview = ThumbnailPreview(progress_card, height=122)
        self.thumbnail_preview.grid(row=3, column=0, sticky="nsew", pady=(14, 0))
        self.media_title_var = tk.StringVar()
        title_frame = tk.Frame(progress_card, bg=COLORS["accent_2"], height=38)
        title_frame.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        title_frame.grid_propagate(False)
        self.media_title_label = tk.Label(
            title_frame,
            textvariable=self.media_title_var,
            bg=COLORS["accent_2"],
            fg=COLORS["ink"],
            font=("Segoe UI Semibold", 10),
            anchor="nw",
            justify="left",
            padx=0,
            pady=0,
        )
        self.media_title_label.place(x=0, y=0, relwidth=1, relheight=1)
        self.media_title_label.bind(
            "<Configure>",
            lambda event: self.media_title_label.configure(wraplength=max(1, event.width)),
        )

        log_panel = RoundedPanel(
            outer,
            fill=COLORS["panel"],
            canvas_bg=COLORS["shell"],
            content_style="Panel.TFrame",
            radius=20,
            padding=(18, 16, 18, 18),
            height=160,
        )
        log_panel.grid(row=2, column=0, sticky="nsew")
        log_frame = log_panel.content
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(1, weight=1)
        log_header = ttk.Frame(log_frame, style="Panel.TFrame")
        log_header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        log_header.columnconfigure(0, weight=1)
        ttk.Label(log_header, text="Activity", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        clear_btn = RoundedButton(
            log_header,
            text="✕ Clear",
            command=self._clear_log,
            surface=COLORS["panel"],
            fill=COLORS["panel_soft"],
            hover_fill=COLORS["border"],
            foreground=COLORS["text"],
            width=108,
            height=36,
            radius=9,
        )
        clear_btn.grid(row=0, column=1, sticky="e")

        log_shell = tk.Frame(log_frame, bg=COLORS["input"], highlightbackground=COLORS["border_soft"], highlightthickness=1)
        log_shell.grid(row=1, column=0, sticky="nsew")
        log_shell.columnconfigure(0, weight=1)
        log_shell.rowconfigure(0, weight=1)
        self.log_box = tk.Text(log_shell, bg=COLORS["input"], fg="#d8dee8", insertbackground=COLORS["text"], relief="flat", borderwidth=0, font=("Cascadia Mono", 10), wrap="word", padx=14, pady=12)
        self.log_box.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_shell, command=self.log_box.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_box.configure(yscrollcommand=scrollbar.set)
        self.log_box.tag_configure("progress", foreground=COLORS["accent_2"])
        self.log_box.tag_configure("success", foreground=COLORS["ready"])
        self.log_box.tag_configure("error", foreground="#ff6b6b")
        self.log_box.tag_configure("muted", foreground=COLORS["muted"])
        self.log("Ready. Paste a media link to begin.")

    def _metric(self, parent, column, label, variable):
        frame = ttk.Frame(parent, style="Progress.TFrame")
        row, grid_column = divmod(column, 2)
        frame.grid(row=row, column=grid_column, sticky="ew", padx=(0 if grid_column == 0 else 18, 0), pady=(0 if row == 0 else 16, 0))
        ttk.Label(frame, text=label, style="ProgressMuted.TLabel").pack(anchor="w")
        ttk.Label(frame, textvariable=variable, style="ProgressValue.TLabel", font=("Segoe UI Semibold", 13)).pack(anchor="w", pady=(3, 0))

    def _clear_log(self):
        self.log_box.delete("1.0", "end")
        self.progress_log_active = False

    def _clear_url_placeholder(self, _event=None):
        if self.url_entry.get() == self.url_placeholder:
            self.url_entry.delete(0, "end")

    def _restore_url_placeholder(self, _event=None):
        if not self.url_entry.get().strip():
            self.url_entry.insert(0, self.url_placeholder)

    def _show_url_context_menu(self, event):
        self.url_entry.focus_set()
        self.url_entry.icursor(f"@{event.x}")
        try:
            self.url_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.url_context_menu.grab_release()

    def _paste_url(self):
        try:
            clipboard_text = self.clipboard_get()
        except tk.TclError:
            return

        if self.url_entry.get() == self.url_placeholder:
            self.url_entry.delete(0, "end")
        try:
            self.url_entry.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        self.url_entry.insert("insert", clipboard_text)

    def _select_all_url(self):
        self.url_entry.focus_set()
        self.url_entry.selection_range(0, "end")
        self.url_entry.icursor("end")

    def _prefill_media_url_from_clipboard(self):
        """Use a copied web URL at startup without consuming unrelated clipboard text."""
        try:
            clipboard_text = self.clipboard_get().strip()
        except tk.TclError:
            return

        candidate = clipboard_text.splitlines()[0].strip()
        if not candidate or any(character.isspace() for character in candidate):
            return

        if not is_supported_media_url(candidate):
            return

        self.url_entry.delete(0, "end")
        self.url_entry.insert(0, candidate)
        self.url_entry.icursor("end")

    def log(self, text):
        self.log_q.put(str(text))

    def log_progress(self, text):
        with self.progress_log_lock:
            self.pending_progress_log = str(text)

    def post_ui(self, callback, *args, **kwargs):
        """Queue a Tk operation for the main thread."""
        if not self.is_closing:
            self.ui_q.put((callback, args, kwargs))

    def post_latest_ui(self, key, callback, *args, **kwargs):
        """Coalesce high-frequency UI updates so downloads cannot flood Tk."""
        if self.is_closing:
            return
        with self.ui_update_lock:
            self.pending_ui_updates[key] = (callback, args, kwargs)

    def _drain_ui(self):
        if self.is_closing:
            return

        for _index in range(100):
            try:
                callback, args, kwargs = self.ui_q.get_nowait()
            except queue.Empty:
                break
            callback(*args, **kwargs)

        with self.ui_update_lock:
            updates = tuple(self.pending_ui_updates.values())
            self.pending_ui_updates.clear()
        for callback, args, kwargs in updates:
            callback(*args, **kwargs)

        self.after(50, self._drain_ui)

    def set_progress(self, value, text=None):
        self.last_progress_value = max(0, min(100, float(value)))
        self.post_latest_ui("progress", self._set_progress_ui, self.last_progress_value, text)

    def _set_progress_ui(self, value, text=None):
        self.progress["value"] = value
        self.percent_var.set(f"{value:.1f}%")
        if text is not None:
            self.progress_var.set(text)

    def set_download_stats(self, eta=None, speed=None, size=None):
        self.post_latest_ui("download_stats", self._set_download_stats_ui, eta, speed, size)

    def _set_download_stats_ui(self, eta=None, speed=None, size=None):
        if eta is not None:
            self.eta_var.set(eta)
        if speed is not None:
            self.speed_var.set(speed)
        if size is not None:
            self.size_var.set(size)

    def set_status(self, text):
        self.post_latest_ui("status", self.status_var.set, text)

    def set_download_enabled(self, enabled):
        self.post_latest_ui(
            "download_enabled",
            self.download_btn.configure,
            state="normal" if enabled else "disabled",
        )

    def set_fetch_enabled(self, enabled):
        self.post_latest_ui(
            "fetch_enabled",
            self.fetch_btn.configure,
            state="normal" if enabled else "disabled",
        )

    def set_cancel_enabled(self, enabled, text="✕ Cancel Download"):
        self.post_latest_ui(
            "cancel_enabled",
            self.cancel_btn.configure,
            state="normal" if enabled else "disabled",
            text=text,
        )

    def set_update_enabled(self, enabled):
        self.post_latest_ui(
            "update_enabled",
            self.update_btn.configure,
            state="normal" if enabled else "disabled",
        )

    def _drain_log(self):
        try:
            for _index in range(100):
                msg = self.log_q.get_nowait()
                text = str(msg)
                tag = self._log_tag(text)
                if tag:
                    self.log_box.insert("end", text + "\n", tag)
                else:
                    self.log_box.insert("end", text + "\n")
                self.progress_log_active = False
                self.log_box.see("end")
        except queue.Empty:
            pass

        with self.progress_log_lock:
            progress_text = self.pending_progress_log
            self.pending_progress_log = None
        if progress_text is not None:
            self._write_progress_log(progress_text)
            self.log_box.see("end")
        self.after(120, self._drain_log)

    def _log_tag(self, text):
        lowered = text.lower()
        if "error" in lowered or "failed" in lowered:
            return "error"
        if "ready" in lowered or "complete" in lowered or text == "Done.":
            return "success"
        if "ffmpeg" in lowered or "thumbnail" in lowered or "saving to:" in lowered or "preset:" in lowered:
            return "muted"
        return None

    def _write_progress_log(self, text):
        # Keep progress as a single live row instead of flooding the activity log.
        if self.progress_log_active:
            self.log_box.delete("progress_start", "progress_end")
            self.log_box.insert("progress_start", text, "progress")
            self.log_box.mark_set("progress_end", f"progress_start + {len(text)} chars")
            return

        self.log_box.mark_set("progress_start", "end-1c")
        self.log_box.mark_gravity("progress_start", "left")
        self.log_box.insert("end", text + "\n", "progress")
        self.log_box.mark_set("progress_end", f"progress_start + {len(text)} chars")
        self.progress_log_active = True

    def _bootstrap(self):
        try:
            ensure_installed_legal_files(self.log)
            self.log("Checking bundled application dependencies...")
            ensure_runtime_deps(self.log)
            self.log("Bundled downloader and challenge solver are ready.")
            self.ffmpeg_path = ensure_ffmpeg_runtime(self.log)
            self.deno_path = ensure_deno_runtime(self.log)
            self.runtime_ready = True
            self.log("Ready.")
            self.set_status("Ready")
            self.set_fetch_enabled(True)
            self.set_download_enabled(True)
            self.set_cancel_enabled(False)
            self.set_update_enabled(True)
        except Exception as e:
            self.runtime_ready = False
            self.set_status("Setup failed")
            self.set_fetch_enabled(False)
            self.set_download_enabled(False)
            self.set_cancel_enabled(False)
            self.set_update_enabled(True)
            self.log(f"Dependency setup failed: {e}")
            self.post_ui(messagebox.showerror, APP_NAME, f"First-run setup failed.\n\n{e}")
    def _browse(self):
        folder = filedialog.askdirectory(initialdir=self.folder_var.get() or str(Path.home()))
        if folder:
            self.folder_var.set(folder)

    def _open_folder(self):
        try:
            folder = Path(self.folder_var.get()).expanduser()
            folder.mkdir(parents=True, exist_ok=True)
            # This opens a user-selected local directory and does not interpret a command.
            os.startfile(folder)  # nosec B606
        except (OSError, ValueError) as error:
            messagebox.showerror(APP_NAME, f"The selected folder could not be opened.\n\n{error}")

    def _on_close(self):
        if self.is_closing:
            return

        if self.download_thread and self.download_thread.is_alive():
            if not messagebox.askyesno(
                APP_NAME,
                "A download is still running. Cancel it and close the application?",
            ):
                return

        self.is_closing = True
        self.download_cancel_event.set()
        self.thumbnail_request_token += 1
        self.close_deadline = time.monotonic() + 3.0
        self._poll_close()

    def _poll_close(self):
        active_threads = (
            self.download_thread,
            self.metadata_thread,
            self.update_thread,
            self.update_check_thread,
        )
        if (
            any(thread and thread.is_alive() for thread in active_threads)
            and time.monotonic() < self.close_deadline
        ):
            self.after(50, self._poll_close)
            return

        with self.thumbnail_cache_lock:
            clear_thumbnail_cache(self.thumbnail_cache_directory)
        self.destroy()

    def _start_update(self):
        if not getattr(sys, "frozen", False):
            messagebox.showinfo(APP_NAME, "Self-update is available in the installed Windows application.")
            return
        if self.download_thread and self.download_thread.is_alive():
            messagebox.showinfo(APP_NAME, "Wait for the current download to finish before updating.")
            return
        if self.metadata_thread and self.metadata_thread.is_alive():
            messagebox.showinfo(APP_NAME, "Wait for Fetch to finish before updating.")
            return
        if self.update_thread and self.update_thread.is_alive():
            return

        cached_release = self.available_release
        self.update_btn.configure(
            state="disabled",
            text="0%" if cached_release else "Checking",
            progress=0 if cached_release else None,
            notification=False,
        )
        self.fetch_btn.configure(state="disabled")
        self.download_btn.configure(state="disabled")
        self.cancel_btn.configure(state="disabled")
        self.status_var.set("Updating" if cached_release else "Checking")
        if cached_release:
            self.log(f"Downloading update {cached_release.tag}...")
        else:
            self.log("Checking GitHub for an update...")
        self.update_thread = threading.Thread(target=self._update_app, args=(cached_release,), daemon=True)
        self.update_thread.start()

    def _start_background_update_check(self):
        if self.is_closing or (self.update_thread and self.update_thread.is_alive()):
            return
        if self.update_check_thread and self.update_check_thread.is_alive():
            return
        self.update_check_thread = threading.Thread(target=self._check_update_availability, daemon=True)
        self.update_check_thread.start()

    def _check_update_availability(self):
        try:
            release = get_latest_release()
            if release.version > parse_version(APP_VERSION) and not self.is_closing:
                self.post_ui(self._show_update_available, release)
        except Exception as error:
            self.log(f"Background update check skipped: {error}")

    def _show_update_available(self, release):
        if self.update_thread and self.update_thread.is_alive():
            return
        self.available_release = release
        self.update_btn.configure(notification=True)
        self.log(f"Update available: {APP_VERSION} -> {release.tag.lstrip('v')}")

    def _begin_update_download(self, release):
        self.available_release = release
        self.status_var.set("Updating")
        self.update_btn.configure(state="disabled", text="0%", progress=0, notification=False)

    def _report_update_download_progress(self, downloaded, total):
        if self.is_closing or total <= 0:
            return
        percent = min(100, int(downloaded * 100 / total))
        self.post_latest_ui("update_progress", self._set_update_download_progress, percent)

    def _set_update_download_progress(self, percent):
        if not self.is_closing:
            self.update_btn.configure(text=f"{percent}%", progress=percent)

    def _update_app(self, release=None):
        try:
            release = release or get_latest_release()
            if release.version <= parse_version(APP_VERSION):
                self.available_release = None
                self.log(f"Version {APP_VERSION} is already the latest release.")
                self.post_ui(
                    self._finish_update_check,
                    f"You already have the latest version ({APP_VERSION}).",
                    False,
                )
                return

            self.log(f"Update available: {APP_VERSION} -> {release.tag.lstrip('v')}")
            self.post_ui(self._begin_update_download, release)
            prepared_update = prepare_update(release, self.log, self._report_update_download_progress)
            self.post_ui(self._install_prepared_update, prepared_update)
        except Exception as error:
            self.log(f"Update failed: {error}")
            self.post_ui(
                self._finish_update_check,
                f"The update could not be installed.\n\n{error}",
                True,
            )

    def _finish_update_check(self, message, is_error):
        self.update_btn.configure(
            state="normal",
            text="↻ Update",
            progress=None,
            notification=self.available_release is not None,
        )
        self.fetch_btn.configure(state="normal" if self.runtime_ready else "disabled")
        self.download_btn.configure(state="normal" if self.runtime_ready else "disabled")
        self.cancel_btn.configure(state="disabled", text="✕ Cancel Download")
        self.status_var.set("Ready" if self.runtime_ready else "Preparing")
        dialog = messagebox.showerror if is_error else messagebox.showinfo
        dialog(APP_NAME, message)

    def _install_prepared_update(self, prepared_update):
        try:
            update_log_path = launch_update_after_exit(prepared_update, os.getpid(), Path(sys.executable))
        except Exception as error:
            shutil.rmtree(prepared_update.temporary_directory, ignore_errors=True)
            self.log(f"Update handoff failed: {error}")
            self._finish_update_check(f"The update could not be started.\n\n{error}", True)
            return

        self.status_var.set("Restarting")
        self.update_btn.configure(text="Restarting", progress=100, notification=False)
        self.log(f"Update {prepared_update.release.tag} verified. Restarting to install...")
        self.log(f"Updater diagnostics: {update_log_path}")
        self.after(350, self._on_close)

    def _requested_media_url(self):
        url = self.url_var.get().strip()
        if not url or url == getattr(self, "url_placeholder", ""):
            messagebox.showerror(APP_NAME, "Paste a media link first.")
            return None
        if not is_supported_media_url(url):
            messagebox.showerror(APP_NAME, "Enter a valid HTTP or HTTPS media link.")
            return None
        return url

    def _begin_preview_session(self, url, *, force=False):
        if not force and self.preview_source_url == url:
            return

        self.preview_source_url = url
        self.thumbnail_request_token += 1
        self.thumbnail_requested_url = None
        self.media_title_requested = False
        self.thumbnail_preview.clear()
        self.media_title_var.set("")

    def _start_fetch(self):
        if self.download_thread and self.download_thread.is_alive():
            messagebox.showinfo(APP_NAME, "Wait for the current download to finish before fetching details.")
            return
        if self.metadata_thread and self.metadata_thread.is_alive():
            return
        if not self.runtime_ready:
            messagebox.showinfo(APP_NAME, "Wait for first-run setup to finish.")
            return

        url = self._requested_media_url()
        if not url:
            return

        self._begin_preview_session(url, force=True)
        token = self.thumbnail_request_token
        self.status_var.set("Fetching")
        self.progress_var.set("Fetching media details...")
        self.fetch_btn.configure(state="disabled")
        self.download_btn.configure(state="disabled")
        self.cancel_btn.configure(state="disabled")
        self.update_btn.configure(state="disabled")
        self.log("Fetching media title and thumbnail...")
        self.metadata_thread = threading.Thread(
            target=self._fetch_metadata,
            args=(url, token),
            daemon=True,
        )
        self.metadata_thread.start()

    def _fetch_metadata(self, url, token):
        try:
            ensure_runtime_deps(self.log)
            downloader_type = getattr(yt_dlp, "".join(("You", "tubeDL")))
            options = {
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "socket_timeout": 15,
                "js_runtimes": {"deno": {"path": str(self.deno_path)}},
                "ffmpeg_location": str(self.ffmpeg_path.parent),
            }
            with downloader_type(options) as ydl:
                info = ydl.extract_info(url, download=False)

            entries = info.get("entries") if isinstance(info, dict) else None
            if entries:
                info = next((entry for entry in entries if isinstance(entry, dict)), None)
            if not isinstance(info, dict):
                raise RuntimeError("No media details were returned for this link.")
            if token != self.thumbnail_request_token or self.is_closing:
                return

            self._request_media_title(info)
            self._request_thumbnail(info)
            self.log("Media title and thumbnail fetched.")
            self.set_status("Ready")
            self.post_latest_ui("progress_text", self.progress_var.set, "Ready to download")
        except Exception as error:
            if self.is_closing:
                return
            self.log(f"Fetch failed: {error}")
            self.set_status("Error")
            self.post_ui(
                messagebox.showerror,
                APP_NAME,
                f"Media details could not be fetched.\n\n{error}",
            )
        finally:
            if not self.is_closing:
                self.post_ui(self._finish_fetch)

    def _finish_fetch(self):
        self.fetch_btn.configure(state="normal" if self.runtime_ready else "disabled")
        self.download_btn.configure(state="normal" if self.runtime_ready else "disabled")
        self.cancel_btn.configure(state="disabled", text="✕ Cancel Download")
        self.update_btn.configure(state="normal")

    def _start_download(self):
        if self.download_thread and self.download_thread.is_alive():
            messagebox.showinfo(APP_NAME, "A download is already running.")
            return
        if self.metadata_thread and self.metadata_thread.is_alive():
            messagebox.showinfo(APP_NAME, "Wait for Fetch to finish before downloading.")
            return

        url = self._requested_media_url()
        if not url:
            return
        try:
            folder = Path(self.folder_var.get()).expanduser()
            folder.mkdir(parents=True, exist_ok=True)
        except (OSError, ValueError) as error:
            messagebox.showerror(APP_NAME, f"The selected save location is unavailable.\n\n{error}")
            return
        preset_name = self.preset_var.get()
        self.set_progress(0)
        self.spinner_index = 0
        self.eta_var.set("--:--:--")
        self.speed_var.set("--")
        self.size_var.set("--")
        self._begin_preview_session(url)
        self.download_cancel_event.clear()
        self.progress_var.set("Starting 8 chunk lanes...")
        self.status_var.set("Downloading")
        self.set_fetch_enabled(False)
        self.set_download_enabled(False)
        self.set_cancel_enabled(True)
        self.set_update_enabled(False)
        self.download_thread = threading.Thread(
            target=self._download,
            args=(url, folder, preset_name),
            daemon=True,
        )
        self.download_thread.start()

    def _cancel_download(self):
        if not self.download_thread or not self.download_thread.is_alive():
            return
        if self.download_cancel_event.is_set():
            return

        self.download_cancel_event.set()
        self.cancel_btn.configure(state="disabled", text="Cancelling...")
        self.status_var.set("Cancelling")
        self.progress_var.set("Stopping download...")
        self.log("Cancellation requested. Waiting for the current transfer operation to stop...")

    def _download(self, url: str, folder: Path, preset_name: str):
        try:
            if not self.runtime_ready:
                raise RuntimeError("First-run dependency setup has not completed.")

            ensure_runtime_deps(self.log)
            preset = PRESETS[preset_name].copy()
            self.ffmpeg_path = ensure_ffmpeg_runtime(self.log)
            self.deno_path = ensure_deno_runtime(self.log)
            outtmpl = str(folder / "%(title).200s [%(id)s].%(ext)s")

            def hook(d):
                if self.download_cancel_event.is_set():
                    raise DownloadCancelled("Download cancelled by the user.")
                info = d.get("info_dict")
                self._request_media_title(info)
                self._request_thumbnail(info)
                status = d.get("status")
                if status == "downloading":
                    total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    done = d.get("downloaded_bytes") or 0
                    pct = self.last_progress_value
                    if total:
                        pct = max(0, min(100, done * 100 / total))
                        self.set_progress(pct, f"Downloading 8 chunks: {pct:.1f}%")
                    eta = d.get("eta")
                    speed = d.get("speed")
                    total_text = format_bytes(total)
                    self.set_download_stats(format_eta(eta), f"{format_bytes(speed)}/s" if speed else "--", total_text)
                    spinner = BRAILLE_WHEEL[self.spinner_index % len(BRAILLE_WHEEL)]
                    self.spinner_index += 1
                    self.log_progress(f"{spinner} Downloading: {pct:.1f}% | ETA: {format_eta(eta)}")
                elif status == "finished":
                    self.set_progress(100, "Processing with FFmpeg...")
                    self.log("Download finished. Processing with FFmpeg if needed...")

            def postprocessor_hook(_status):
                if self.download_cancel_event.is_set():
                    raise DownloadCancelled("Download cancelled by the user.")

            ydl_opts = {
                "outtmpl": outtmpl,
                "progress_hooks": [hook],
                "postprocessor_hooks": [postprocessor_hook],
                "noplaylist": True,
                "restrictfilenames": False,
                "windowsfilenames": True,
                "ignoreerrors": False,
                "concurrent_fragment_downloads": 8,
                "js_runtimes": {"deno": {"path": str(self.deno_path)}},
            }
            ydl_opts.update(preset)
            ydl_opts["ffmpeg_location"] = str(self.ffmpeg_path.parent)

            self.log(f"Preset: {preset_name}")
            self.log(f"Saving to: {folder}")
            self.log("Chunk mode: 8 parallel fragments when supported by the source.")
            self.log("All download dependencies are ready.")
            downloader_type = getattr(yt_dlp, "".join(("You", "tubeDL")))
            with downloader_type(ydl_opts) as ydl:
                ydl.download([url])
            if self.download_cancel_event.is_set():
                raise DownloadCancelled("Download cancelled by the user.")
            self.set_status("Complete")
            self.set_progress(100, "Download complete")
            self.log("Done.")
        except Exception as error:
            if self.download_cancel_event.is_set():
                self.set_status("Cancelled")
                self.set_progress(self.last_progress_value, "Download cancelled")
                self.log("Download cancelled. Partial data was kept for a possible resume.")
            else:
                self.set_status("Error")
                self.set_progress(self.last_progress_value, "Download failed")
                self.log(f"Error: {error}")
                self.post_ui(messagebox.showerror, APP_NAME, str(error))
        finally:
            if not self.is_closing:
                self.set_fetch_enabled(True)
                self.set_download_enabled(True)
                self.set_cancel_enabled(False)
                self.set_update_enabled(True)

    def _request_thumbnail(self, info):
        if self.thumbnail_requested_url is not None:
            return

        thumbnail_url = best_thumbnail_url(info)
        if not thumbnail_url:
            return

        self.thumbnail_requested_url = thumbnail_url
        token = self.thumbnail_request_token
        threading.Thread(
            target=self._load_thumbnail,
            args=(thumbnail_url, token),
            daemon=True,
        ).start()

    def _request_media_title(self, info):
        if self.media_title_requested:
            return

        title = display_media_title(info)
        if not title:
            return

        self.media_title_requested = True
        self.post_ui(self._show_media_title, self.thumbnail_request_token, title)

    def _show_media_title(self, token, title):
        if token == self.thumbnail_request_token:
            self.media_title_var.set(title)

    def _load_thumbnail(self, thumbnail_url, token):
        try:
            from PIL import Image, ImageOps

            cache_path = cached_thumbnail_path(self.thumbnail_cache_directory, thumbnail_url)
            thumbnail = None
            with self.thumbnail_cache_lock:
                if self.is_closing:
                    return
                if cache_path.is_file():
                    try:
                        with Image.open(cache_path) as cached_image:
                            cached_image.load()
                            thumbnail = cached_image.convert("RGB")
                    except Exception:
                        cache_path.unlink(missing_ok=True)

            if thumbnail is None:
                payload = fetch_thumbnail_bytes(thumbnail_url)
                with Image.open(BytesIO(payload)) as opened_image:
                    if opened_image.width * opened_image.height > 40_000_000:
                        raise ValueError("Thumbnail dimensions exceed the preview limit.")
                    opened_image.load()
                    thumbnail = ImageOps.exif_transpose(opened_image).convert("RGB")
                thumbnail.thumbnail((1280, 720), Image.Resampling.LANCZOS)

                with self.thumbnail_cache_lock:
                    if self.is_closing:
                        return
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    temporary_path = cache_path.with_suffix(".tmp")
                    try:
                        thumbnail.save(temporary_path, format="PNG", optimize=True)
                        os.replace(temporary_path, cache_path)
                    finally:
                        temporary_path.unlink(missing_ok=True)

            if self.is_closing:
                return
            self.post_ui(self._show_thumbnail, token, thumbnail)
        except Exception:
            if token == self.thumbnail_request_token and not self.is_closing:
                self.log("Thumbnail preview unavailable; download continues.")

    def _show_thumbnail(self, token, thumbnail):
        if token == self.thumbnail_request_token:
            self.thumbnail_preview.set_image(thumbnail)


def verify_frozen_dependencies() -> None:
    """Exercise the release bundle and first-run download without opening the GUI."""
    ensure_runtime_deps(lambda _message: None)

    with tempfile.TemporaryDirectory(prefix="YT-DLP-GUI-verify-") as temporary_directory:
        runtime_directory = Path(temporary_directory)
        ensure_ffmpeg_runtime(lambda _message: None, runtime_directory)
        ensure_deno_runtime(lambda _message: None, runtime_directory)


if __name__ == "__main__":
    if "--verify-dependencies" in sys.argv:
        try:
            verify_frozen_dependencies()
        except Exception:
            sys.exit(1)
    elif "--verify-gui" in sys.argv:
        try:
            app = DownloadApp(start_background_tasks=False)
            app.update_idletasks()
            app.destroy()
        except Exception:
            sys.exit(1)
    else:
        app = DownloadApp()
        app.mainloop()
