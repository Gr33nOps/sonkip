package io.github.gr33nops.sonkip;

import android.content.*;
import android.database.Cursor;
import android.net.Uri;
import android.provider.DocumentsContract;
import org.json.*;
import java.io.*;
import java.net.*;

/** A linked music folder; unavailable providers never imply that songs were deleted. */
final class MusicFolder {
    private static long lastSync;
    static synchronized void syncIfDue(Context context) {
        if(android.os.SystemClock.elapsedRealtime()-lastSync>=5000)sync(context);
    }
    static android.content.SharedPreferences prefs(Context context) {
        return context.getSharedPreferences("music-folder",Context.MODE_PRIVATE);
    }
    static String mime(String extension) {
        switch(extension.toLowerCase(java.util.Locale.ROOT)) {
            case "webm": return "audio/webm";
            case "mp4": case "m4a": return "audio/mp4";
            case "opus": case "ogg": return "audio/ogg";
            case "mp3": return "audio/mpeg";
            case "flac": return "audio/flac";
            default: return "application/octet-stream";
        }
    }
    private static void scan(Context context,Uri document) {
        try {
            String id=DocumentsContract.getDocumentId(document);
            if(!id.startsWith("primary:"))return;
            File root=android.os.Environment.getExternalStorageDirectory().getCanonicalFile();
            File audio=new File(root,id.substring("primary:".length())).getCanonicalFile();
            if(!audio.getPath().startsWith(root.getPath()+File.separator))return;
            android.media.MediaScannerConnection.scanFile(context,new String[]{audio.getPath()},null,null);
        } catch(Exception ignored) { /* The document provider still receives notifyChange. */ }
    }
    static synchronized void sync(Context context) {
        String folder=prefs(context).getString("tree","");
        if(folder.isEmpty())return;
        HttpURLConnection connection=null;
        try {
            connection=(HttpURLConnection)new URL("http://127.0.0.1:8765/api/tracks").openConnection();
            connection.setConnectTimeout(3000);connection.setReadTimeout(10000);
            ByteArrayOutputStream bytes=new ByteArrayOutputStream();
            try(InputStream input=connection.getInputStream()){byte[] b=new byte[8192];int n;while((n=input.read(b))!=-1)bytes.write(b,0,n);}
            JSONArray tracks=new JSONObject(bytes.toString("UTF-8")).getJSONArray("tracks");
            Uri tree=Uri.parse(folder);
            JSONArray removed=reconcileTracks(context,tree,tracks);
            java.util.Set<String> deleted=new java.util.HashSet<>();
            for(int i=0;i<removed.length();i++) {
                String id=removed.getString(i);
                HttpURLConnection deletion=(HttpURLConnection)new URL("http://127.0.0.1:8765/api/tracks/"+id).openConnection();
                try {
                    deletion.setRequestMethod("DELETE");deletion.setConnectTimeout(3000);deletion.setReadTimeout(10000);
                    int status=deletion.getResponseCode();
                    if(status!=200 && status!=404)throw new IOException("Cannot remove deleted folder song from Saved");
                    String key=folder+"|"+id;
                    prefs(context).edit().remove(key).remove("stamp|"+key).commit();deleted.add(id);
                } finally {deletion.disconnect();}
            }
            JSONArray live=new JSONArray();
            for(int i=0;i<tracks.length();i++)if(!deleted.contains(tracks.getJSONObject(i).getString("id")))live.put(tracks.getJSONObject(i));
            copyTracks(context,tree,live);
            prefs(context).edit().remove("error").apply();
        }catch(Exception error){prefs(context).edit().putString("error","Folder sync failed. Your songs are safe in Sonkip. Reconnect or choose the folder again. "+error.getMessage()).apply();}
        finally {lastSync=android.os.SystemClock.elapsedRealtime();if(connection!=null)connection.disconnect();}
    }
    static JSONArray reconcileTracks(Context context,Uri tree,JSONArray tracks)throws Exception {
        ContentResolver resolver=context.getContentResolver();
        Uri parent=DocumentsContract.buildDocumentUriUsingTree(tree,DocumentsContract.getTreeDocumentId(tree));
        try(Cursor root=resolver.query(parent,new String[]{DocumentsContract.Document.COLUMN_DOCUMENT_ID},null,null,null)) {
            if(root==null || !root.moveToFirst())throw new IOException("Selected folder is unavailable. Reconnect it and retry.");
        }
        java.util.Set<String> documents=new java.util.HashSet<>();
        Uri children=DocumentsContract.buildChildDocumentsUriUsingTree(tree,DocumentsContract.getTreeDocumentId(tree));
        try(Cursor cursor=resolver.query(children,new String[]{DocumentsContract.Document.COLUMN_DOCUMENT_ID},null,null,null)) {
            if(cursor==null)throw new IOException("Cannot list selected Music folder");
            while(cursor.moveToNext())documents.add(cursor.getString(0));
        }
        java.util.Set<String> saved=new java.util.HashSet<>();
        for(int i=0;i<tracks.length();i++)saved.add(tracks.getJSONObject(i).getString("id"));
        JSONArray removed=new JSONArray();String prefix=tree.toString()+"|";
        for(java.util.Map.Entry<String,?> entry:prefs(context).getAll().entrySet()) {
            if(!entry.getKey().startsWith(prefix) || !(entry.getValue() instanceof String))continue;
            String id=entry.getKey().substring(prefix.length());Uri document=Uri.parse((String)entry.getValue());
            boolean exists=documents.contains(DocumentsContract.getDocumentId(document));
            if(!saved.contains(id)) {
                if(exists && !DocumentsContract.deleteDocument(resolver,document))throw new IOException("Cannot delete linked song from folder");
                scan(context,document);
                prefs(context).edit().remove(entry.getKey()).remove("stamp|"+entry.getKey()).commit();
            } else if(!exists)removed.put(id);
        }
        return removed;
    }
    static void copyTracks(Context context,Uri tree,JSONArray tracks)throws Exception {
        ContentResolver resolver=context.getContentResolver();
        Uri parent=DocumentsContract.buildDocumentUriUsingTree(tree,DocumentsContract.getTreeDocumentId(tree));
        File root=new File(context.getFilesDir(),"music/tracks").getCanonicalFile();
        for(int i=0;i<tracks.length();i++) {
            if(Thread.currentThread().isInterrupted())throw new InterruptedIOException("Copy interrupted");
            JSONObject track=tracks.getJSONObject(i);
            String key=tree.toString()+"|"+track.getString("id");
            String previous=prefs(context).getString(key,"");
            File source=new File(root,track.getString("filename")).getCanonicalFile();
            if(!root.equals(source.getParentFile()) || !source.isFile())throw new IOException("Saved audio unavailable");
            String stamp=source.length()+":"+source.lastModified();
            boolean replaceContainer=false;
            if(!previous.isEmpty()) {
                try(Cursor cursor=resolver.query(Uri.parse(previous),new String[]{DocumentsContract.Document.COLUMN_DOCUMENT_ID},null,null,null)) {
                    if(cursor==null)throw new IOException("Cannot read linked song");
                    if(!cursor.moveToFirst())continue; // Reconcile deletion before making new copies.
                    String oldStamp=prefs(context).getString("stamp|"+key,"");
                    if(stamp.equals(oldStamp))continue;
                }
                String oldMime=resolver.getType(Uri.parse(previous));
                replaceContainer=oldMime!=null && !oldMime.equals(mime(track.optString("extension")));
            }
            // createDocument creates a new document; never open an unrelated existing name for writing.
            Uri outputUri=previous.isEmpty() || replaceContainer?DocumentsContract.createDocument(resolver,parent,mime(track.optString("extension")),source.getName()):Uri.parse(previous);
            if(outputUri==null)throw new IOException("Cannot create audio in this folder");
            try {
                try(InputStream input=new FileInputStream(source);OutputStream output=resolver.openOutputStream(outputUri,"w")) {
                    if(output==null)throw new IOException("Cannot write audio in this folder");
                    byte[] b=new byte[65536];int n;while((n=input.read(b))!=-1){if(Thread.currentThread().isInterrupted())throw new InterruptedIOException("Copy interrupted");output.write(b,0,n);}
                }
                resolver.notifyChange(outputUri,null);
                scan(context,outputUri);
                if(!prefs(context).edit().putString(key,outputUri.toString()).putString("stamp|"+key,stamp).commit())throw new IOException("Cannot remember copied song");
                if(replaceContainer){DocumentsContract.deleteDocument(resolver,Uri.parse(previous));scan(context,Uri.parse(previous));}
            }catch(Exception error){if(previous.isEmpty())try{DocumentsContract.deleteDocument(resolver,outputUri);}catch(Exception ignored){}throw error;}
        }
    }
}
