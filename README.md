# sonkip. — Find it. Save it. Play it.

An open-source **local-only web app** for finding tracks or importing playlists, downloading permitted audio in the **best original format offered by the source**, and maintaining an offline music library. No account, remote application server, analytics, or JavaScript framework is required.

**Website:** https://gr33nops.github.io/sonkip/

The GitHub Pages site is a static project page. The downloader intentionally runs on your own computer so searches, audio files, and library data are never sent to a sonkip server.

![Stack](https://img.shields.io/badge/Stack-FastAPI%20%2B%20vanilla%20JS-8fddad)

## Features

- Search YouTube by title, artist, or album.
- Paste a playlist URL supported by yt-dlp to queue every valid song, with batch progress and no fixed playlist-size limit imposed by sonkip.
- Download the best **audio-only** source format with `yt-dlp` (`bestaudio`). No re-encoding to MP3/FLAC, so no avoidable quality loss.
- Download progress, speed and estimated time; up to two concurrent downloads.
- SQLite library persisted between restarts; offline playback, file export and deletion.
- Responsive animated UI with no frontend build tools, cookies, analytics, or CDN JavaScript.
- FastAPI binds to `127.0.0.1` **only**, not a public interface.

> Only download content you own or have permission to download and comply with the source's terms. sonkip. does not bypass DRM or paywalls. Some sources/videos are not downloadable. YouTube audio is generally lossy; this app **cannot create genuine lossless FLAC** from lossy source audio. Search and playlist imports need Internet; playing previously downloaded tracks works offline.

## Requirements

- Python **3.10+**
- [Deno](https://docs.deno.com/runtime/getting_started/installation/) **2.3+**, on PATH (recommended for yt-dlp's YouTube JavaScript challenges)
- Optional: [FFmpeg](https://ffmpeg.org/download.html) on PATH (helpful for certain audio containers; normal single-stream original-audio downloads do not need transcoding)

Latest yt-dlp YouTube support also needs the `yt-dlp-ejs` Python package, which is installed by the `yt-dlp[default]` dependency in this project. See the [yt-dlp EJS guide](https://github.com/yt-dlp/yt-dlp/wiki/EJS).

## Quick start

### One-command Windows install

Open PowerShell and run:

```powershell
irm https://raw.githubusercontent.com/Gr33nOps/sonkip/main/install.ps1 | iex
```

This downloads Sonkip without Git, installs it under `%LOCALAPPDATA%\Sonkip`, creates its private Python environment, installs the dependencies, and opens the app. Use `Start Sonkip.cmd` in that folder whenever you want to launch it again.

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

## Limitations / future work

- Browser playback depends on the format: modern browsers commonly handle WebM/Opus and MP4/AAC, but some formats require VLC or a local player.
- Searching YouTube is an external network request and can occasionally be blocked, rate-limited or changed upstream. Upgrade with `pip install -U 'yt-dlp[default]'`.
- Download jobs live in memory while the app runs. Finished library records persist. Stopping the app interrupts active downloads.
- Track art is loaded from `i.ytimg.com` while online; original media is local, but covers aren't cached offline.
- No automated YouTube integration test is included, as it would require real network access.
- Run this on your own trusted computer; **do not expose it to your LAN or the public internet**. The app has no user authentication and is not hardened for multi-user hosting.

## License

The app's own code is [MIT-licensed](LICENSE). Dependencies retain their respective licenses; yt-dlp is Unlicense, other packages have separate terms.
