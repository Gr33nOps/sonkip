# sonkip. — Find it. Save it. Play it.

An open-source **local-only web app** for finding tracks or importing playlists, downloading permitted audio in the **best original format offered by the source**, and maintaining an offline music library. No account, remote application server, analytics, or JavaScript framework is required.

**Website:** https://gr33nops.github.io/sonkip/

**Android APK:** https://github.com/Gr33nOps/sonkip/releases/download/android-latest/sonkip-android.apk

The GitHub Pages site is a static project page. The downloader intentionally runs on your own computer so searches, audio files, and library data are never sent to a sonkip server.

![Stack](https://img.shields.io/badge/Stack-FastAPI%20%2B%20vanilla%20JS-8fddad)

## Features

- Search YouTube by title, artist, or album.
- Paste a public YouTube or YouTube Music playlist URL to queue its available tracks. Spotify and Apple Music playlist imports are not supported. Batch progress shows saved and failed tracks separately.
- Prefer the best **audio-only** source format, falling back to a combined audio/video file when necessary. No re-encoding to MP3/FLAC.
- Download progress, speed and estimated time; up to two concurrent downloads.
- SQLite library persisted between restarts; offline playback, file export and deletion.
- Responsive animated UI with no frontend build tools, tracking cookies, analytics, or CDN JavaScript.
- Optional local YouTube authentication for content the user is already allowed to access; the session file never leaves the device and can be deleted from the app.
- FastAPI binds to `127.0.0.1` **only**, not a public interface.

> Only download content you own or have permission to download and comply with the source's terms. sonkip. does not bypass DRM or paywalls. Some sources/videos are not downloadable. YouTube audio is generally lossy; this app **cannot create genuine lossless FLAC** from lossy source audio. Search and playlist imports need Internet; playing previously downloaded tracks works offline.

## Requirements

- Python **3.10+**
- Deno is installed into the private Python environment by the desktop installer for YouTube JavaScript challenges.
- Optional: [FFmpeg](https://ffmpeg.org/download.html) on PATH (helpful for certain audio containers; normal single-stream original-audio downloads do not need transcoding)

Latest yt-dlp YouTube support also needs the `yt-dlp-ejs` Python package, which is installed by the `yt-dlp[default]` dependency in this project. See the [yt-dlp EJS guide](https://github.com/yt-dlp/yt-dlp/wiki/EJS).

## Quick start

### Android

Download the current APK from the website or the link above, allow installation from your browser when Android asks, and open Sonkip. The APK bundles Python, QuickJS-NG, and yt-dlp's EJS scripts, and runs its interface and download engine on `127.0.0.1`. Its music library is stored in Android app-private storage and is removed if the app is uninstalled. Playlist downloads stay in **Saved**; export individual files from there instead of triggering a browser download for every track.

Android 7.0 (API 24) or newer is required. The current APK supports 32-bit and 64-bit ARM devices. Public YouTube tracks use cookie-free playback clients, and completed songs can be exported to the phone's Music folder. For content that legitimately requires the user's account, open **Access** and choose a Netscape-format YouTube `cookies.txt` export; Sonkip stores it in app-private storage and deletes it when **Disconnect** is pressed. Sonkip cannot bypass DRM, private-media permissions, regional blocks, or paywalls.

Desktop installs also include the experimental WebPoClient provider, which can automatically mint current YouTube proof-of-origin tokens using locally installed Chrome or Chromium when yt-dlp requests one. This feature still follows the source's permissions and does not defeat DRM.

### One-command Windows install

Open PowerShell and run:

```powershell
irm https://raw.githubusercontent.com/Gr33nOps/sonkip/main/install.ps1 | iex
```

This downloads Sonkip without Git, installs it under `%LOCALAPPDATA%\Sonkip`, creates its private Python environment, installs the dependencies, and opens the app. Use `Start Sonkip.cmd` in that folder whenever you want to launch it again.

### One-command macOS / Linux install

Open Terminal and run:

```bash
curl -fsSL https://raw.githubusercontent.com/Gr33nOps/sonkip/main/install.sh | bash
```

This installs Sonkip under `~/.local/share/sonkip`, creates its private Python environment, installs the dependencies, and opens the app. Run it again later with `~/.local/bin/sonkip`.

### Manual setup

Download the repository ZIP, extract it, and open a terminal in that folder:

#### Windows PowerShell

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python run.py
```

#### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python run.py
```

Visit **http://127.0.0.1:8000**.

If your environment blocks PowerShell activation, run `.venv\Scripts\python.exe -m pip install -r requirements.txt` then `.venv\Scripts\python.exe run.py` instead.

## Files

```text
sonkip-local/
├── app/
│   ├── __init__.py
│   ├── main.py          # HTTP API and secure local file serving
│   ├── engine.py        # Search, audio downloader, jobs and progress
│   └── storage.py       # Persistent SQLite library
├── android/              # Native WebView + embedded Python APK project
├── static/
│   ├── index.html       # UI
│   ├── style.css        # Responsive styling
│   ├── app.js           # Search, progress, player and library logic
│   └── favicon.svg
├── tests/
│   └── test_app.py
├── run.py                # Localhost server launcher
├── requirements.txt
├── LICENSE               # MIT (this app's code only)
└── README.md
```

## Local files & API

Default local storage: `~/Music/Sonkip/tracks/` with SQLite at `~/Music/Sonkip/library.sqlite3`. Existing `~/Music/Sonora` libraries are detected automatically. Override with environment variable `LOCALMUSIC_HOME` (an absolute directory is recommended).

All saved state is local to that folder. sonkip has no user accounts, telemetry, hosted database, or cloud library.

Routes:

| Method | Endpoint                 | Purpose                                                          |
| ------ | ------------------------ | ---------------------------------------------------------------- |
| GET    | `/api/search?q=...`      | Song search                                                      |
| POST   | `/api/downloads`         | Start job with JSON `{ "video_id": "11-character-ID" }`          |
| POST   | `/api/playlists`         | Import and queue a playlist with JSON `{ "url": "https://..." }` |
| GET    | `/api/jobs`              | Poll progress                                                    |
| GET    | `/api/tracks`            | List downloaded songs                                            |
| GET    | `/api/tracks/{id}/audio` | Stream local audio                                               |
| GET    | `/api/tracks/{id}/file`  | Download/copy audio                                              |
| DELETE | `/api/tracks/{id}`       | Permanently remove a local track                                 |
| GET    | `/api/health`            | Status and local storage path                                    |

Interactive backend documentation: `http://127.0.0.1:8000/docs`.

## Development tests

```bash
pip install pytest httpx
pytest -q
```

Tests use a temporary library and do not call YouTube.

### Building Android

Install Java 17, Gradle 8.13, Android SDK 35, NDK `28.2.13676358`, CMake and Ninja. Set `ANDROID_HOME` to the SDK folder. Run `python android/build_runtime.py` from the repository root, then `gradle -p android :app:assembleDebug`. The runtime build downloads checksum-pinned QuickJS-NG source and builds both ARM ABIs; its license is included in the APK. GitHub Actions performs these steps automatically.

## Limitations / future work

- Browser playback depends on the format: modern browsers commonly handle WebM/Opus and MP4/AAC, but some formats require VLC or a local player.
- Searching YouTube is an external network request and can occasionally be blocked, rate-limited or changed upstream. Upgrade with `pip install -U 'yt-dlp[default]'`.
- Download jobs live in memory while the app runs. Finished library records persist. Stopping the app interrupts active downloads.
- Track art is loaded from `i.ytimg.com` while online; original media is local, but covers aren't cached offline.
- No automated YouTube integration test is included, as it would require real network access.
- Run this on your own trusted computer; **do not expose it to your LAN or the public internet**. The app has no user authentication and is not hardened for multi-user hosting.

## License

The app's own code is [MIT-licensed](LICENSE). Dependencies retain their respective licenses; yt-dlp is Unlicense, other packages have separate terms.
