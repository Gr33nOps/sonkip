package io.github.gr33nops.sonkip;

import android.app.Instrumentation;
import android.content.Context;
import android.net.Uri;
import android.os.Bundle;
import android.provider.DocumentsContract;
import com.chaquo.python.Python;
import com.chaquo.python.PyObject;
import com.chaquo.python.android.AndroidPlatform;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;

/** Explicit adb-only regression checks, compiled into debug builds only. */
public final class DeviceRegressionChecks extends Instrumentation {
    private String mode, playlistUrl;
    @Override public void onCreate(Bundle arguments) {
        super.onCreate(arguments);mode=arguments.getString("mode","inspect");
        playlistUrl=arguments.getString("playlist_url","");start();
    }
    @Override public void onStart() {
        Bundle result=new Bundle();Context context=getTargetContext();
        try {
            if(!Python.isStarted())Python.start(new AndroidPlatform(context));
            Python python=Python.getInstance();PyObject scope=python.getBuiltins().callAttr("dict");
            scope.callAttr("__setitem__","home",new File(context.getFilesDir(),"music").getAbsolutePath());
            if(mode.equals("inspect")) {
                python.getBuiltins().callAttr("exec", "import json,time\nfrom app import engine\n"
                    +"t=time.monotonic()\nq='Tame Impala Past Life'\nc=engine._catalog_search(q)\n"
                    +"ranked=engine._rank_search_results(q,[{**x,'uploader':x['artist']+' - Topic'} for x in c])\n"
                    +"result=json.dumps({'catalog_count':len(c),'ranked_count':len(ranked),'first':c[:1],"
                    +"'words':sorted(engine._words(q)),'seconds':time.monotonic()-t})\n",scope);
                result.putString("details",scope.callAttr("__getitem__","result").toString());
            } else if(mode.equals("apply-metadata")) {
                scope.callAttr("__setitem__","metadata_file",new File(context.getCacheDir(),"verified-metadata.json").getAbsolutePath());
                python.getBuiltins().callAttr("exec","import json,threading\nfrom pathlib import Path\n"
                    +"from app.android_server import create_android_server\nserver=create_android_server(home,Path(home),port=8765)\n"
                    +"threading.Thread(target=server.serve_forever,daemon=True).start()\n"
                    +"overrides=json.loads(Path(metadata_file).read_text(encoding='utf-8'))\n"
                    +"for source in overrides:\n track=next(x for x in server.store.list_tracks() if x['video_id']==source['video_id'])\n"
                    +" server.manager._repair_track(track,source)\n",scope);
                MusicFolder.sync(context);assertFolderOk(context);
                python.getBuiltins().callAttr("exec","server.shutdown()\nserver.server_close()\nserver.manager.pool.shutdown(wait=True)\nPath(metadata_file).unlink()\n",scope);
                result.putString("details","Verified release metadata applied and folder synced");
            } else if(mode.equals("audit")) {
                python.getBuiltins().callAttr("exec","import json\nfrom pathlib import Path\nfrom app.storage import MusicStore\n"
                    +"store=MusicStore(Path(home))\ntracks=store.list_tracks()\n"
                    +"result=json.dumps([{**x,'path':str(store.path_for(x))} for x in tracks])\n",scope);
                org.json.JSONArray songs=new org.json.JSONArray(scope.callAttr("__getitem__","result").toString());
                org.json.JSONArray missingCovers=new org.json.JSONArray(),unknownAlbums=new org.json.JSONArray();int albums=0;
                for(int i=0;i<songs.length();i++) {
                    org.json.JSONObject song=songs.getJSONObject(i);android.media.MediaMetadataRetriever metadata=new android.media.MediaMetadataRetriever();
                    try {
                        metadata.setDataSource(song.getString("path"));byte[] cover=metadata.getEmbeddedPicture();
                        if(cover==null || cover.length==0)missingCovers.put(song.optString("title"));
                        String album=metadata.extractMetadata(android.media.MediaMetadataRetriever.METADATA_KEY_ALBUM);
                        if(album!=null && !album.isEmpty())albums++;else unknownAlbums.put(song.optString("title"));
                        String stored=song.optString("album","");
                        if(!stored.isEmpty() && !stored.equals("null") && !stored.equals(album))throw new AssertionError("Saved/file album mismatch: "+song.optString("title"));
                    } finally {metadata.release();}
                }
                result.putInt("songs",songs.length());result.putInt("songs_with_albums",albums);
                result.putString("unknown_albums",unknownAlbums.toString());result.putString("missing_covers",missingCovers.toString());
                if(missingCovers.length()>0)throw new AssertionError("Some saved songs still have no embedded cover");
            } else if(mode.equals("playlist")) {
                if(playlistUrl.isEmpty())throw new IllegalArgumentException("Pass -e playlist_url PUBLIC_PLAYLIST_URL");
                scope.callAttr("__setitem__","playlist_url",playlistUrl);
                scope.callAttr("__setitem__","output",new File(context.getCacheDir(),"spotify-device-preview.json").getAbsolutePath());
                python.getBuiltins().callAttr("exec", "import json,time\nfrom pathlib import Path\nfrom app import engine\n"
                    +"t=time.monotonic()\np=engine.extract_playlist(playlist_url)\n"
                    +"Path(output).write_text(json.dumps(p),encoding='utf-8')\n"
                    +"assert p['source_count']==250, p['source_count']\nassert len(p['entries'])>=240, len(p['entries'])\n"
                    +"result=json.dumps({'source_count':p['source_count'],'unique_matches':len(p['entries']),"
                    +"'unmatched':p['unmatched'],'duplicates':p.get('duplicate_count'),'seconds':time.monotonic()-t})\n",scope);
                result.putString("details",scope.callAttr("__getitem__","result").toString());
            } else if(mode.equals("downloads")) {
                runOnMainSync(()->{try{PublicTokenProvider.initialize(context);}catch(Exception e){throw new RuntimeException(e);}});
                scope.callAttr("__setitem__","runtime",context.getApplicationInfo().nativeLibraryDir+"/libqjs.so");
                scope.callAttr("__setitem__","preview",new File(context.getCacheDir(),"spotify-device-preview.json").getAbsolutePath());
                python.getBuiltins().callAttr("exec", "import os,json,threading\nfrom pathlib import Path\n"
                    +"os.environ['SONKIP_ANDROID_TOKENS']='1'\nos.environ['SONKIP_QUICKJS']=runtime\nimport app.android_tokens\n"
                    +"from app.android_server import create_android_server\nfrom app.engine import _same_recording\n"
                    +"server=create_android_server(home,Path(home),port=8765)\nthreading.Thread(target=server.serve_forever,daemon=True).start()\n"
                    +"baseline=server.store.list_tracks()\nbaseline_ids={x['id'] for x in baseline}\n"
                    +"sources=[x for x in json.loads(Path(preview).read_text())['entries'] if not any("
                    +"x['video_id']==t['video_id'] or _same_recording(t,x) for t in baseline)][:2]\n"
                    +"assert len(sources)==2\njobs=[server.manager.start(x['video_id'],fmt,True,x) for x,fmt in zip(sources,['m4a','original'])]\n"
                    +"assert not baseline_ids.intersection(jobs), 'Do not modify existing music during download checks'\n",scope);
                PyObject manager=scope.callAttr("__getitem__","server").get("manager");long deadline=android.os.SystemClock.elapsedRealtime()+600000;
                String previous="";
                while(true) {
                    python.getBuiltins().callAttr("exec","states=[server.manager.get_job(x) for x in jobs]\nstatus=json.dumps(states)\n",scope);
                    String json=scope.callAttr("__getitem__","status").toString();org.json.JSONArray states=new org.json.JSONArray(json);boolean done=true;
                    String summary="";for(int i=0;i<states.length();i++){org.json.JSONObject job=states.getJSONObject(i);summary+=job.optString("status")+":"+job.optInt("percent")+" ";if(!job.optString("status").matches("complete|error"))done=false;}
                    if(!summary.equals(previous)){previous=summary;Bundle progress=new Bundle();progress.putString("downloads",json);sendStatus(0,progress);}
                    if(done)break;if(android.os.SystemClock.elapsedRealtime()>deadline)throw new AssertionError("Download check timed out");Thread.sleep(1000);
                }
                python.getBuiltins().callAttr("exec","assert all(x['status']=='complete' for x in states), states\n"
                    +"paths=[str(server.store.path_for(server.store.get_track(x))) for x in jobs]\n",scope);
                MusicFolder.sync(context);assertFolderOk(context);
                PyObject paths=scope.callAttr("__getitem__","paths");
                for(PyObject path:paths.asList()) {
                    android.media.MediaMetadataRetriever metadata=new android.media.MediaMetadataRetriever();
                    try {metadata.setDataSource(path.toString());byte[] cover=metadata.getEmbeddedPicture();
                        if(cover==null || cover.length==0)throw new AssertionError("New download has no readable embedded cover");
                    } finally {metadata.release();}
                }
                python.getBuiltins().callAttr("exec","result=json.dumps([server.store.get_track(x) for x in jobs])\n"
                    +"server.manager.delete_tracks(jobs)\n",scope);MusicFolder.sync(context);assertFolderOk(context);
                result.putString("details",scope.callAttr("__getitem__","result").toString());
                python.getBuiltins().callAttr("exec","server.shutdown()\nserver.server_close()\nserver.manager.pool.shutdown(wait=True)\n",scope);
            } else if(mode.equals("repair")) {
                python.getBuiltins().callAttr("exec", "import os,threading\nfrom pathlib import Path\n"
                    +"os.environ['SONKIP_ANDROID_TOKENS']='1'\nfrom app.android_server import create_android_server\n"
                    +"server=create_android_server(home,Path(home),port=8765)\n"
                    +"threading.Thread(target=server.serve_forever,daemon=True).start()\nserver.manager.repair_library()\n",scope);
                PyObject manager=scope.callAttr("__getitem__","server").get("manager");int last=-1;
                while(true) {
                    String json=python.getModule("json").callAttr("dumps",manager.callAttr("repair_status")).toString();
                    org.json.JSONObject state=new org.json.JSONObject(json);
                    if(state.optInt("completed")!=last){last=state.optInt("completed");Bundle progress=new Bundle();progress.putString("repair",json);sendStatus(0,progress);}
                    if(!state.optBoolean("running")){result.putString("details",json);break;}
                    Thread.sleep(1000);
                }
                MusicFolder.sync(context);assertFolderOk(context);
                python.getBuiltins().callAttr("exec","server.shutdown()\nserver.server_close()\nserver.manager.pool.shutdown(wait=True)\n",scope);
            } else if(mode.equals("sync")) {
                if(MusicFolder.prefs(context).getString("tree","").isEmpty())throw new AssertionError("Choose a Music folder first");
                File fixture=new File(context.getCacheDir(),"sonkip-regression-fixture.m4a");
                try(InputStream input=getContext().getAssets().open("sync-fixture.m4a");FileOutputStream output=new FileOutputStream(fixture)) {
                    byte[] bytes=new byte[8192];int n;while((n=input.read(bytes))!=-1)output.write(bytes,0,n);
                }
                scope.callAttr("__setitem__","fixture",fixture.getAbsolutePath());
                python.getBuiltins().callAttr("exec", "import json,threading,shutil,uuid\nfrom pathlib import Path\n"
                    +"from app.android_server import create_android_server\nserver=create_android_server(home,Path(home),port=8765)\n"
                    +"threading.Thread(target=server.serve_forever,daemon=True).start()\n"
                    +"def add_fixture():\n track_id=uuid.uuid4().hex\n path=server.store.tracks_dir/(track_id+'.m4a')\n"
                    +" shutil.copyfile(fixture,path)\n server.store.add_track({'id':track_id,'video_id':'NMRhx71bGo4',"
                    +"'title':'Sonkip sync regression fixture','artist':'Sonkip','album':'Device checks',"
                    +"'filename':path.name,'extension':'m4a','bytes':path.stat().st_size,'duration':1})\n return track_id\n"
                    +"first_id=add_fixture()\n",scope);
                MusicFolder.sync(context);assertFolderOk(context);
                String firstId=scope.callAttr("__getitem__","first_id").toString();
                String tree=MusicFolder.prefs(context).getString("tree","");
                Uri first=Uri.parse(MusicFolder.prefs(context).getString(tree+"|"+firstId,""));
                if(!DocumentsContract.deleteDocument(context.getContentResolver(),first))throw new AssertionError("Cannot remove fixture folder copy");
                MusicFolder.sync(context);assertFolderOk(context);
                python.getBuiltins().callAttr("exec", "assert server.store.get_track(first_id) is None, 'Folder deletion left a saved song'\n"
                    +"second_id=add_fixture()\n",scope);
                MusicFolder.sync(context);assertFolderOk(context);
                String secondId=scope.callAttr("__getitem__","second_id").toString();
                Uri second=Uri.parse(MusicFolder.prefs(context).getString(tree+"|"+secondId,""));
                python.getBuiltins().callAttr("exec","assert server.manager.delete_tracks([second_id])==[second_id]\n",scope);
                MusicFolder.sync(context);assertFolderOk(context);
                try(android.database.Cursor cursor=context.getContentResolver().query(second,new String[]{DocumentsContract.Document.COLUMN_DOCUMENT_ID},null,null,null)) {
                    if(cursor!=null && cursor.moveToFirst())throw new AssertionError("Saved deletion left the folder copy");
                } catch(IllegalArgumentException expectedMissingFile) { /* ExternalStorageProvider rejects deleted document URIs. */ }
                python.getBuiltins().callAttr("exec","songs=server.store.list_tracks()\n"
                    +"song=next(x for x in songs if x['extension']=='opus')\n"
                    +"audio_path=str(server.store.path_for(song))\n",scope);
                android.media.MediaMetadataRetriever metadata=new android.media.MediaMetadataRetriever();
                try {
                    metadata.setDataSource(scope.callAttr("__getitem__","audio_path").toString());
                    byte[] cover=metadata.getEmbeddedPicture();
                    if(cover==null || cover.length==0)throw new AssertionError("Android cannot read repaired Opus cover");
                    result.putInt("android_cover_bytes",cover.length);
                    result.putString("android_album",metadata.extractMetadata(android.media.MediaMetadataRetriever.METADATA_KEY_ALBUM));
                } finally {metadata.release();}
                android.media.MediaPlayer player=new android.media.MediaPlayer();
                try {
                    player.setDataSource(scope.callAttr("__getitem__","audio_path").toString());player.prepare();player.start();Thread.sleep(750);
                    if(!player.isPlaying() || player.getCurrentPosition()<=0)throw new AssertionError("Repaired song did not play");
                    result.putInt("playback_position_ms",player.getCurrentPosition());player.stop();
                } finally {player.release();}
                python.getBuiltins().callAttr("exec","server.shutdown()\nserver.server_close()\nserver.manager.pool.shutdown(wait=True)\n",scope);
                fixture.delete();result.putString("folder_to_saved","passed");result.putString("saved_to_folder","passed");
            } else throw new IllegalArgumentException("Unknown check mode");
            result.putString("status","passed");finish(-1,result);
        } catch(Throwable error) {result.putString("status","failed");result.putString("error",android.util.Log.getStackTraceString(error));finish(0,result);}
    }
    private static void assertFolderOk(Context context) {
        String error=MusicFolder.prefs(context).getString("error","");
        if(!error.isEmpty())throw new AssertionError(error);
    }
}
