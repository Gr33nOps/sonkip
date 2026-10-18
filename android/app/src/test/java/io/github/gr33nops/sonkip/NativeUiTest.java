package io.github.gr33nops.sonkip;

import android.widget.EditText;
import android.widget.TextView;
import org.json.JSONArray;
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
}
