from pathlib import Path

import yt_dlp


BRAILLE_WHEEL = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

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
    "Audio only / M4A": {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
    },
}


def format_eta(seconds):
    if seconds is None:
        return "--:--:--"
    try:
        seconds = max(0, int(seconds))
    except (TypeError, ValueError):
        return "--:--:--"
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def download(url, folder, preset_name, callback):
    spinner = {"index": 0, "last_pct": 0.0}
    folder_path = Path(folder)
    folder_path.mkdir(parents=True, exist_ok=True)
    outtmpl = str(folder_path / "%(title).200s [%(id)s].%(ext)s")

    def hook(data):
        status = data.get("status")
        if status == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            done = data.get("downloaded_bytes") or 0
            pct = spinner["last_pct"]
            if total:
                pct = max(0, min(100, done * 100 / total))
                spinner["last_pct"] = pct

            wheel = BRAILLE_WHEEL[spinner["index"] % len(BRAILLE_WHEEL)]
            spinner["index"] += 1
            callback.setProgress(pct, f"Downloading 8 chunks: {pct:.1f}%")
            callback.replaceProgressLog(f"{wheel} Downloading: {pct:.1f}% | ETA: {format_eta(data.get('eta'))}")
        elif status == "finished":
            callback.setProgress(100, "Processing...")
            callback.appendLog("Download finished. Processing if needed...")

    options = {
        "outtmpl": outtmpl,
        "progress_hooks": [hook],
        "noplaylist": True,
        "ignoreerrors": False,
        "restrictfilenames": False,
        "concurrent_fragment_downloads": 8,
    }
    options.update(PRESETS[preset_name])

    callback.appendLog(f"Preset: {preset_name}")
    callback.appendLog("Chunk mode: 8 parallel fragments when supported by the source.")
    callback.appendLog("Android note: FFmpeg-dependent merging may need extra runtime support.")
    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])
