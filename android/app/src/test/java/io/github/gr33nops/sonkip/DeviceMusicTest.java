package io.github.gr33nops.sonkip;

import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk = 28)
public class DeviceMusicTest {
    @Test public void skipsTheSameRecordingAlreadyOnThePhone() throws Exception {
        JSONObject wanted = new JSONObject().put("title", "Song (Official Audio)")
            .put("artist", "Artist - Topic").put("duration", 201);
        assertTrue(DeviceMusic.matches(wanted, "Song", "Artist", 201000));
    }
    @Test public void differentVersionsAndMissingDetailsAreNotSkipped() throws Exception {
        JSONObject wanted = new JSONObject().put("title", "Song").put("artist", "Artist").put("duration", 201);
        assertFalse(DeviceMusic.matches(wanted, "Song", "Artist", 260000));
        assertFalse(DeviceMusic.matches(wanted, "Song", "Another Artist", 201000));
        assertFalse(DeviceMusic.matches(new JSONObject().put("title", "Song").put("artist", "Artist"),
            "Song", "Artist", 201000));
    }
}
