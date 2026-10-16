package io.github.gr33nops.sonkip;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.Intent;
import android.graphics.Insets;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.WindowInsets;
import android.view.WindowManager;
import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.*;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

public class MainActivity extends Activity {
    private static final String BASE = "http://127.0.0.1:8765";
    private static final AtomicBoolean backendStarted = new AtomicBoolean();
    private static volatile String backendError;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService requests = Executors.newFixedThreadPool(3);
    private final AtomicBoolean refreshing = new AtomicBoolean();
    private NativeUi ui;
    private JSONArray tracks = new JSONArray();
    private boolean ready, active, importing;
    private String exportId;
    private PlaylistStore playlists;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        playlists=new PlaylistStore(this);
        ui = new NativeUi(this, this::action);
        setContentView(ui);
        ui.setOnApplyWindowInsetsListener((view,insets) -> {
            if(Build.VERSION.SDK_INT >= 30) {
                Insets bars = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.ime());
                view.setPadding(bars.left,bars.top,bars.right,bars.bottom);
            } else view.setPadding(insets.getSystemWindowInsetLeft(),insets.getSystemWindowInsetTop(),insets.getSystemWindowInsetRight(),insets.getSystemWindowInsetBottom());
            return insets;
        });
        getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS)
                != android.content.pm.PackageManager.PERMISSION_GRANTED)
            requestPermissions(new String[]{android.Manifest.permission.POST_NOTIFICATIONS}, 42);
        try { PublicTokenProvider.initialize(this); }
        catch(Exception error) { ui.notice("Downloads unavailable: "+error.getMessage(),true); }
        startBackend(getApplicationContext());
        requests.execute(() -> {
            for(int attempt=0;attempt<100 && !isDestroyed();attempt++) {
                try {
                    request("GET","/api/health",null);
                    main.post(() -> {ready=true; ui.notice("Local library ready · no account needed",false); refresh();});
                    return;
                } catch(Exception ignored) {
                    if(backendError!=null) break;
                    try {Thread.sleep(300);} catch(InterruptedException e) {Thread.currentThread().interrupt();return;}
                }
            }
            main.post(() -> ui.notice(backendError == null ? "Could not start. Close and reopen Sonkip." : backendError,true));
        });
    }

    private static void startBackend(Context context) {
        if(!backendStarted.compareAndSet(false,true)) return;
        backendError=null;
        Thread server = new Thread(() -> {
            try {
                if(!Python.isStarted()) Python.start(new AndroidPlatform(context));
                Python python = Python.getInstance();
                PyObject env = python.getModule("os").get("environ");
                env.callAttr("__setitem__","SONKIP_QUICKJS",context.getApplicationInfo().nativeLibraryDir+"/libqjs.so");
                python.getModule("app.android_tokens");
                env.callAttr("__setitem__","SONKIP_ANDROID_TOKENS","1");
                PyObject module=python.getModule("app.android_server");
                File source=new File(module.get("__file__").toString());
                module.callAttr("create_android_server",new File(context.getFilesDir(),"music").getAbsolutePath(),
                    new File(source.getParentFile(),"static").getAbsolutePath(),"127.0.0.1",8765).callAttr("serve_forever");
            } catch(Exception error) { backendError="Local engine could not start: "+error.getMessage(); backendStarted.set(false); }
        },"sonkip-local-engine");
        server.setDaemon(true); server.start();
    }

    private JSONObject request(String method, String path, JSONObject body) throws Exception {
        HttpURLConnection connection=(HttpURLConnection)new URL(BASE+path).openConnection();
        try {
            connection.setRequestMethod(method); connection.setConnectTimeout(3000); connection.setReadTimeout(path.equals("/api/playlists") ? 600000 : 120000);
            if(body!=null) {
                connection.setDoOutput(true); connection.setRequestProperty("Content-Type","application/json");
                try(OutputStream output=connection.getOutputStream()) {output.write(body.toString().getBytes(StandardCharsets.UTF_8));}
            }
            int status=connection.getResponseCode();
            InputStream stream = status>=400 ? connection.getErrorStream() : connection.getInputStream();
            if(stream==null) throw new IOException("Local engine returned HTTP "+status);
            ByteArrayOutputStream bytes=new ByteArrayOutputStream();
            try(InputStream input=stream) {byte[] buffer=new byte[8192];int n;while((n=input.read(buffer))!=-1)bytes.write(buffer,0,n);}
            JSONObject response=new JSONObject(bytes.toString(StandardCharsets.UTF_8.name()));
            if(status>=400) throw new IOException(response.optString("detail","Request failed"));
            return response;
        } finally {connection.disconnect();}
    }

    private void action(String action, String value) {
        if(action.equals("tab")) {if(ready)refresh();return;}
        if(!ready) {ui.notice("The local engine is still starting. Please wait a moment.",false);return;}
        try {
            switch(action) {
                case "search": find(value); break;
                case "save": save(value); break;
                case "play": play(value); break;
                case "play-all": PlaybackService.playQueue(this,tracks,false,true);break;
                case "shuffle-all": PlaybackService.playQueue(this,tracks,true,true);break;
                case "playlists": showPlaylists(null);break;
                case "next": if(PlaybackService.current!=null)PlaybackService.current.next();break;
                case "previous": if(PlaybackService.current!=null)PlaybackService.current.previous();break;
                case "toggle": if(PlaybackService.current!=null) {PlaybackService.current.toggle();updatePlayer();} break;
                case "seek": if(PlaybackService.current!=null)PlaybackService.current.seek(Integer.parseInt(value)); break;
                case "export": export(value); break;
                case "more": new AlertDialog.Builder(this).setTitle(track(value).optString("title"))
                    .setItems(new String[]{"Add to playlist","Remove from library"},(d,which)->playlistAction(()->{
                        if(which==0)showPlaylists(value);else confirmDelete(value);
                    })).show();break;
            }
        } catch(Exception error) {ui.notice(error.getMessage(),true);}
    }
    private void find(String query) {
        DownloadService.begin(this);
        importing=true;
        ui.setBusy(true); ui.notice("Finding your music…",false);
        requests.execute(() -> {
            try {
                Uri uri=Uri.parse(query);
                boolean playlist=uri.isHierarchical() && (uri.getQueryParameterNames().contains("list")
                        || "open.spotify.com".equals(uri.getHost()) || "soundcloud.com".equals(uri.getHost()) || "www.soundcloud.com".equals(uri.getHost()));
                JSONObject result=playlist ? request("POST","/api/playlists",new JSONObject().put("url",query))
                    : request("GET","/api/search?q="+URLEncoder.encode(query,"UTF-8"),null);
                main.post(() -> {
                    if(isDestroyed())return;
                    importing=false; ui.setBusy(false);
                    if(playlist) {ui.remember(result.optJSONArray("jobs"));ui.showTab("downloads");ui.notice(result.optInt("count")+" queued · "+result.optJSONArray("unmatched").length()+" skipped"+(result.optString("notice").isEmpty()?"":" · YouTube matches; versions may differ"),false);}
                    else {JSONArray songs=result.optJSONArray("results");ui.setResults(songs);ui.notice(songs.length()==0?"No matches. Try another song or artist.":"Choose a song to save on your phone.",false);}
                    refresh();
                });
            } catch(Exception error) {main.post(() -> {if(isDestroyed())return;importing=false;ui.setBusy(false);ui.notice(error.getMessage(),true);refresh();});}
            finally {DownloadService.end();}
        });
    }
    private void save(String video) {
        DownloadService.begin(this);
        requests.execute(() -> {
            try {request("POST","/api/downloads",new JSONObject().put("video_id",video));main.post(() -> {ui.showTab("downloads");ui.notice("Song queued",false);refresh();});}
            catch(Exception error) {main.post(() -> ui.notice(error.getMessage(),true));}
            finally {DownloadService.end();}
        });
    }
    private void refresh() {
        if(!ready || isDestroyed() || !refreshing.compareAndSet(false,true))return;
        requests.execute(() -> {
            try {
                JSONArray saved=request("GET","/api/tracks",null).getJSONArray("tracks");
                JSONArray jobs=request("GET","/api/jobs",null).getJSONArray("jobs");
                main.post(() -> {
                    tracks=saved;ui.setTracks(saved);ui.setJobs(jobs);
                });
            } catch(Exception error) {main.post(() -> ui.notice("Could not refresh: "+error.getMessage(),true));}
            finally {refreshing.set(false);}
        });
    }
    private JSONObject track(String id) throws Exception {
        for(int i=0;i<tracks.length();i++)if(id.equals(tracks.getJSONObject(i).optString("id")))return tracks.getJSONObject(i);
        throw new IOException("This song is not available yet. Open Library and try again.");
    }
    private void play(String id) throws Exception {
        JSONObject song=track(id);
        PlaybackService.play(this,id,song.optString("title"));
        ui.notice("Opening "+song.optString("title")+"…",false);
    }
    private void updatePlayer() {
        PlaybackService service=PlaybackService.current;
        if(service!=null)ui.queueDescription(service.queueDescription());
        if(service!=null && service.isPrepared())ui.playback(service.title,service.isPlaying(),service.position(),service.duration());
        else ui.hidePlayer();
        if(PlaybackService.error!=null){ui.notice(PlaybackService.error,true);PlaybackService.error=null;}
    }
    private interface PlaylistAction {void run()throws Exception;}
    private void playlistAction(PlaylistAction action){try{action.run();}catch(Exception e){ui.notice(e.getMessage(),true);}}
    private void showPlaylists(String addSong)throws Exception {
        JSONArray lists=playlists.list();String[] names=new String[lists.length()+1];names[0]="+ Create playlist";
        for(int i=0;i<lists.length();i++)names[i+1]=lists.getJSONObject(i).getString("name")+" · "+playlists.resolve(lists.getJSONObject(i).getString("id"),tracks).length()+" songs";
        new AlertDialog.Builder(this).setTitle(addSong==null?"My playlists":"Add to playlist").setItems(names,(d,which)->playlistAction(()->{
            if(which==0){namePlaylist(null,addSong);return;}
            JSONObject list=lists.getJSONObject(which-1);String id=list.getString("id");
            if(addSong!=null){playlists.save(id,list.getString("name"),list.getJSONArray("tracks").put(addSong));ui.notice("Added to "+list.getString("name"),false);}
            else openPlaylist(id);
        })).setNegativeButton("Close",null).show();
    }
    private void namePlaylist(String id,String addSong)throws Exception {
        android.widget.EditText name=new android.widget.EditText(this);name.setSingleLine(true);name.setHint("Playlist name");
        name.setContentDescription("Playlist name");
        if(id!=null)name.setText(playlists.get(id).getString("name"));
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle(id==null?"Create playlist":"Rename playlist").setView(name)
            .setNegativeButton("Cancel",null).setPositiveButton("Save",null).create();
        dialog.setOnShowListener(d->dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v->{
            try {
                JSONArray ids=id==null?new JSONArray():playlists.get(id).getJSONArray("tracks");if(addSong!=null)ids.put(addSong);
                String saved=playlists.save(id,name.getText().toString(),ids);dialog.dismiss();
                if(id==null && addSong==null)editPlaylist(saved);else openPlaylist(saved);
            }catch(Exception e){name.setError(e.getMessage());}
        }));dialog.show();
    }
    private void openPlaylist(String id)throws Exception {
        JSONObject list=playlists.get(id);JSONArray songs=playlists.resolve(id,tracks);
        new AlertDialog.Builder(this).setTitle(list.getString("name")).setMessage(songs.length()+" saved songs\nPlaylist order follows the order you added songs.")
            .setPositiveButton("Play",(d,w)->playlistAction(()->PlaybackService.playQueue(this,songs,false,false)))
            .setNeutralButton("Shuffle",(d,w)->playlistAction(()->PlaybackService.playQueue(this,songs,true,false)))
            .setNegativeButton("Edit",(d,w)->new AlertDialog.Builder(this).setTitle(list.optString("name"))
                .setItems(new String[]{"Choose songs","Rename","Delete playlist"},(dialog,which)->playlistAction(()->{
                    if(which==0)editPlaylist(id);else if(which==1)namePlaylist(id,null);
                    else new AlertDialog.Builder(this).setTitle("Delete playlist?").setMessage("Your saved songs will stay in Library.")
                        .setNegativeButton("Keep",null).setPositiveButton("Delete",(confirm,n)->playlistAction(()->{playlists.delete(id);showPlaylists(null);})).show();
                })).show()).show();
    }
    private void editPlaylist(String id)throws Exception {
        JSONObject list=playlists.get(id);JSONArray old=list.getJSONArray("tracks");
        JSONArray library=new JSONArray(tracks.toString());String[] labels=new String[library.length()];boolean[] chosen=new boolean[library.length()];
        java.util.Set<String> selected=new java.util.LinkedHashSet<>();for(int i=0;i<old.length();i++)selected.add(old.getString(i));
        for(int i=0;i<library.length();i++){JSONObject song=library.getJSONObject(i);labels[i]=song.optString("title")+" — "+song.optString("artist");chosen[i]=selected.contains(song.getString("id"));}
        new AlertDialog.Builder(this).setTitle("Choose songs · "+list.getString("name"))
            .setMultiChoiceItems(labels,chosen,(d,which,checked)->{
                String songId=library.optJSONObject(which).optString("id");if(checked)selected.add(songId);else selected.remove(songId);
            }).setNegativeButton("Cancel",null).setPositiveButton("Save",(d,w)->playlistAction(()->{
                JSONArray ids=new JSONArray();for(String songId:selected)ids.put(songId);
                playlists.save(id,list.getString("name"),ids);openPlaylist(id);
            })).show();
    }
    private void export(String id) throws Exception {
        JSONObject song=track(id);exportId=id;
        Intent intent=new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("audio/"+(song.optString("extension").equals("webm")?"webm":"mp4"));
        intent.putExtra(Intent.EXTRA_TITLE,song.optString("title").replaceAll("[\\\\/:*?\"<>|]","_")+"."+song.optString("extension"));
        startActivityForResult(intent,41);
    }
    private void confirmDelete(String id) throws Exception {
        JSONObject song=track(id);
        new AlertDialog.Builder(this).setTitle(song.optString("title")).setMessage("Remove this song from Sonkip? Files you exported are kept.")
            .setNegativeButton("Keep",null).setPositiveButton("Remove",(dialog,which) -> requests.execute(() -> {
                try {request("DELETE","/api/tracks/"+id,null);main.post(() -> {
                    if(PlaybackService.current!=null && id.equals(PlaybackService.current.trackId)) {
                        stopService(new Intent(this,PlaybackService.class));ui.hidePlayer();
                    }
                    refresh();ui.notice("Song removed from Sonkip",false);
                });}catch(Exception error){main.post(() -> ui.notice(error.getMessage(),true));}
            })).show();
    }
    @Override protected void onActivityResult(int code,int result,Intent data) {
        super.onActivityResult(code,result,data);
        if(code!=41 || result!=RESULT_OK || data==null || data.getData()==null)return;
        String id=exportId;Uri destination=data.getData();ui.notice("Exporting audio…",false);
        requests.execute(() -> {
            HttpURLConnection connection=null;
            try {
                connection=(HttpURLConnection)new URL(BASE+"/api/tracks/"+id+"/audio").openConnection();
                connection.setConnectTimeout(3000);connection.setReadTimeout(30000);
                if(connection.getResponseCode()!=200)throw new IOException("The saved file is unavailable");
                try(InputStream input=connection.getInputStream();OutputStream output=getContentResolver().openOutputStream(destination)) {
                    if(output==null)throw new IOException("Cannot write to the selected location");
                    byte[] buffer=new byte[65536];int n;while((n=input.read(buffer))!=-1)output.write(buffer,0,n);
                }
                main.post(() -> ui.notice("Export complete",false));
            }catch(Exception error){main.post(() -> ui.notice("Export failed: "+error.getMessage(),true));}
            finally {if(connection!=null)connection.disconnect();}
        });
    }
    private final Runnable tick=new Runnable() {public void run(){if(!active)return;refresh();updatePlayer();main.postDelayed(this,2000);}};
    @Override protected void onResume(){super.onResume();active=true;main.post(tick);}
    @Override protected void onPause(){active=false;main.removeCallbacks(tick);super.onPause();}
    @Override protected void onDestroy(){
        active=false;main.removeCallbacksAndMessages(null);requests.shutdown();
        PublicTokenProvider.detach(this);
        super.onDestroy();
    }
}
