(() => {
  "use strict";

  const state = {
    currentTab: "search", // 'search' | 'library'
    inputMode: "song", // 'song' | 'playlist'
    query: "",
    results: [],
    library: [],
    libraryQuery: "",
    librarySort: "newest",
    librarySelectionMode: false,
    selectedTracks: new Set(),
    musicFolder: '',
    activeJobs: new Map(), // video_id -> job
    jobPollers: new Map(),
    currentlyPlaying: null, // { id, video_id, title, artist, url }
    isPlaying: false,
    searchTimeout: null,
    toastTimeout: null,
    pollInterval: null,
    playlist: null,
    playlistSelected: new Set(),
    authConnected: false,
    audioFormat: ["original", "mp3", "m4a", "opus", "flac"].includes(
      localStorage.getItem("sonkip-audio-format"),
    )
      ? localStorage.getItem("sonkip-audio-format")
      : "m4a",
    embedMetadata: localStorage.getItem("sonkip-embed-metadata") !== "false",
  };

  const $ = (id) => document.getElementById(id);
  const audio = $("audio-el");
  const isStaticPages = !window.SonkipPlatform.isLocalAppHost(
    window.location.hostname,
  );

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

  function showFirstRunSetup() {
    if (localStorage.getItem("sonkip-setup-complete")) return;
    $("setup-format").value = state.audioFormat;
    $("setup-artwork").checked = state.embedMetadata;
    $("setup-dialog").showModal();
  }

  function finishFirstRunSetup() {
    state.audioFormat = $("setup-format").value;
    state.embedMetadata = $("setup-artwork").checked;
    $("audio-format").value = state.audioFormat;
    $("embed-metadata").checked = state.embedMetadata;
    localStorage.setItem("sonkip-audio-format", state.audioFormat);
    localStorage.setItem("sonkip-embed-metadata", String(state.embedMetadata));
    localStorage.setItem("sonkip-setup-complete", "true");
    const chooseFolder = $("setup-folder").checked;
    $("setup-dialog").close();
    if (chooseFolder) $("music-folder").click();
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

  function filteredLibrary() {
    const query = state.libraryQuery.toLocaleLowerCase().trim();
    const songs = state.library.filter(track => `${track.title} ${track.artist} ${track.album || ""} ${track.album_artist || ""}`.toLocaleLowerCase().includes(query));
    if (state.librarySort === "oldest") songs.reverse();
    else if (["title", "artist", "album"].includes(state.librarySort)) songs.sort((a,b) => String(a[state.librarySort] || "").localeCompare(String(b[state.librarySort] || "")));
    return songs;
  }

  function selectAllVisible() {
    for (const track of filteredLibrary()) state.selectedTracks.add(track.id);
    render();
  }

  function clearLibrarySelection() {
    state.selectedTracks.clear();
    render();
  }

  // --- Rendering ---

  function render() {
    const list = $("track-list");
    const statusMsg = $("status-message");
    const searchClear = $("search-clear");
    const mainContent = document.querySelector(".main-content");

    searchClear.hidden = !$("search-input").value;
    $("library-tools").hidden = state.currentTab !== "library";
    $("library-select").hidden = state.librarySelectionMode;
    $("library-select-all").hidden = !state.librarySelectionMode;
    $("library-delete-selected").hidden = !state.librarySelectionMode;
    $("library-selection-done").hidden = !state.librarySelectionMode;
    $("library-selection-count").hidden = !state.librarySelectionMode;
    $("library-delete-selected").disabled = state.selectedTracks.size === 0;
    $("library-selection-count").textContent = `${state.selectedTracks.size} selected`;

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
      list.innerHTML = filteredLibrary()
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
        <button class="track-download-btn downloaded" data-save-local="${safe(track.id)}" aria-label="Download ${safe(track.title)} to this device" title="Download file to device">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3v12m0 0 5-5m-5 5-5-5M4 21h16"/></svg>
          <span class="hidden sm:inline">DOWNLOAD</span>
        </button>
        <button class="track-delete-btn" data-delete-track="${safe(track.id)}" aria-label="Delete ${safe(track.title)} from library" title="Delete from library">×</button>
      `;
    } else if (job && job.status !== "complete" && job.status !== "error") {
      const pct = job.percent ? `${Math.round(job.percent)}%` : "...";
      dlHtml = `
        <button class="track-download-btn" aria-label="Downloading ${safe(track.title)} ${safe(pct)}" disabled>
          <span class="spinner"></span>
          <span class="hidden sm:inline">DOWNLOADING ${pct}</span>
        </button>
        ${job.id ? `<button class="track-download-btn" data-cancel-job="${safe(job.id)}">Cancel</button>` : ""}
      `;
    } else if (isLocalSaved) {
      const localItem = state.library.find(
        (t) => t.video_id === track.video_id,
      );
      dlHtml = `
        <button class="track-download-btn downloaded" data-save-local="${safe(localItem ? localItem.id : "")}" aria-label="Download ${safe(track.title)} to this device" title="Saved in library. Click to save file again">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3v12m0 0 5-5m-5 5-5-5M4 21h16"/></svg>
          <span class="hidden sm:inline">DOWNLOADED ✓</span>
        </button>
      `;
    } else {
      dlHtml = `
        <button class="track-download-btn" data-download-track="${safe(track.video_id || "")}" data-track-title="${safe(track.title)}" data-track-artist="${safe(track.artist)}" aria-label="Download ${safe(track.title)}">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3v12m0 0 5-5m-5 5-5-5M4 21h16"/></svg>
          <span class="hidden sm:inline">DOWNLOAD</span>
        </button>
      `;
    }

    const tagHtml =
      isLocal && track.extension
        ? `<span class="track-tag">${safe(track.extension.toUpperCase())}</span>`
        : "";
    const selectionHtml = isLocal && state.librarySelectionMode
      ? `<button class="track-select-btn${state.selectedTracks.has(track.id) ? " selected" : ""}" data-select-track="${safe(track.id)}" aria-pressed="${state.selectedTracks.has(track.id)}" aria-label="Select ${safe(track.title)}">${state.selectedTracks.has(track.id) ? "✓" : "○"}</button>`
      : "";

    return `
      <article class="track-item" data-vid="${safe(track.video_id || "")}" data-tid="${safe(track.id || "")}">
        ${selectionHtml}
        ${selectionHtml ? "" : (track.thumbnail || track.artwork_url ? `<img class="track-artwork" src="${safe(track.thumbnail || track.artwork_url)}" alt="" width="56" height="56" loading="lazy" />` : `<span class="track-artwork artwork-placeholder" aria-hidden="true">♪</span>`)}
        <button
          class="${playClass}"
          data-play-track="${safe((isLocal ? track.id : track.video_id) || "")}"
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
          ${track.album || track.duration != null || track.year ? `<p class="track-metadata">${[track.album, track.year, track.duration != null ? formatTime(track.duration) : ""].filter(Boolean).map(safe).join(" · ")}</p>` : ""}
          ${track.is_best_match && !isLocal ? `<span class="best-match">BEST MATCH</span>` : ""}
          ${track.needs_review ? `<p class="track-error">Check this match before downloading. The version or duration is uncertain.</p>` : ""}
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
    $("mode-song").setAttribute("aria-pressed", String(!playlistMode));
    $("mode-playlist").setAttribute("aria-pressed", String(playlistMode));
    $("search-input").placeholder = playlistMode
      ? "PASTE A PLAYLIST LINK…"
      : "TYPE A SONG, ARTIST, OR ALBUM…";
    $("input-hint").textContent = playlistMode
      ? "YOUTUBE, SPOTIFY, OR SOUNDCLOUD · AUDIO MATCHED ON YOUTUBE"
      : "SEARCH BY TITLE, ARTIST, ALBUM, OR VIDEO LINK";
    $("search-input").focus();
  }

  function renderPlaylistPreview() {
    const preview = $("playlist-preview");
    if (!preview || !state.playlist?.entries) return;
    preview.hidden = false;
    preview.innerHTML = state.playlist.entries.map((track) => {
      const artwork = track.thumbnail || track.artwork_url;
      return `
        <label class="playlist-track">
          <input type="checkbox" data-playlist-track="${safe(track.video_id)}" ${state.playlistSelected.has(track.video_id) ? "checked" : ""} />
          ${artwork ? `<img src="${safe(artwork)}" alt="" width="48" height="48" loading="lazy" />` : `<span class="playlist-artwork-placeholder artwork-placeholder" aria-hidden="true">♪</span>`}
          <span><strong>${safe(track.title)}</strong><small>${safe(track.artist)}${track.album ? ` · ${safe(track.album)}` : ""}${track.duration != null ? ` · ${formatTime(track.duration)}` : ""}</small></span>
        </label>`;
    }).join("");
    $("playlist-selection-count").textContent = `${state.playlistSelected.size} selected`;
    $("playlist-save").disabled = state.playlistSelected.size === 0;
  }

  async function startPlaylist(url) {
    url = url.trim();
    if (!url) return;
    const panel = $("playlist-progress");
    panel.hidden = false;
    state.playlist = null;
    state.playlistSelected.clear();
    $("playlist-preview").hidden = true;
    const previewActions = $("playlist-preview-actions");
    if (previewActions) previewActions.hidden = true;
    $("playlist-title").textContent = "Reading playlist and finding YouTube matches…";
    $("playlist-count").textContent = "—";
    $("playlist-meter-fill").style.width = "8%";
    try {
      const data = await api("/api/playlists", {
        method: "POST",
        body: JSON.stringify({ url }),
      });
      state.playlist = {
        previewId: data.preview_id,
        title: data.title,
        entries: data.entries || [],
        total: 0,
        complete: 0,
        failed: 0,
      };
      state.playlistSelected = new Set(state.playlist.entries.map((entry) => entry.video_id));
      if (previewActions) previewActions.hidden = false;
      $("playlist-title").textContent = data.title + (data.notice ? ` · ${data.notice}` : "");
      $("playlist-count").textContent = `${data.count} tracks · ${state.playlistSelected.size} selected`;
      $("playlist-meter-fill").style.width = "0%";
      renderPlaylistPreview();
      showToast(`Review ${data.count} tracks, then press Save`);
    } catch (err) {
      $("playlist-title").textContent = "Playlist could not be loaded";
      $("playlist-count").textContent = err.message;
      $("playlist-meter-fill").style.width = "0%";
      showToast(err.message, true);
    }
  }

  async function savePlaylistSelection() {
    if (!state.playlist || state.playlistSelected.size === 0) return;
    $("playlist-save").disabled = true;
    try {
      const data = await api("/api/playlists/download", {
        method: "POST",
        body: JSON.stringify({
          preview_id: state.playlist.previewId,
          video_ids: Array.from(state.playlistSelected),
          audio_format: state.audioFormat,
          embed_metadata: state.embedMetadata,
        }),
      });
      state.playlist.total = data.count;
      state.playlist.complete = 0;
      state.playlist.failed = 0;
      state.currentTab = "search";
      state.query = data.title;
      state.results = data.jobs;
      $("playlist-preview").hidden = true;
      $("playlist-preview-actions").hidden = true;
      $("playlist-count").textContent = `0 / ${data.count}`;
      $("playlist-meter-fill").style.width = "8%";
      for (const item of data.jobs) {
        state.activeJobs.set(item.video_id, {video_id: item.video_id, status: "queued", percent: 0, title: item.title});
        pollJob(item.job_id, item.video_id, item.title, true);
      }
      render();
      showToast(`${data.count} selected songs queued from ${data.title}`);
    } catch (err) {
      $("playlist-save").disabled = false;
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
      const source = (state.results || []).find((track) => track.video_id === videoId);
      const res = await api("/api/downloads", {
        method: "POST",
        body: JSON.stringify({
          video_id: videoId,
          audio_format: state.audioFormat,
          embed_metadata: state.embedMetadata,
          ...(source ? {metadata: source} : {}),
        }),
      });
      const jobId = res.job_id;
      pollJob(jobId, videoId, title);
    } catch (err) {
      state.activeJobs.delete(videoId);
      render();
      showToast(err.message, true);
    }
  }

  function pollJob(jobId, videoId, title, isPlaylist = false, exportFile = !isPlaylist) {
    if(state.jobPollers.has(jobId))return;
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
          state.jobPollers.delete(jobId);
          showToast(`Downloaded ${title}! Saved to your device.`);
          await loadLibrary();

          // Trigger browser file download directly
          if (job.track_id && exportFile && !state.musicFolder) {
            triggerBrowserDownload(job.track_id);
          }
          render();
          if (isPlaylist) updatePlaylistProgress();
        } else if (job.status === "error") {
          clearInterval(timer);
          state.jobPollers.delete(jobId);
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
    state.jobPollers.set(jobId,timer);
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
      if(!isStaticPages) {
        const folder=await api('/api/music-folder');state.musicFolder=folder.folder;
        if(folder.error)showToast(`Saved in Sonkip, but folder copy failed: ${folder.error}`,true);
      }
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

  async function deleteSelectedTracks() {
    const trackIds = Array.from(state.selectedTracks);
    if (!trackIds.length || !confirm(`Delete ${trackIds.length} selected song${trackIds.length === 1 ? "" : "s"} from your library?`)) return;
    try {
      const result = await api("/api/tracks/delete-selected", {
        method: "POST",
        body: JSON.stringify({ track_ids: trackIds }),
      });
      if (state.currentlyPlaying && trackIds.includes(state.currentlyPlaying.id)) {
        pausePlayback();
        state.currentlyPlaying = null;
        $("player-bar").hidden = true;
      }
      state.selectedTracks.clear();
      state.librarySelectionMode = false;
      await loadLibrary();
      render();
      showToast(`${result.deleted.length} song${result.deleted.length === 1 ? "" : "s"} deleted`);
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
    if (/^https?:\/\//i.test(val.trim()) && (/[?&]list=/.test(val) || /^https:\/\/(open\.spotify\.com\/(?:intl-[a-z]+\/)?(?:playlist|album)\/|(?:www\.)?soundcloud\.com\/[^/]+\/sets\/)/i.test(val.trim()))) {
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
  $("playlist-select-all").addEventListener("click", () => {
    state.playlistSelected = new Set((state.playlist?.entries || []).map((entry) => entry.video_id));
    renderPlaylistPreview();
  });
  $("playlist-deselect-all").addEventListener("click", () => {
    state.playlistSelected.clear();
    renderPlaylistPreview();
  });
  $("playlist-preview").addEventListener("change", (event) => {
    const videoId = event.target.dataset.playlistTrack;
    if (!videoId) return;
    if (event.target.checked) state.playlistSelected.add(videoId);
    else state.playlistSelected.delete(videoId);
    renderPlaylistPreview();
  });
  $("playlist-save").addEventListener("click", savePlaylistSelection);
  $("audio-format").value = state.audioFormat;
  $("audio-format").addEventListener("change", (event) => {
    state.audioFormat = event.target.value;
    localStorage.setItem("sonkip-audio-format", state.audioFormat);
    showToast(`New downloads will be saved as ${event.target.selectedOptions[0].textContent.split(" · ")[0]}.`);
  });
  $("embed-metadata").checked = state.embedMetadata;
  $("embed-metadata").addEventListener("change", (event) => {
    state.embedMetadata = event.target.checked;
    localStorage.setItem("sonkip-embed-metadata", String(state.embedMetadata));
    showToast(
      state.embedMetadata
        ? "New downloads will include song details and artwork."
        : "Song details and artwork are off for new downloads.",
    );
  });
  $("setup-save").addEventListener("click", finishFirstRunSetup);

  $("brand-btn").addEventListener("click", () => {
    switchTab("search");
    searchInput.value = "";
    $("search-clear").hidden = true;
    performSearch("");
  });

  $("nav-search-btn").addEventListener("click", () => switchTab("search"));
  $("nav-lib-btn").addEventListener("click", () => switchTab("library"));
  $("library-query").addEventListener("input", event => {state.libraryQuery=event.target.value;render();});
  $("library-sort").addEventListener("change", event => {state.librarySort=event.target.value;render();});
  $("library-select").addEventListener("click", () => {state.librarySelectionMode=true;state.selectedTracks.clear();render();});
  $("library-select-all").addEventListener("click", selectAllVisible);
  $("library-delete-selected").addEventListener("click", deleteSelectedTracks);
  $("library-selection-done").addEventListener("click", () => {state.librarySelectionMode=false;clearLibrarySelection();});
  $("restore-backup").addEventListener("click", () => $("backup-file").click());
  $("music-folder").addEventListener("click", async () => {
    try {const config=await api('/api/music-folder');$('folder-path').value=config.folder;$('folder-status').textContent=config.error||'Choose a folder on this computer.';$('folder-dialog').showModal();}
    catch(error){showToast(error.message,true);}
  });
  $('folder-browse').addEventListener('click', async () => {
    $('folder-browse').disabled=true;$('folder-status').textContent='Choose a folder in the system dialog…';
    try {const selected=await api('/api/music-folder/pick',{method:'POST'});if(selected.folder)$('folder-path').value=selected.folder;$('folder-status').textContent='Press Save folder to copy your music.';}
    catch(error){$('folder-status').textContent=error.message;}finally{$('folder-browse').disabled=false;}
  });
  async function saveMusicFolder(folder) {
    $('folder-save').disabled=true;$('folder-disable').disabled=true;$('folder-status').textContent='Saving folder and copying music…';
    try {const result=await api('/api/music-folder',{method:'POST',body:JSON.stringify({folder})});state.musicFolder=result.folder;$('folder-path').value=result.folder;$('folder-status').textContent=result.error|| (result.folder?'Music copied. Future downloads will be copied here automatically.':'Automatic copies stopped. Existing files are kept.');}
    catch(error){$('folder-status').textContent=error.message;}finally{$('folder-save').disabled=false;$('folder-disable').disabled=false;}
  }
  $('folder-save').addEventListener('click',()=>saveMusicFolder($('folder-path').value));
  $('folder-disable').addEventListener('click',()=>saveMusicFolder(''));
  $("backup-file").addEventListener("change", async event => {
    const file=event.target.files[0];if(!file)return;
    if(!confirm("Restore this Sonkip backup? Missing songs will be added; existing songs are kept.")){event.target.value="";return;}
    try {showToast("Restoring backup…");const result=await api("/api/backup/restore",{method:"POST",body:file,headers:{"Content-Type":"application/zip"}});await loadLibrary();render();showToast(`${result.imported} songs restored`);}
    catch(error){showToast(error.message,true);}finally{event.target.value="";}
  });
  $("show-downloads").addEventListener("click", () => loadDownloadHistory().catch(error=>showToast(error.message,true)));
  $("retry-failed").addEventListener("click", async () => {
    try {const result=await api("/api/jobs/retry-failed",{method:"POST"});await loadDownloadHistory();showToast(`${result.job_ids.length} downloads queued again`);}
    catch(error){showToast(error.message,true);}
  });

  async function loadDownloadHistory() {
    const data=await api("/api/jobs");
    state.activeJobs.clear();
    state.query="Downloads";
    state.results=data.jobs.map(job=>{
      state.activeJobs.set(job.video_id,job);
      const track=state.library.find(track=>track.video_id===job.video_id);
      const title=track?.title || job.title || job.video_id;
      if(!["error","complete"].includes(job.status))pollJob(job.id,job.video_id,title,false,false);
      return {video_id:job.video_id,title,artist:track?.artist || job.artist || "Download history"};
    });
    switchTab("search");
  }

  function switchTab(tab) {
    state.currentTab = tab;
    $("nav-search-btn").classList.toggle("active", tab === "search");
    $("nav-lib-btn").classList.toggle("active", tab === "library");
    render();
  }

  document.addEventListener("click", (e) => {
    const select=e.target.closest("[data-select-track]");
    if(select){const id=select.dataset.selectTrack;if(state.selectedTracks.has(id))state.selectedTracks.delete(id);else state.selectedTracks.add(id);render();return;}
    const cancel=e.target.closest("[data-cancel-job]");
    if(cancel){api(`/api/jobs/${encodeURIComponent(cancel.dataset.cancelJob)}/cancel`,{method:"POST"}).then(loadDownloadHistory).catch(error=>showToast(error.message,true));return;}
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
      showFirstRunSetup();
      api("/api/jobs/resume-interrupted",{method:"POST"}).then(result=>{
        if(result.job_ids.length)loadDownloadHistory().catch(error=>showToast(error.message,true));
      }).catch(error=>showToast(error.message,true));
    });
  }
})();
