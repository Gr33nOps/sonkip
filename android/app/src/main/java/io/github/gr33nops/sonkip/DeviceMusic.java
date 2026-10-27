package io.github.gr33nops.sonkip;

import android.content.Context;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.os.Build;
import android.provider.MediaStore;
import org.json.JSONObject;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/** Checks indexed audio with enough metadata to avoid confusing versions of a song. */
final class DeviceMusic {
    private DeviceMusic() {}

    static boolean canRead(Context context) {
        String permission = Build.VERSION.SDK_INT >= 33
            ? android.Manifest.permission.READ_MEDIA_AUDIO : android.Manifest.permission.READ_EXTERNAL_STORAGE;
        return context.checkSelfPermission(permission) == PackageManager.PERMISSION_GRANTED;
    }

    static List<Song> read(Context context) {
        List<Song> songs = new ArrayList<>();
        if (!canRead(context)) return songs;
        String[] columns = {MediaStore.Audio.Media.TITLE, MediaStore.Audio.Media.ARTIST,
            MediaStore.Audio.Media.DURATION};
        try (Cursor cursor = context.getContentResolver().query(MediaStore.Audio.Media.EXTERNAL_CONTENT_URI,
                columns, MediaStore.Audio.Media.IS_MUSIC + " != 0", null, null)) {
            if (cursor != null) while (cursor.moveToNext())
                songs.add(new Song(cursor.getString(0), cursor.getString(1), cursor.getLong(2)));
        } catch (SecurityException ignored) { songs.clear(); }
        return songs;
    }

    static boolean contains(List<Song> songs, JSONObject wanted) {
        for (Song song : songs) if (matches(wanted, song.title, song.artist, song.durationMs)) return true;
        return false;
    }

    static boolean matches(JSONObject wanted, String title, String artist, long durationMs) {
        if (wanted == null || durationMs <= 0 || wanted.optInt("duration") <= 0) return false;
        String wantedTitle = normalize(wanted.optString("title"));
        String wantedArtist = normalize(wanted.optString("artist"));
        if (wantedTitle.isEmpty() || wantedArtist.isEmpty() || !wantedTitle.equals(normalize(title))
                || !wantedArtist.equals(normalize(artist))) return false;
        return Math.abs(wanted.optInt("duration") * 1000L - durationMs) <= 3000L;
    }

    private static String normalize(String value) {
        if (value == null) return "";
        return value.replaceAll("(?i)\\s*[\\[(](?:official\\s+)?(?:audio|video|music\\s+video|lyric\\s+video|lyrics)[\\])]\\s*$", "")
            .replaceAll("(?i)\\s*-\\s*topic$", "")
            .trim().replaceAll("\\s+", " ").toLowerCase(Locale.ROOT);
    }

    static final class Song {
        final String title, artist;
        final long durationMs;
        Song(String title, String artist, long durationMs) {
            this.title = title; this.artist = artist; this.durationMs = durationMs;
        }
    }
}
