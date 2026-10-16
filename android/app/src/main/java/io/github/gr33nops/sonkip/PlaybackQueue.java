package io.github.gr33nops.sonkip;

import org.json.*;
import java.util.*;

final class PlaybackQueue {
    private final List<JSONObject> songs=new ArrayList<>();
    private int index;
    final boolean shuffled;
    PlaybackQueue(JSONArray tracks,boolean shuffle,Random random){this(tracks,shuffle,true,random);}
    PlaybackQueue(JSONArray tracks,boolean shuffle,boolean chronological,Random random) {
        shuffled=shuffle;Set<String> seen=new HashSet<>();
        for(int i=0;i<tracks.length();i++) {
            JSONObject song=tracks.optJSONObject(i);
            if(song!=null && !song.optString("id").isEmpty() && seen.add(song.optString("id")))songs.add(song);
        }
        // The library API returns newest first; stable reversal also handles tied timestamps.
        if(chronological){Collections.reverse(songs);songs.sort(Comparator.comparing(s->s.optString("created_at")));}
        if(shuffle)Collections.shuffle(songs,random);
    }
    JSONObject current(){return songs.isEmpty()?null:songs.get(index);}
    JSONObject next(){if(index+1>=songs.size())return null;return songs.get(++index);}
    JSONObject previous(){if(songs.isEmpty())return null;index=Math.max(0,index-1);return songs.get(index);}
    String description(){return songs.isEmpty()?"":(index+1)+" / "+songs.size()+" · "+(shuffled?"Shuffle":"In order");}
}
