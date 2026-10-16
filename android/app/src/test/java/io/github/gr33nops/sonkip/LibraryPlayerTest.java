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
        ui.playback("First",true,0,10000);
        ui.findViewWithTag("player-next").performClick();assertEquals("next",action[0]);
        ui.findViewWithTag("player-previous").performClick();assertEquals("previous",action[0]);
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
