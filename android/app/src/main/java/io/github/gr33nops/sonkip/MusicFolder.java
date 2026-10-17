package io.github.gr33nops.sonkip;

import android.content.*;
import android.database.Cursor;
import android.net.Uri;
import android.provider.DocumentsContract;
import org.json.*;
import java.io.*;
import java.net.*;

/** User-granted shared folder; internal audio is retained if a provider fails. */
final class MusicFolder {
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
            copyTracks(context,Uri.parse(folder),tracks);
            prefs(context).edit().remove("error").apply();
        }catch(Exception error){prefs(context).edit().putString("error","Folder copy failed. Your songs are safe in Sonkip. Reconnect or choose the folder again. "+error.getMessage()).apply();}
        finally {if(connection!=null)connection.disconnect();}
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
            if(!previous.isEmpty()) {
                try(Cursor cursor=resolver.query(Uri.parse(previous),new String[]{DocumentsContract.Document.COLUMN_DOCUMENT_ID},null,null,null)) {
                    if(cursor!=null && cursor.moveToFirst())continue;
                }
            }
            File source=new File(root,track.getString("filename")).getCanonicalFile();
            if(!root.equals(source.getParentFile()) || !source.isFile())throw new IOException("Saved audio unavailable");
            // createDocument creates a new document; never open an unrelated existing name for writing.
            Uri outputUri=DocumentsContract.createDocument(resolver,parent,mime(track.optString("extension")),source.getName());
            if(outputUri==null)throw new IOException("Cannot create audio in this folder");
            try {
                try(InputStream input=new FileInputStream(source);OutputStream output=resolver.openOutputStream(outputUri,"w")) {
                    if(output==null)throw new IOException("Cannot write audio in this folder");
                    byte[] b=new byte[65536];int n;while((n=input.read(b))!=-1){if(Thread.currentThread().isInterrupted())throw new InterruptedIOException("Copy interrupted");output.write(b,0,n);}
                }
                if(!prefs(context).edit().putString(key,outputUri.toString()).commit())throw new IOException("Cannot remember copied song");
            }catch(Exception error){try{DocumentsContract.deleteDocument(resolver,outputUri);}catch(Exception ignored){}throw error;}
        }
    }
}
