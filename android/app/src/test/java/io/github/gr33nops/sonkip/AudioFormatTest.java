package io.github.gr33nops.sonkip;

import org.json.JSONObject;
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
}
