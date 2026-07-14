# YT-DLP GUI Android

This is the Android build of the downloader. It uses a native Android interface and embeds Python with Chaquopy so the app can call `yt-dlp` from inside the APK.

## Build

From the project root, run:

```bat
build_android.bat
```

The APK is copied to:

```txt
dist\YT-DLP-GUI-Android-debug.apk
```

## Notes

- The debug APK is installable for testing.
- Downloads are saved to the app's Android downloads folder.
- FFmpeg-dependent video/audio merging may need extra Android FFmpeg support later.
