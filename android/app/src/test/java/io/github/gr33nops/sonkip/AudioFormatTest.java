package io.github.gr33nops.sonkip;

import org.json.JSONObject;
import org.json.JSONArray;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk = 28)
public class AudioFormatTest {
    @Test public void requestBodiesIncludeTheSelectedAudioFormat() throws Exception {
        JSONObject song = MainActivity.downloadRequest("NMRhx71bGo4", "mp3", false);
        assertEquals("NMRhx71bGo4", song.getString("video_id"));
        assertEquals("mp3", song.getString("audio_format"));
        assertFalse(song.getBoolean("embed_metadata"));
        JSONObject playlist = MainActivity.playlistRequest("https://example.test/list", "flac", true);
        assertEquals("https://example.test/list", playlist.getString("url"));
        assertEquals("flac", playlist.getString("audio_format"));
        assertTrue(playlist.getBoolean("embed_metadata"));
    }
    @Test public void playlistDownloadBodyCarriesPreviewSelectionAndSettings() throws Exception {
        JSONObject request = MainActivity.playlistDownloadRequest(
            "preview123", new JSONArray("[\"dQw4w9WgXcQ\",\"M7lc1UVf-VE\"]"), "m4a", false
        );

        assertEquals("preview123", request.getString("preview_id"));
        assertEquals(2, request.getJSONArray("video_ids").length());
        assertEquals("m4a", request.getString("audio_format"));
        assertFalse(request.getBoolean("embed_metadata"));
    }
}
