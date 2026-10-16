package io.github.gr33nops.sonkip;

import android.app.Notification;
import android.content.Context;
import org.json.JSONArray;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;
import org.robolectric.annotation.Config;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk=28)
public class DownloadNoticeTest {
    @Test public void oldDownloadHistoryDoesNotInflateCurrentProgress()throws Exception {
        java.lang.reflect.Method filter=java.util.Arrays.stream(DownloadNotice.class.getDeclaredMethods()).filter(m->m.getName().equals("currentBatch")).findFirst().orElse(null);
        assertNotNull("Persistent history must not count toward the current batch",filter);
        java.util.Set<String> seen=new java.util.HashSet<>();
        JSONArray selected=(JSONArray)filter.invoke(null,new JSONArray("[{\"id\":\"old\",\"status\":\"complete\"},{\"id\":\"new\",\"status\":\"downloading\",\"percent\":20}]"),seen);
        assertEquals(1,selected.length());
        Notification first=DownloadNotice.build(RuntimeEnvironment.getApplication(),selected,false);
        assertEquals(20,first.extras.getInt(Notification.EXTRA_PROGRESS));
        selected=(JSONArray)filter.invoke(null,new JSONArray("[{\"id\":\"old\",\"status\":\"complete\"},{\"id\":\"new\",\"status\":\"complete\"}]"),seen);
        assertEquals(1,selected.length());assertEquals("new",selected.getJSONObject(0).getString("id"));
    }
    private Notification notice(String jobs, boolean importing) throws Exception {
        Class<?> type;
        try { type=Class.forName("io.github.gr33nops.sonkip.DownloadNotice"); }
        catch(ClassNotFoundException e) { fail("Missing job-aware download notification"); return null; }
        return (Notification)type.getDeclaredMethod("build",Context.class,JSONArray.class,boolean.class)
            .invoke(null,RuntimeEnvironment.getApplication(),new JSONArray(jobs),importing);
    }
    @Test public void activeTransferShowsPercentageEvenDuringAnotherImport() throws Exception {
        Notification n=notice("[{\"status\":\"downloading\",\"percent\":45,\"speed\":1048576}]",true);
        assertEquals(45,n.extras.getInt(Notification.EXTRA_PROGRESS));
        assertFalse(n.extras.getBoolean(Notification.EXTRA_PROGRESS_INDETERMINATE));
        assertTrue(n.extras.getCharSequence(Notification.EXTRA_TEXT).toString().contains("45%"));
    }
    @Test public void queueProgressIncludesPartialSongWithoutCallingFailuresSaved() throws Exception {
        Notification n=notice("[{\"status\":\"complete\"},{\"status\":\"downloading\",\"percent\":50},{\"status\":\"queued\"},{\"status\":\"error\"}]",false);
        assertEquals(62,n.extras.getInt(Notification.EXTRA_PROGRESS));
        String text=n.extras.getCharSequence(Notification.EXTRA_TEXT).toString();
        assertTrue(text.contains("1 saved"));assertTrue(text.contains("1 failed"));
    }
    @Test public void preparationDoesNotInventTransferProgress() throws Exception {
        Notification n=notice("[{\"status\":\"starting\",\"percent\":0}]",false);
        assertTrue(n.extras.getBoolean(Notification.EXTRA_PROGRESS_INDETERMINATE));
        assertTrue(n.extras.getCharSequence(Notification.EXTRA_TEXT).toString().contains("Preparing"));
    }
}
