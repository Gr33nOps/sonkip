# Changelog

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
