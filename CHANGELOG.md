# Changelog

## 2.7.0

- Match the Android app to the website with square controls, fine borders, paper and ink surfaces, orange accents, and acid-yellow playback states.
- Apply Manrope and DM Mono to native dialogs and their actions, including format, playlist, library, backup, and playback controls.
- Refine Find, Library, Downloads, playlist review, and the expandable player for mobile use.
- Add searchable playlist song selection and clearer repeat and sleep timer states.
- Fix the Music folder menu, stray null metadata, lingering success notices, and disabled Save styling.
- Show newest download activity first so recent saves and active jobs are easy to find.

## 2.6.1

- Add first-run format, artwork, and Music folder setup on Android and desktop.
- Skip matching tracks already in the phone's indexed audio library when audio access is granted, and reuse Sonkip tracks across format choices.
- Use the site's Manrope and DM Mono fonts in the Android interface.
- Favor artist uploads in search and reject lyrics-only uploads during playlist matching.
- Save available original audio on Android when an M4A stream is unavailable, and label the fallback format in Downloads.
- Remove stale failed download entries when the song is already saved.

## 2.6.0

- Add a review-first playlist and album flow on Android and desktop: Sonkip finds every match, selects them by default, and waits for an explicit Save action before queueing downloads.
- Improve search ordering so exact title/artist matches and official artist uploads rank ahead of live, cover, remix, remaster, and unrelated variants.
- Normalize downloaded metadata for cleaner song titles, artists, album artists, artwork, release grouping, track numbers, years, and genres in external music players.
- Detect tracks from the same release even when a different YouTube upload is matched, preventing duplicate downloads without merging unrelated songs.
- Show cover art and album details in native Android search, review, download, and library views.
- Improve the website's keyboard focus, control semantics, live status announcements, contrast, touch targets, responsive dialogs, and layout stability.

## 2.5.1

- Add library selection mode on Android and desktop with individual selection, Select all, and Delete selected.
- Remove a deleted track's completed job so it no longer remains in Downloads after leaving the library.
- Make compatible M4A/AAC the default for fresh Android, macOS, Windows, and Linux installs while preserving an existing saved format choice.

## 2.5.0

- Add an optional **Music details & artwork** setting for new downloads. It is enabled by default and remembered separately on Android and desktop.
- Embed standard title, artist, album, track, year, genre, and cover tags in M4A, MP3, FLAC, and Opus files when the source provides them.
- Keep metadata failures non-fatal so an unavailable thumbnail or malformed source tag never discards playable audio.
- Notify Android's document provider after copying a song to the selected Music folder so other players can refresh it promptly.

## 2.4.1

- Add a remembered output-format choice for new songs and whole playlists.
- Support Original, MP3, M4A, Opus, and FLAC on desktop; Android offers Original, M4A/AAC, and Opus/WebM without cloud conversion.
- Preserve the selected format across retries and interrupted-download recovery.
- Fix the Android localhost bridge so song and playlist downloads keep the chosen format, and advance the APK version so the corrected bundled runtime replaces 2.3.1 cleanly.
- When YouTube exposes AAC only inside an MP4 stream on Android, extract it locally into an audio-only M4A file without transcoding.

## 2.3.1

- Add a Music folder setting on Android and desktop so existing and future songs are copied to a user-selected shared folder for playback in other music players.
- Keep Sonkip's internal library copy for reliable offline playback; changing or disabling the folder never deletes previously copied files.
- Remember completed copies, avoid overwriting unrelated files, and surface folder-access failures without losing downloads.

## 2.3.0

- Persist download jobs and recover interrupted work on reopening, retaining partial files where supported.
- Add cancellation, bounded transient retries, and Retry failed; reuse saved or already queued songs.
- Fix repeated-artist filenames and partial fragments being mistaken for finished audio.
- Add library search/sorting and ZIP backup/restore; Android backups include local playlists.
- Add Android repeat modes, upcoming-queue editing, and a sleep timer.
- Hold uncertain playlist matches for review and keep download notification progress scoped to the current batch.
- Update the website's Android download to 2.3.0. See [release notes](docs/releases/2.3.0.md) for verification and limitations.

## 2.2.0

- Added Play all in oldest-to-newest download order and library-wide Shuffle.
- Added automatic next-track playback, Previous/Next buttons, and matching notification/lock-screen controls.
- Added local playlists with song selection, add-from-library, rename, delete, ordered playback, and shuffle.
- Playlists retain their own song order. Missing library tracks are skipped when resolving a playlist; deleting a playlist does not delete audio.
- The player shows queue position and whether it is shuffled.

## 2.1.1

- Replaced the Android website wrapper with a native Find, Downloads, and Library interface.
- Added background playback, lock-screen controls, and foreground download notifications.
- Notifications use Sonkip's orange accent and vinyl artwork. Download progress includes partial transfers, saved/failed counts, and transfer speed in the expanded view.
- Added local public YouTube token generation on Android.
- Added public Spotify playlist/album and SoundCloud set imports. Track metadata is matched to YouTube; audio is downloaded from YouTube, not Spotify or SoundCloud.
- Saved audio uses readable artist/title filenames on desktop and Android. Existing library records retain their identifiers when old filenames are migrated.
- Fixed the Android startup failure caused by unsupported hard-link operations during filename migration.
- Added automated tests for native controls, background services, download notifications, playlist matching, tokens, and filename safety.
- GitHub Actions builds test artifacts; it no longer automatically publishes unverified APKs.

### Updating

Install the APK over the existing app. Do not uninstall first: uninstalling removes the app-private library. Allow notifications to see download progress. Export any files you want to keep outside Sonkip.

### Limits

Public media can still be unavailable, region-restricted, or rejected by its source. Sonkip does not bypass DRM or access restrictions. Spotify's public embed may expose only part of a large playlist; YouTube matches can be different uploads or editions. Unsupported matches are skipped.

Switching apps is supported. Force-stopping Sonkip or restarting the phone interrupts unfinished jobs; automatic recovery is not yet supported. Android and manufacturer battery restrictions can also stop background work. Android 15 applies a six-hour daily background data-sync limit.
