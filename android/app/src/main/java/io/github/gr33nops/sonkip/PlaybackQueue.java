package io.github.gr33nops.sonkip;

import org.json.*;
import java.util.*;

final class PlaybackQueue {
    private final List<JSONObject> songs=new ArrayList<>();
    private int index;
    private String repeat="off";
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
    JSONObject next(){if(index+1>=songs.size()){if(!repeat.equals("all") || songs.isEmpty())return null;index=0;return current();}return songs.get(++index);}
    JSONObject completed(){return repeat.equals("one")?current():next();}
    void setRepeat(String mode){if(!Arrays.asList("off","one","all").contains(mode))throw new IllegalArgumentException("Unknown repeat mode");repeat=mode;}
    JSONArray upcoming(){JSONArray result=new JSONArray();for(int i=index+1;i<songs.size();i++)result.put(songs.get(i));return result;}
    void moveNext(int position){int target=index+1+position;if(position<0 || target>=songs.size())return;songs.add(index+1,songs.remove(target));}
    void removeUpcoming(int position){int target=index+1+position;if(position>=0 && target<songs.size())songs.remove(target);}
    JSONObject previous(){if(songs.isEmpty())return null;index=Math.max(0,index-1);return songs.get(index);}
    String description(){return songs.isEmpty()?"":(index+1)+" / "+songs.size()+" · "+(shuffled?"Shuffle":"In order");}
}
