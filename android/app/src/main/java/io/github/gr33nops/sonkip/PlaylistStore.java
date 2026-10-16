package io.github.gr33nops.sonkip;

import android.content.Context;
import android.content.SharedPreferences;
import org.json.*;
import java.util.*;

/** Stores only playlist names and local track IDs; never copies or deletes audio. */
final class PlaylistStore {
    private final SharedPreferences preferences;
    PlaylistStore(Context context){preferences=context.getSharedPreferences("local-playlists",Context.MODE_PRIVATE);}
    JSONArray list()throws JSONException{return new JSONArray(preferences.getString("lists","[]"));}
    String save(String id,String name,JSONArray ids)throws Exception {
        name=name.trim();if(name.isEmpty())throw new IllegalArgumentException("Give your playlist a name.");
        if(name.length()>80)throw new IllegalArgumentException("Use a name under 80 characters.");
        JSONArray all=list(),unique=new JSONArray();Set<String> seen=new HashSet<>();
        for(int i=0;i<ids.length();i++){String value=ids.optString(i);if(!value.isEmpty()&&seen.add(value))unique.put(value);}
        if(id==null)id=UUID.randomUUID().toString();
        JSONObject entry=new JSONObject().put("id",id).put("name",name).put("tracks",unique);
        boolean replaced=false;
        for(int i=0;i<all.length();i++)if(id.equals(all.getJSONObject(i).getString("id"))){all.put(i,entry);replaced=true;break;}
        if(!replaced)all.put(entry);
        write(all);return id;
    }
    void delete(String id)throws Exception {
        JSONArray all=list(),kept=new JSONArray();
        for(int i=0;i<all.length();i++)if(!id.equals(all.getJSONObject(i).getString("id")))kept.put(all.getJSONObject(i));
        write(kept);
    }
    JSONObject get(String id)throws Exception {
        JSONArray all=list();for(int i=0;i<all.length();i++)if(id.equals(all.getJSONObject(i).getString("id")))return all.getJSONObject(i);
        throw new IllegalArgumentException("That playlist no longer exists.");
    }
    JSONArray resolve(String id,JSONArray library)throws Exception {
        Map<String,JSONObject> available=new HashMap<>();
        for(int i=0;i<library.length();i++){JSONObject song=library.getJSONObject(i);available.put(song.getString("id"),song);}
        JSONArray ids=get(id).getJSONArray("tracks"),songs=new JSONArray();
        for(int i=0;i<ids.length();i++){JSONObject song=available.get(ids.getString(i));if(song!=null)songs.put(song);}
        return songs;
    }
    private void write(JSONArray all)throws Exception {
        if(!preferences.edit().putString("lists",all.toString()).commit())throw new java.io.IOException("Could not save the playlist. Check free storage.");
    }
}
