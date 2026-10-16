# sonkip.

### Find it. Save it. Play it.

Save public YouTube songs and playlists on your own device. Sonkip runs as a native Android app or a local website on Windows, macOS, and Linux. Your library stays on your device; Sonkip has no accounts or analytics.

[Website](https://gr33nops.github.io/sonkip/) · [Android releases](https://github.com/Gr33nOps/sonkip/releases) · [Report a bug](https://github.com/Gr33nOps/sonkip/issues)

The GitHub Pages site is a static project page. The downloader intentionally runs on your own computer so searches, audio files, and library data are never sent to a sonkip server.

## Features

- Search YouTube by title, artist, or album.
- Paste a public YouTube playlist, Spotify playlist/album, or SoundCloud set. Spotify and SoundCloud provide track names; Sonkip matches those tracks on YouTube and downloads from there. Unmatched tracks are counted separately. Apple Music and other services are not supported yet.
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

Download an APK from Releases, install it, and open Sonkip. Use Find to search or paste a playlist, Downloads to check progress, and Library to play or export songs. Version 2.1 adds background playback and downloads using Android foreground services. Allow notifications to see download progress; playback controls are available in the notification and on the lock screen. Switching apps does not pause music.

Force-stopping Sonkip or restarting the phone stops active work; unfinished jobs do not resume automatically. Android 15 limits background data-sync time to six hours per day. Some manufacturers apply additional battery restrictions; if downloads stop while the screen is off, check Sonkip's battery settings. Sonkip does not change those settings automatically.

Android 7.0 or newer on a 32-bit or 64-bit ARM device is required. Songs are stored in app-private storage. Export files you want to keep elsewhere before uninstalling. Install updates over the existing app to preserve your library. The native app does not currently offer account authentication.

In Library, **Play all** plays songs in download order (oldest first); **Shuffle** plays each song once in a random order. The player and notification have Previous and Next controls, and playback advances automatically when a song ends. Previous restarts the current song after three seconds, otherwise it goes to the preceding song.

Use **My playlists → Create playlist** to choose saved songs. You can also use a song's **More → Add to playlist** menu. Each playlist supports Play, Shuffle, song selection, rename, and delete. Deleting a playlist leaves its audio files in Library. Playlists are saved locally and survive updates; the active playback queue is temporary.

Public downloads use locally generated proof-of-origin tokens. Desktop uses Chrome or Chromium; Android uses an internal WebView behind its native interface. No cookie import is needed for public tracks. Private, restricted, unavailable, or DRM-protected media may still fail.

Matching a playlist can take a minute or more before downloads begin. Spotify's public embed can expose only part of a large playlist; Sonkip reports the number of tracks it could read, not a guaranteed full playlist count. Matches may be different uploads or editions. Sonkip skips candidates with clearly different titles, artists, or versions instead of downloading the first search result.

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
├── android/              # Native Android UI and embedded Python engine
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

Audio files use `Artist - Song title.ext` names. Duplicate names get a number, and older ID-named library files are renamed from their saved metadata when the app starts. The source format is preserved: `.webm` can contain audio only, even if Windows labels it a video file.

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
