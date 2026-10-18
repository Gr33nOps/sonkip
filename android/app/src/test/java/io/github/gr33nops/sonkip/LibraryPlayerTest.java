package io.github.gr33nops.sonkip;

import android.content.Context;
import org.json.*;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;
import org.robolectric.annotation.Config;
import java.util.*;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class) @Config(sdk=28)
public class LibraryPlayerTest {
    @Test public void savedSearchResultPlaysExistingAudioInsteadOfSavingAgain()throws Exception {
        String[] action={null,null};NativeUi ui=new NativeUi(RuntimeEnvironment.getApplication(),(a,v)->{action[0]=a;action[1]=v;});
        ui.setTracks(new JSONArray("[{\"id\":\"local-song\",\"video_id\":\"abcdefghijk\",\"title\":\"Song\"}]"));
        ui.setResults(new JSONArray("[{\"video_id\":\"abcdefghijk\",\"title\":\"Song\"}]"));
        android.widget.Button button=ui.findViewWithTag("save-abcdefghijk");
        button.performClick();assertEquals("play",action[0]);assertEquals("local-song",action[1]);
    }
    @Test public void repeatAndUpcomingEditsKeepCurrentSong() throws Exception {
        Object q=queue(false);
        assertNotNull("Queue needs repeat modes", Arrays.stream(q.getClass().getDeclaredMethods()).filter(m->m.getName().equals("setRepeat")).findFirst().orElse(null));
        call(q,"setRepeat",new Class[]{String.class},"one");
        assertEquals("a",((JSONObject)call(q,"completed",new Class[]{})).getString("id"));
        assertEquals("b",((JSONObject)call(q,"next",new Class[]{})).getString("id"));
        call(q,"setRepeat",new Class[]{String.class},"all");
        call(q,"next",new Class[]{});
        assertEquals("a",((JSONObject)call(q,"completed",new Class[]{})).getString("id"));
        call(q,"moveNext",new Class[]{int.class},1);
        assertEquals("a",((JSONObject)call(q,"current",new Class[]{})).getString("id"));
        assertEquals("c",((JSONArray)call(q,"upcoming",new Class[]{})).getJSONObject(0).getString("id"));
        call(q,"removeUpcoming",new Class[]{int.class},0);
        assertEquals("b",((JSONObject)call(q,"next",new Class[]{})).getString("id"));
    }

    @Test public void libraryCanFilterWithoutDeletingSongs() throws Exception {
        NativeUi ui=new NativeUi(RuntimeEnvironment.getApplication(),(a,v)->{});
        ui.setTracks(songs());ui.showTab("library");
        assertNotNull("Library needs search and sort",ui.findViewWithTag("library-filter"));
        call(ui,"filterLibrary",new Class[]{String.class,String.class},"second","title");
        assertNotNull(ui.findViewWithTag("play-b"));
        assertNull(ui.findViewWithTag("play-a"));
        call(ui,"filterLibrary",new Class[]{String.class,String.class},"","oldest");
        assertNotNull(ui.findViewWithTag("play-a"));
        assertNotNull(ui.findViewWithTag("play-c"));
    }

