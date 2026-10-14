(() => {
  "use strict";

  const state = {
    currentTab: "search", // 'search' | 'library'
    inputMode: "song", // 'song' | 'playlist'
    query: "",
    results: [],
    library: [],
    activeJobs: new Map(), // video_id -> job
    currentlyPlaying: null, // { id, video_id, title, artist, url }
    isPlaying: false,
    searchTimeout: null,
    toastTimeout: null,
    pollInterval: null,
    playlist: null,
    authConnected: false,
  };

  const $ = (id) => document.getElementById(id);
  const audio = $("audio-el");
  const isStaticPages = window.location.hostname.endsWith(".github.io");

  function safe(str) {
    return String(str ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  }

  function formatTime(seconds) {
    if (seconds == null || !Number.isFinite(Number(seconds))) return "—";
    seconds = Math.max(0, Math.floor(Number(seconds)));
    const mins = Math.floor(seconds / 60);
    const secs = String(seconds % 60).padStart(2, "0");
    return `${mins}:${secs}`;
  }

  function showToast(text, isError = false) {
    const toast = $("toast");
    toast.textContent = text;
    toast.classList.toggle("toast-error", isError);
    toast.hidden = false;
    clearTimeout(state.toastTimeout);
    state.toastTimeout = setTimeout(() => {
      toast.hidden = true;
    }, 3200);
  }

  async function api(path, options = {}) {
    const res = await fetch(path, {
      ...options,
      headers: {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...options.headers,
      },
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || `Request failed (${res.status})`);
    }
    return data;
  }

  function renderAuthStatus() {
    const connected = state.authConnected;
    $("auth-disconnected").hidden = connected;
    $("auth-connected").hidden = !connected;
    $("auth-open-btn").classList.toggle("connected", connected);
    $("auth-open-btn").textContent = connected ? "ACCESS ✓" : "ACCESS";
  }

  async function loadAuthStatus() {
    try {
      const status = await api("/api/auth/youtube");
      state.authConnected = Boolean(status.connected);
      renderAuthStatus();
    } catch {
      state.authConnected = false;
      renderAuthStatus();
    }
  }

  // --- Rendering ---

  function render() {
    const list = $("track-list");
    const statusMsg = $("status-message");
    const searchClear = $("search-clear");
    const mainContent = document.querySelector(".main-content");

    searchClear.hidden = !$("search-input").value;

    const isInitial = state.currentTab === "search" && !state.query;
    if (mainContent) {
      mainContent.classList.toggle("is-initial", isInitial);
    }

    if (state.currentTab === "library") {
      if (state.library.length === 0) {
        list.innerHTML = "";
        list.hidden = true;
        statusMsg.hidden = false;
        statusMsg.textContent =
          "Your library is empty. Search for songs and click Download to save them!";
        return;
      }
      statusMsg.hidden = true;
      list.hidden = false;
      list.innerHTML = state.library
        .map((track) => renderTrackRow(track, true))
        .join("");
      return;
    }

    // Search Tab
    if (state.query) {
      if (state.results.length === 0) {
        list.innerHTML = "";
        list.hidden = true;
        statusMsg.hidden = false;
        statusMsg.textContent = "Nothing found. Try a different title.";
        return;
      }
      statusMsg.hidden = true;
      list.hidden = false;
      list.innerHTML = state.results
        .map((track) => renderTrackRow(track, false))
        .join("");
    } else {
      // Empty / Start state: No list at start
      list.innerHTML = "";
      list.hidden = true;
      statusMsg.hidden = true;
    }
  }

  function renderTrackRow(track, isLocal = false) {
    const isPlayingThis =
      state.currentlyPlaying &&
      (state.currentlyPlaying.video_id === track.video_id ||
        (isLocal && state.currentlyPlaying.id === track.id)) &&
      state.isPlaying;

    const playSymbol = isPlayingThis ? "Ⅱ" : "▶";
    const playClass = isPlayingThis
      ? "track-play-btn playing"
      : "track-play-btn";

    let dlHtml = "";
    const job = track.video_id ? state.activeJobs.get(track.video_id) : null;
    const isLocalSaved =
      isLocal ||
      state.library.some((t) => t.video_id && t.video_id === track.video_id);

    if (isLocal) {
      dlHtml = `
        <button class="track-download-btn downloaded" data-save-local="${safe(track.id)}" title="Download file to device">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3v12m0 0 5-5m-5 5-5-5M4 21h16"/></svg>
          <span class="hidden sm:inline">DOWNLOAD</span>
        </button>
        <button class="track-delete-btn" data-delete-track="${safe(track.id)}" title="Delete from library">×</button>
      `;
    } else if (job && job.status !== "complete" && job.status !== "error") {
      const pct = job.percent ? `${Math.round(job.percent)}%` : "...";
      dlHtml = `
        <button class="track-download-btn" disabled>
          <span class="spinner"></span>
          <span class="hidden sm:inline">DOWNLOADING ${pct}</span>
        </button>
      `;
    } else if (isLocalSaved) {
      const localItem = state.library.find(
        (t) => t.video_id === track.video_id,
      );
      dlHtml = `
        <button class="track-download-btn downloaded" data-save-local="${safe(localItem ? localItem.id : "")}" title="Saved in library. Click to save file again">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3v12m0 0 5-5m-5 5-5-5M4 21h16"/></svg>
          <span class="hidden sm:inline">DOWNLOADED ✓</span>
        </button>
      `;
    } else {
      dlHtml = `
        <button class="track-download-btn" data-download-track="${safe(track.video_id || "")}" data-track-title="${safe(track.title)}" data-track-artist="${safe(track.artist)}">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3v12m0 0 5-5m-5 5-5-5M4 21h16"/></svg>
          <span class="hidden sm:inline">DOWNLOAD</span>
        </button>
      `;
    }

    const tagHtml =
      isLocal && track.extension
        ? `<span class="track-tag">${safe(track.extension.toUpperCase())}</span>`
        : "";

    return `
      <article class="track-item" data-vid="${safe(track.video_id || "")}" data-tid="${safe(track.id || "")}">
        <button
          class="${playClass}"
          data-play-track="${safe(track.video_id || track.id || "")}"
          data-is-local="${isLocal ? "1" : "0"}"
          data-title="${safe(track.title)}"
          data-artist="${safe(track.artist)}"
          aria-label="${isPlayingThis ? "Pause" : "Play"} ${safe(track.title)}"
        >
          ${playSymbol}
        </button>
        <div class="track-info">
          <h2 class="track-title">${safe(track.title)}</h2>
          <p class="track-artist">${safe(track.artist)}${tagHtml}</p>
          ${job?.status === "error" ? `<p class="track-error">${safe(job.error || "Download failed")}. Use the download button to retry.</p>` : ""}
        </div>
        <div class="track-actions">
          ${dlHtml}
        </div>
      </article>
    `;
  }

  // --- Search ---

  async function performSearch(query) {
    query = query.trim();
    state.query = query;

    if (!query) {
      state.results = [];
      render();
      return;
    }

    const statusMsg = $("status-message");
    statusMsg.hidden = false;
    statusMsg.textContent = `Searching for "${query}"...`;
    $("track-list").innerHTML = "";

    try {
      const data = await api("/api/search?q=" + encodeURIComponent(query));
      if (state.query === query) {
        state.results = data.results || [];
        render();
      }
    } catch (err) {
      if (state.query === query) {
        state.results = [];
        statusMsg.hidden = false;
        statusMsg.textContent = `Search error: ${err.message}`;
      }
    }
  }

  function setInputMode(mode) {
    state.inputMode = mode;
    const playlistMode = mode === "playlist";
    $("mode-song").classList.toggle("active", !playlistMode);
    $("mode-playlist").classList.toggle("active", playlistMode);
    $("mode-song").setAttribute("aria-selected", String(!playlistMode));
    $("mode-playlist").setAttribute("aria-selected", String(playlistMode));
    $("search-input").placeholder = playlistMode
      ? "PASTE A PLAYLIST LINK"
      : "TYPE A SONG OR ARTIST";
    $("input-hint").textContent = playlistMode
      ? "YOUTUBE OR YOUTUBE MUSIC PLAYLIST LINK"
      : "SEARCH BY TITLE, ARTIST, ALBUM, OR VIDEO LINK";
    $("search-input").focus();
  }

  async function startPlaylist(url) {
    url = url.trim();
    if (!url) return;
    const panel = $("playlist-progress");
    panel.hidden = false;
    $("playlist-title").textContent = "Reading playlist…";
    $("playlist-count").textContent = "—";
    $("playlist-meter-fill").style.width = "8%";
    try {
      const data = await api("/api/playlists", {
        method: "POST",
        body: JSON.stringify({ url }),
      });
      state.playlist = {
        title: data.title,
        total: data.count,
        complete: 0,
        failed: 0,
      };
      state.currentTab = "search";
      state.query = url;
      state.results = data.jobs;
      $("playlist-title").textContent = data.title;
      $("playlist-count").textContent = `0 / ${data.count}`;
      $("playlist-meter-fill").style.width = "12%";
      showToast(`${data.count} songs queued from ${data.title}`);
      for (const item of data.jobs) {
        state.activeJobs.set(item.video_id, {
          video_id: item.video_id,
          status: "queued",
          percent: 0,
          title: item.title,
        });
        pollJob(item.job_id, item.video_id, item.title, true);
      }
      render();
    } catch (err) {
      $("playlist-title").textContent = "Playlist could not be loaded";
      $("playlist-count").textContent = err.message;
      $("playlist-meter-fill").style.width = "0%";
      showToast(err.message, true);
    }
  }

  function updatePlaylistProgress(failed = false) {
    if (!state.playlist) return;
    state.playlist.complete += 1;
    if (failed) state.playlist.failed += 1;
    const { complete, total, failed: failures } = state.playlist;
    $("playlist-count").textContent =
      `${complete - failures} saved · ${failures} failed · ${total - complete} remaining`;
    $("playlist-meter-fill").style.width =
      `${Math.round((complete / total) * 100)}%`;
    if (complete === total)
      showToast(
        failures
          ? `Playlist finished: ${complete - failures} saved, ${failures} failed. Retry failed tracks below.`
          : `Playlist saved — all ${total} songs are in your library.`,
        failures > 0,
      );
  }

  // --- Downloads ---

  async function startDownload(videoId, title, artist) {
    if (!videoId) return;

    showToast(`Downloading ${title}`);

    // Set initial job state
    state.activeJobs.set(videoId, {
      video_id: videoId,
      status: "starting",
      percent: 0,
      title: title,
    });
    render();

    try {
      const res = await api("/api/downloads", {
        method: "POST",
        body: JSON.stringify({ video_id: videoId }),
      });
      const jobId = res.job_id;
      pollJob(jobId, videoId, title);
    } catch (err) {
      state.activeJobs.delete(videoId);
      render();
      showToast(err.message, true);
    }
  }

  function pollJob(jobId, videoId, title, isPlaylist = false) {
    let polling = false;
    const timer = setInterval(async () => {
      if (polling) return;
      polling = true;
      try {
        const job = await api(`/api/jobs/${jobId}`);
        state.activeJobs.set(videoId, job);
        render();

        if (job.status === "complete") {
          clearInterval(timer);
          showToast(`Downloaded ${title}! Saved to your device.`);
          await loadLibrary();

          // Trigger browser file download directly
          if (job.track_id && !isPlaylist) {
            triggerBrowserDownload(job.track_id);
          }
          render();
          if (isPlaylist) updatePlaylistProgress();
        } else if (job.status === "error") {
          clearInterval(timer);
          showToast(`Download failed: ${job.error || "Unknown error"}`, true);
          render();
          if (isPlaylist) updatePlaylistProgress(true);
        }
      } catch (err) {
        // A temporary connection failure must not abandon a running job.
      } finally {
        polling = false;
      }
    }, 1000);
  }

  function triggerBrowserDownload(trackId) {
    const iframe = document.createElement("iframe");
    iframe.style.display = "none";
    iframe.src = `/api/tracks/${encodeURIComponent(trackId)}/file`;
    document.body.appendChild(iframe);
    setTimeout(() => iframe.remove(), 10000);
  }

  async function loadLibrary() {
    try {
      const data = await api("/api/tracks");
      state.library = data.tracks || [];
      $("nav-lib-count").textContent = state.library.length;
    } catch (err) {
      console.error("Failed to load library:", err);
    }
  }

  async function deleteTrack(trackId, title) {
    if (!confirm(`Delete "${title}" from your library?`)) return;
    try {
      await api(`/api/tracks/${encodeURIComponent(trackId)}`, {
        method: "DELETE",
      });
      if (state.currentlyPlaying && state.currentlyPlaying.id === trackId) {
        pausePlayback();
        $("player-bar").hidden = true;
      }
      showToast(`Deleted "${title}"`);
      await loadLibrary();
      render();
    } catch (err) {
      showToast(err.message, true);
    }
  }

  // --- Audio Playback ---

  async function playTrack(trackIdOrVid, isLocal, title, artist) {
    // If clicking on the currently playing track, toggle pause/play
    if (
      state.currentlyPlaying &&
      (state.currentlyPlaying.video_id === trackIdOrVid ||
        state.currentlyPlaying.id === trackIdOrVid)
    ) {
      if (state.isPlaying) {
        pausePlayback();
      } else {
        resumePlayback();
      }
      render();
      return;
    }

    // New track to play
    showToast(`Loading ${title}...`);

    let audioUrl = "";
    if (isLocal) {
      audioUrl = `/api/tracks/${encodeURIComponent(trackIdOrVid)}/audio`;
    } else {
      // Check if already in library
      const localTrack = state.library.find((t) => t.video_id === trackIdOrVid);
      if (localTrack) {
        audioUrl = `/api/tracks/${encodeURIComponent(localTrack.id)}/audio`;
      } else {
        try {
          const streamData = await api(
            `/api/stream/${encodeURIComponent(trackIdOrVid)}`,
          );
          audioUrl = streamData.url;
        } catch (err) {
          showToast(`Stream unavailable: ${err.message}`, true);
          return;
        }
      }
    }

    state.currentlyPlaying = {
      id: isLocal ? trackIdOrVid : null,
      video_id: !isLocal ? trackIdOrVid : null,
      title: title,
      artist: artist,
      url: audioUrl,
    };

    audio.src = audioUrl;
    audio
      .play()
      .then(() => {
        state.isPlaying = true;
        updatePlayerBar();
        render();
      })
      .catch((err) => {
        showToast("Playback error. Browser may not support this stream.", true);
        state.isPlaying = false;
        render();
      });
  }

  function pausePlayback() {
    audio.pause();
    state.isPlaying = false;
    $("player-toggle").textContent = "▶";
    render();
  }

  function resumePlayback() {
    audio
      .play()
      .then(() => {
        state.isPlaying = true;
        $("player-toggle").textContent = "Ⅱ";
        render();
      })
      .catch((err) => {
        showToast("Playback error", true);
      });
  }

  function updatePlayerBar() {
    if (!state.currentlyPlaying) {
      $("player-bar").hidden = true;
      return;
    }
    $("player-bar").hidden = false;
    $("player-title").textContent = state.currentlyPlaying.title;
    $("player-artist").textContent = state.currentlyPlaying.artist;
    $("player-toggle").textContent = state.isPlaying ? "Ⅱ" : "▶";
  }

  // --- Audio Event Listeners ---

  audio.addEventListener("play", () => {
    state.isPlaying = true;
    $("player-toggle").textContent = "Ⅱ";
    render();
  });

  audio.addEventListener("pause", () => {
    state.isPlaying = false;
    $("player-toggle").textContent = "▶";
    render();
  });

  audio.addEventListener("ended", () => {
    state.isPlaying = false;
    $("player-toggle").textContent = "▶";
    render();
  });

  audio.addEventListener("timeupdate", () => {
    if (!audio.duration) return;
    const current = audio.currentTime;
    const duration = audio.duration;
    $("player-time-current").textContent = formatTime(current);
    $("player-time-total").textContent = formatTime(duration);
    $("player-seek").value = (current / duration) * 100;
  });

  audio.addEventListener("loadedmetadata", () => {
    $("player-time-total").textContent = formatTime(audio.duration);
  });

  $("player-seek").addEventListener("input", (e) => {
    if (audio.duration) {
      audio.currentTime = (Number(e.target.value) / 100) * audio.duration;
    }
  });

  $("player-toggle").addEventListener("click", () => {
    if (state.isPlaying) {
      pausePlayback();
    } else {
      resumePlayback();
    }
  });

  $("player-close").addEventListener("click", () => {
    pausePlayback();
    state.currentlyPlaying = null;
    audio.removeAttribute("src");
    $("player-bar").hidden = true;
    render();
  });

  $("player-download-btn").addEventListener("click", () => {
    if (!state.currentlyPlaying) return;
    if (state.currentlyPlaying.id) {
      triggerBrowserDownload(state.currentlyPlaying.id);
    } else if (state.currentlyPlaying.video_id) {
      startDownload(
        state.currentlyPlaying.video_id,
        state.currentlyPlaying.title,
        state.currentlyPlaying.artist,
      );
    }
  });

  // --- Input and Click Event Listeners ---

  const searchInput = $("search-input");
  searchInput.addEventListener("input", (e) => {
    const val = e.target.value;
    clearTimeout(state.searchTimeout);
    if (/^https?:\/\//i.test(val.trim()) && /[?&]list=/.test(val)) {
      setInputMode("playlist");
    }
    if (state.inputMode === "song")
      state.searchTimeout = setTimeout(() => performSearch(val), 350);
    $("search-clear").hidden = !val;
  });

  searchInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      clearTimeout(state.searchTimeout);
      if (state.inputMode === "playlist") startPlaylist(searchInput.value);
      else performSearch(searchInput.value);
    }
  });

  $("search-clear").addEventListener("click", () => {
    searchInput.value = "";
    $("search-clear").hidden = true;
    searchInput.focus();
    performSearch("");
  });

  $("search-submit").addEventListener("click", () => {
    clearTimeout(state.searchTimeout);
    if (state.inputMode === "playlist") startPlaylist(searchInput.value);
    else performSearch(searchInput.value);
  });

  $("mode-song").addEventListener("click", () => setInputMode("song"));
  $("mode-playlist").addEventListener("click", () => setInputMode("playlist"));

  $("brand-btn").addEventListener("click", () => {
    switchTab("search");
    searchInput.value = "";
    $("search-clear").hidden = true;
    performSearch("");
  });

  $("nav-search-btn").addEventListener("click", () => switchTab("search"));
  $("nav-lib-btn").addEventListener("click", () => switchTab("library"));

  function switchTab(tab) {
    state.currentTab = tab;
    $("nav-search-btn").classList.toggle("active", tab === "search");
    $("nav-lib-btn").classList.toggle("active", tab === "library");
    render();
  }

  document.addEventListener("click", (e) => {
    const playBtn = e.target.closest("[data-play-track]");
    if (playBtn) {
      const idOrVid = playBtn.dataset.playTrack;
      const isLocal = playBtn.dataset.isLocal === "1";
      const title = playBtn.dataset.title;
      const artist = playBtn.dataset.artist;
      playTrack(idOrVid, isLocal, title, artist);
      return;
    }

    const dlBtn = e.target.closest("[data-download-track]");
    if (dlBtn) {
      const vid = dlBtn.dataset.downloadTrack;
      const title = dlBtn.dataset.trackTitle;
      const artist = dlBtn.dataset.trackArtist;
      startDownload(vid, title, artist);
      return;
    }

    const saveLocalBtn = e.target.closest("[data-save-local]");
    if (saveLocalBtn) {
      const trackId = saveLocalBtn.dataset.saveLocal;
      if (trackId) {
        triggerBrowserDownload(trackId);
        showToast("Downloading saved audio file...");
      }
      return;
    }

    const deleteBtn = e.target.closest("[data-delete-track]");
    if (deleteBtn) {
      const trackId = deleteBtn.dataset.deleteTrack;
      const track = state.library.find((t) => t.id === trackId);
      deleteTrack(trackId, track ? track.title : "this track");
      return;
    }
  });

  // Hotkey "/" to focus search
  document.addEventListener("keydown", (e) => {
    if (
      e.key === "/" &&
      !["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName)
    ) {
      e.preventDefault();
      switchTab("search");
      searchInput.focus();
    }
  });

  const platformApi = window.SonkipPlatform;
  if (platformApi) {
    const detectedPlatform = platformApi.detectPlatform(navigator);
    const platformDownload = platformApi.getPlatformDownload(detectedPlatform);
    $("platform-name").textContent = platformDownload.label;
    $("platform-download").href = platformDownload.href;
    $("platform-download").innerHTML =
      `${platformDownload.button} <span>↘</span>`;
    $("install-command-box").hidden = !platformDownload.command;
    if (platformDownload.command) {
      $("install-command-label").textContent = platformDownload.commandLabel;
      $("install-command").textContent = platformDownload.command;
    }
  }

  const copyInstallButton = $("copy-install-command");
  if (copyInstallButton) {
    copyInstallButton.addEventListener("click", async () => {
      const commandNode = $("install-command");
      const command = commandNode.textContent.trim();
      try {
        // Legacy execCommand can report success without updating the system
        // clipboard in embedded browsers. Never use that as proof of copying.
        await navigator.clipboard.writeText(command);
        copyInstallButton.textContent = "COPIED ✓";
        setTimeout(() => {
          copyInstallButton.textContent = "COPY COMMAND";
        }, 1800);
      } catch {
        const range = document.createRange();
        range.selectNodeContents(commandNode);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        copyInstallButton.textContent = "SELECTED — COPY MANUALLY";
        showToast(
          "Copy is blocked by your browser. The command is selected: press Ctrl+C or long-press and Copy.",
        );
      }
    });
  }

  const authDialog = $("auth-dialog");
  $("auth-open-btn").addEventListener("click", () => authDialog.showModal());
  $("auth-close-btn").addEventListener("click", () => authDialog.close());
  $("auth-file-btn").addEventListener("click", () => $("auth-file").click());
  $("auth-file").addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const cookies = await file.text();
      const result = await api("/api/auth/youtube", {
        method: "POST",
        body: JSON.stringify({ cookies }),
      });
      state.authConnected = Boolean(result.connected);
      renderAuthStatus();
      showToast("YouTube access connected locally.");
    } catch (error) {
      showToast(error.message, true);
    } finally {
      event.target.value = "";
    }
  });
  $("auth-disconnect-btn").addEventListener("click", async () => {
    try {
      await api("/api/auth/youtube", { method: "DELETE" });
      state.authConnected = false;
      renderAuthStatus();
      showToast("YouTube access removed from this device.");
    } catch (error) {
      showToast(error.message, true);
    }
  });

  // Init
  if (isStaticPages) {
    $("download-workspace").hidden = true;
    $("pages-install").hidden = false;
    document.querySelector(".header-nav").hidden = true;
    document.querySelector(".local-pill").innerHTML =
      "<i></i> GITHUB / OPEN SOURCE";
    $("auth-open-btn").hidden = true;
  } else {
    Promise.all([loadLibrary(), loadAuthStatus()]).then(() => {
      render();
    });
  }
})();
