package io.github.gr33nops.sonkip;

import android.widget.EditText;
import android.widget.TextView;
import android.widget.CheckBox;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;
import org.robolectric.annotation.Config;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk = 28)
public class NativeUiTest {
    private String action, value;
    private NativeUi screen() {
        return new NativeUi(RuntimeEnvironment.getApplication(), (a, v) -> {action = a; value = v;});
    }
    @Test public void findScreenKeepsBrandMessageAndNativeSearchTogether() {
        NativeUi ui = screen();
        TextView title = ui.findViewWithTag("brand-headline");
        assertNotNull(title);
        assertEquals("FIND IT.\nSAVE IT.\nPLAY IT.", title.getText().toString());
        assertNotNull(ui.findViewWithTag("query"));
        assertNotNull(ui.findViewWithTag("search"));
    }
    @Test public void searchSubmitsTrimmedInputAndRejectsEmptyInput() {
        NativeUi ui = screen();
        EditText input = ui.findViewWithTag("query");
        assertNotNull("Find must have a native text input", input);
        ui.findViewWithTag("search").performClick();
        assertNull(action);
        input.setText("  Tame Impala  ");
        ui.findViewWithTag("search").performClick();
        assertEquals("search", action);
        assertEquals("Tame Impala", value);
    }
    @Test public void libraryNavigationShowsEmptyState() {
        NativeUi ui = screen();
        assertNotNull("Native library tab is missing", ui.findViewWithTag("tab-library"));
        ui.findViewWithTag("tab-library").performClick();
        assertEquals("library", value);
        assertNotNull(ui.findViewWithTag("empty-library"));
    }
    @Test public void savedSongPlaysUsingLocalIdNotYoutubeId() throws Exception {
        NativeUi ui = screen();
        ui.setTracks(new JSONArray("[{\"id\":\"local123\",\"video_id\":\"NMRhx71bGo4\",\"title\":\"Let It Happen\",\"artist\":\"Tame Impala\",\"duration\":468}]"));
        assertNotNull("Native library tab is missing", ui.findViewWithTag("tab-library"));
        ui.findViewWithTag("tab-library").performClick();
        assertNotNull(ui.findViewWithTag("play-local123"));
        ui.findViewWithTag("play-local123").performClick();
        assertEquals("play", action);
        assertEquals("local123", value);
    }
    @Test public void failedDownloadShowsReasonAndRetriesOriginalVideo() throws Exception {
        NativeUi ui = screen();
        ui.setJobs(new JSONArray("[{\"id\":\"job1\",\"video_id\":\"NMRhx71bGo4\",\"status\":\"error\",\"error\":\"Network unavailable\",\"percent\":0}]"));
        assertNotNull("Native downloads tab is missing", ui.findViewWithTag("tab-downloads"));
        ui.findViewWithTag("tab-downloads").performClick();
        TextView reason = ui.findViewWithTag("error-job1");
        assertNotNull(reason);
        assertTrue(reason.getText().toString().contains("Network unavailable"));
        ui.findViewWithTag("retry-job1").performClick();
        assertEquals("save", action);
        assertEquals("NMRhx71bGo4", value);
    }
    @Test public void playerControlTogglesWithoutLosingLibraryNavigation() {
        NativeUi ui = screen();
        ui.playback("Let It Happen", true, 10000, 468000);
        TextView toggle = ui.findViewWithTag("player-toggle");
        assertEquals("Pause", toggle.getText().toString());
        toggle.performClick();
        assertEquals("toggle", action);
        ui.findViewWithTag("tab-library").performClick();
        assertEquals("Pause", ((TextView)ui.findViewWithTag("player-toggle")).getText().toString());
    }
    @Test public void busySearchCannotSubmitTwice() {
        NativeUi ui = screen();
        ui.setBusy(true);
        assertFalse(ui.findViewWithTag("search").isEnabled());
        ui.setBusy(false);
        assertTrue(ui.findViewWithTag("search").isEnabled());
    }
    @Test public void findScreenOpensAudioFormatChoice() {
        NativeUi ui = screen();
        assertNotNull(ui.findViewWithTag("audio-format"));
        ui.findViewWithTag("audio-format").performClick();
        assertEquals("audio-format", action);
    }
    @Test public void findScreenExposesMusicDetailsAndArtworkToggle() {
        NativeUi ui = screen();
        assertNotNull(ui.findViewWithTag("embed-metadata"));
        ui.findViewWithTag("embed-metadata").performClick();
        assertEquals("embed-metadata", action);
    }
    @Test public void playlistPreviewRequiresExplicitSaveOfSelectedSongs() throws Exception {
        NativeUi ui = screen();
        ui.setPlaylistPreview(new JSONObject("{\"preview_id\":\"preview123\",\"title\":\"Road trip\",\"entries\":[{\"video_id\":\"dQw4w9WgXcQ\",\"title\":\"One\",\"artist\":\"Artist\",\"duration\":10},{\"video_id\":\"M7lc1UVf-VE\",\"title\":\"Two\",\"artist\":\"Artist\",\"duration\":20}]}"));

        CheckBox first = ui.findViewWithTag("playlist-select-dQw4w9WgXcQ");
        assertNotNull("Playlist tracks must be selectable before download", first);
        assertTrue(first.isChecked());
        first.setChecked(false);
        ui.findViewWithTag("playlist-save").performClick();

        assertEquals("save-playlist", action);
        JSONObject submitted = new JSONObject(value);
        assertEquals("preview123", submitted.getString("preview_id"));
        assertEquals(1, submitted.getJSONArray("video_ids").length());
        assertEquals("M7lc1UVf-VE", submitted.getJSONArray("video_ids").getString(0));
    }
    @Test public void playlistPreviewCanDeselectAndSelectAll() throws Exception {
        NativeUi ui = screen();
        ui.setPlaylistPreview(new JSONObject("{\"preview_id\":\"preview123\",\"title\":\"Road trip\",\"entries\":[{\"video_id\":\"dQw4w9WgXcQ\",\"title\":\"One\"},{\"video_id\":\"M7lc1UVf-VE\",\"title\":\"Two\"}]}"));

        ui.findViewWithTag("playlist-deselect-all").performClick();
        assertFalse(ui.findViewWithTag("playlist-save").isEnabled());
        assertEquals("0 selected", ((TextView)ui.findViewWithTag("playlist-selected-count")).getText().toString());
        ui.findViewWithTag("playlist-select-all").performClick();
        assertTrue(ui.findViewWithTag("playlist-save").isEnabled());
        assertEquals("2 selected", ((TextView)ui.findViewWithTag("playlist-selected-count")).getText().toString());
    }
    @Test public void searchResultShowsAlbumYearAndDurationBeforeSaving() throws Exception {
        NativeUi ui = screen();
        ui.setResults(new JSONArray("[{\"video_id\":\"dQw4w9WgXcQ\",\"title\":\"Song\",\"artist\":\"Artist\",\"album\":\"The Album\",\"release_date\":\"2024-02-03\",\"duration\":125}]"));

        TextView metadata = ui.findViewWithTag("metadata-dQw4w9WgXcQ");
        assertNotNull(metadata);
        assertEquals("Artist  ·  The Album  ·  2024  ·  2:05", metadata.getText().toString());
    }
    @Test public void artworkLoaderOnlyAcceptsKnownHttpsImageHosts() {
        assertTrue(NativeUi.isTrustedArtworkUrl("https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"));
        assertTrue(NativeUi.isTrustedArtworkUrl("https://i.scdn.co/image/example"));
        assertFalse(NativeUi.isTrustedArtworkUrl("http://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"));
        assertFalse(NativeUi.isTrustedArtworkUrl("https://tracker.example/cover.jpg"));
        assertFalse(NativeUi.isTrustedArtworkUrl("not-a-url"));
    }
    @Test public void busyPlaylistSubmissionCannotBeStartedTwice() throws Exception {
        NativeUi ui = screen();
        ui.setPlaylistPreview(new JSONObject("{\"preview_id\":\"preview123\",\"entries\":[{\"video_id\":\"dQw4w9WgXcQ\",\"title\":\"One\"}]}"));

        ui.setBusy(true);

        assertFalse(ui.findViewWithTag("playlist-save").isEnabled());
    }
}