    @Test public void downloadsExposeCancellationAndRetryFailed()throws Exception {
        String[] action={null};NativeUi ui=new NativeUi(RuntimeEnvironment.getApplication(),(a,v)->action[0]=a);
        ui.setJobs(new JSONArray("[{\"id\":\"first\",\"status\":\"queued\"},{\"id\":\"second\",\"status\":\"error\"}]"));
        ui.showTab("downloads");
        assertNotNull("Downloads need cancellation",ui.findViewWithTag("cancel-first"));
        ui.findViewWithTag("cancel-first").performClick();assertEquals("cancel-download",action[0]);
        ui.findViewWithTag("retry-failed").performClick();assertEquals("retry-failed",action[0]);
    }
    private Class<?> required(String name) {
        try{return Class.forName("io.github.gr33nops.sonkip."+name);}
        catch(ClassNotFoundException e){fail("Missing library playback component: "+name);return null;}
    }
    private Object call(Object target,String method,Class<?>[] types,Object... args)throws Exception {
        return target.getClass().getDeclaredMethod(method,types).invoke(target,args);
    }
    private JSONArray songs()throws Exception {
        return new JSONArray("[{\"id\":\"c\",\"title\":\"Third\",\"created_at\":\"2026-10-03\"},{\"id\":\"b\",\"title\":\"Second\",\"created_at\":\"2026-10-02\"},{\"id\":\"a\",\"title\":\"First\",\"created_at\":\"2026-10-01\"}]");
    }
    private Object queue(boolean shuffle)throws Exception {
        return required("PlaybackQueue").getDeclaredConstructor(JSONArray.class,boolean.class,Random.class).newInstance(songs(),shuffle,new Random(7));
    }
    @Test public void libraryPlaysInDownloadOrderAndStopsAtEnd()throws Exception {
        Object q=queue(false);
        assertEquals("a",((JSONObject)call(q,"current",new Class[]{})).getString("id"));
        assertEquals("b",((JSONObject)call(q,"next",new Class[]{})).getString("id"));
        assertEquals("c",((JSONObject)call(q,"next",new Class[]{})).getString("id"));
        assertNull(call(q,"next",new Class[]{}));
        assertEquals("b",((JSONObject)call(q,"previous",new Class[]{})).getString("id"));
    }
    @Test public void shuffleVisitsEverySongOnce()throws Exception {
        Object q=queue(true); Set<String> seen=new HashSet<>();List<String> order=new ArrayList<>();
        JSONObject song=(JSONObject)call(q,"current",new Class[]{});
        while(song!=null){assertTrue(seen.add(song.getString("id")));order.add(song.getString("id"));song=(JSONObject)call(q,"next",new Class[]{});}
        assertEquals(new HashSet<>(Arrays.asList("a","b","c")),seen);
        assertNotEquals(Arrays.asList("a","b","c"),order);
    }
    @Test public void playlistsPersistAndResolveOnlyExistingSongs()throws Exception {
        Class<?> type=required("PlaylistStore");Context context=RuntimeEnvironment.getApplication();
        Object store=type.getDeclaredConstructor(Context.class).newInstance(context);
        String id=(String)call(store,"save",new Class[]{String.class,String.class,JSONArray.class},null,"My mix",new JSONArray("[\"a\",\"missing\",\"c\",\"a\"]"));
        Object reopened=type.getDeclaredConstructor(Context.class).newInstance(context);
        JSONArray lists=(JSONArray)call(reopened,"list",new Class[]{});
        assertEquals("My mix",lists.getJSONObject(0).getString("name"));
        JSONArray resolved=(JSONArray)call(reopened,"resolve",new Class[]{String.class,JSONArray.class},id,songs());
        assertEquals(2,resolved.length());assertEquals("a",resolved.getJSONObject(0).getString("id"));
        call(reopened,"delete",new Class[]{String.class},id);
        assertEquals(0,((JSONArray)call(reopened,"list",new Class[]{})).length());
        assertEquals(3,songs().length());
    }
    @Test public void libraryExposesPlayAllShuffleAndPlaylistCreation()throws Exception {
        String[] action={null};NativeUi ui=new NativeUi(RuntimeEnvironment.getApplication(),(a,v)->action[0]=a);
        ui.setTracks(songs());ui.showTab("library");
        assertNotNull(ui.findViewWithTag("library-play-all"));ui.findViewWithTag("library-play-all").performClick();assertEquals("play-all",action[0]);
        ui.findViewWithTag("library-shuffle").performClick();assertEquals("shuffle-all",action[0]);
        ui.findViewWithTag("library-playlists").performClick();assertEquals("playlists",action[0]);
        assertNotNull("Library needs backup and restore",ui.findViewWithTag("library-backup"));
        ui.findViewWithTag("library-backup").performClick();assertEquals("library-backup",action[0]);
        ui.playback("First",true,0,10000);
        ui.findViewWithTag("player-next").performClick();assertEquals("next",action[0]);
        ui.findViewWithTag("player-previous").performClick();assertEquals("previous",action[0]);
        assertNotNull("Player needs a queue/repeat/timer menu",ui.findViewWithTag("player-options"));
        ui.findViewWithTag("player-options").performClick();assertEquals("player-options",action[0]);
    }
    @Test public void librarySelectionSupportsIndividualSelectAllAndDeleteSelected()throws Exception {
        String[] action={null,null};NativeUi ui=new NativeUi(RuntimeEnvironment.getApplication(),(a,v)->{action[0]=a;action[1]=v;});
        ui.setTracks(songs());ui.showTab("library");
        assertNotNull(ui.findViewWithTag("library-select"));
        ui.findViewWithTag("library-select").performClick();
        assertNotNull(ui.findViewWithTag("select-a"));
        ui.findViewWithTag("select-a").performClick();
        assertTrue(ui.findViewWithTag("delete-selected").isEnabled());
        ui.findViewWithTag("select-all").performClick();
        ui.findViewWithTag("delete-selected").performClick();
        assertEquals("delete-selected",action[0]);
        JSONArray ids=new JSONArray(action[1]);
        assertEquals(3,ids.length());
        assertEquals(new HashSet<>(Arrays.asList("a","b","c")),new HashSet<>(Arrays.asList(ids.getString(0),ids.getString(1),ids.getString(2))));
    }
    @Test public void freshAndroidUiShowsCompatibleM4aAsTheDefault() {
        NativeUi ui=new NativeUi(RuntimeEnvironment.getApplication(),(a,v)->{});
        assertTrue(((android.widget.Button)ui.findViewWithTag("audio-format")).getText().toString().contains("M4A / AAC"));
    }
    @Test public void customPlaylistKeepsItsOwnOrderInsteadOfSortingByDownloadDate()throws Exception {
        PlaybackQueue q=new PlaybackQueue(songs(),false,false,new Random(7));
        assertEquals("c",q.current().getString("id"));assertEquals("b",q.next().getString("id"));
    }
    @Test public void renamingPlaylistPreservesMembershipAndRejectsBlankNames()throws Exception {
        PlaylistStore store=new PlaylistStore(RuntimeEnvironment.getApplication());
        String id=store.save(null,"First name",new JSONArray("[\"a\",\"b\"]"));
        store.save(id,"Renamed",store.get(id).getJSONArray("tracks"));
        assertEquals(1,store.list().length());assertEquals("Renamed",store.get(id).getString("name"));
        assertEquals("b",store.get(id).getJSONArray("tracks").getString(1));
        try{store.save(id,"   ",new JSONArray());fail("Blank playlist name accepted");}catch(IllegalArgumentException expected){}
        assertEquals("Renamed",store.get(id).getString("name"));
    }
}
