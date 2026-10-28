package io.github.gr33nops.sonkip;

import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.BitmapFactory;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.widget.*;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.HashMap;
import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Native Android widgets only. The internal token browser is never the app UI. */
@android.annotation.SuppressLint({"ViewConstructor", "SetTextI18n"})
public class NativeUi extends LinearLayout {
    public interface Actions { void run(String action, String value); }
    private static final int INK = Color.rgb(17,17,17), PAPER = Color.rgb(243,240,232),
            MUTED = Color.rgb(110,107,100), ORANGE = Color.rgb(238,71,0),
            ORANGE_TEXT = Color.rgb(176,50,0), LIME = Color.rgb(232,255,0);
    private static final ExecutorService ARTWORK = Executors.newFixedThreadPool(3);
    private static final android.util.LruCache<String,android.graphics.Bitmap> ART_CACHE = new android.util.LruCache<>(32);
    private final Actions actions;
    private final Typeface bodyFace, boldFace, monoFace;
    private final LinearLayout content, navigation, player, playerDetails;
    private final ScrollView scroll;
    private final TextView message, playingTitle, playingTime, playerHint;
    private final Button toggle;
    private final SeekBar seek;
    private JSONArray tracks = new JSONArray(), jobs = new JSONArray(), results = new JSONArray();
    private JSONObject playlistPreview;
    private final Map<String,String> titles = new HashMap<>();
    private String tab = "find", query = "";
    private String libraryQuery="", librarySort="newest";
    private final Set<String> selectedTracks = new LinkedHashSet<>();
    private final Set<String> selectedPlaylistTracks = new LinkedHashSet<>();
    private boolean selectingTracks;
    private String queueDescription="Saved on this phone";
    private String audioFormatLabel="M4A / AAC";
    private boolean metadataEnabled=true;
    private boolean busy, seeking, playerExpanded;
    private int noticeVersion;

    public JSONObject sourceFor(String videoId) {
        for (JSONArray group : new JSONArray[]{results, playlistPreview == null ? null : playlistPreview.optJSONArray("entries")}) {
            if (group == null) continue;
            for (int i = 0; i < group.length(); i++) {
                JSONObject item = group.optJSONObject(i);
                if (item != null && videoId.equals(item.optString("video_id"))) return item;
            }
        }
        return null;
    }

    public NativeUi(Context context, Actions actions) {
        super(context);
        this.actions = actions;
        bodyFace = Typeface.createFromAsset(context.getAssets(), "fonts/manrope-500.ttf");
        boldFace = Typeface.createFromAsset(context.getAssets(), "fonts/manrope-700.ttf");
        monoFace = Typeface.createFromAsset(context.getAssets(), "fonts/dm-mono-400.ttf");
        setOrientation(VERTICAL);
        setBackgroundColor(PAPER);
        LinearLayout brand = row();
        brand.setPadding(dp(20), dp(10), dp(20), dp(6));
        TextView logo = text("sonkip.", 24, INK, true);
        brand.addView(logo, new LayoutParams(0, -2, 1));
        TextView local = text("LOCAL ONLY", 10, MUTED, true);
        local.setTypeface(monoFace);
        brand.addView(local);
        addView(brand);
        message = text("Starting your local library…", 12, MUTED, false);
        message.setPadding(dp(20), dp(5), dp(20), dp(7));
        message.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        message.setBackgroundColor(0xffe9e5db);
        addView(message);
        scroll = new ScrollView(context);
        scroll.setFillViewport(true);
        content = column();
        content.setPadding(dp(20), dp(8), dp(20), dp(24));
        scroll.addView(content);
        addView(scroll, new LayoutParams(-1, 0, 1));

        player = column();
        player.setPadding(dp(16), dp(7), dp(16), dp(5));
        player.setBackgroundColor(INK);
        playerDetails=column();
        LinearLayout playerRow = row();
        LinearLayout playerSummary = column();
        playingTitle = text("", 14, Color.WHITE, true);
        playingTitle.setSingleLine(true); playingTitle.setEllipsize(android.text.TextUtils.TruncateAt.END);
        playerSummary.addView(playingTitle);
        playerHint = text("Playback controls  ↑", 10, 0xffb7b4aa, false);
        playerHint.setTypeface(monoFace); playerSummary.addView(playerHint);
        playerSummary.setContentDescription("Show playback controls");
        playerSummary.setTag("player-expand");playerSummary.setFocusable(true);
        playerSummary.setOnClickListener(v -> {
            playerExpanded=!playerExpanded;
            playerDetails.setVisibility(playerExpanded?VISIBLE:GONE);
            playerSummary.setContentDescription(playerExpanded?"Hide playback controls":"Show playback controls");
            playerHint.setText(playerHint.getText().toString().replace(playerExpanded?'↑':'↓',playerExpanded?'↓':'↑'));
        });
        playerRow.addView(playerSummary, new LayoutParams(0, dp(56), 1));
        toggle = button("Play", "player-toggle", v -> actions.run("toggle", ""));
        toggle.setBackgroundTintList(ColorStateList.valueOf(LIME));
        toggle.setTextColor(INK);
        playerRow.addView(toggle, new LayoutParams(dp(74), dp(48)));
        player.addView(playerRow);
        LinearLayout transport=row();
        Button previous=button("← Previous","player-previous",v->actions.run("previous",""));
        Button next=button("Next →","player-next",v->actions.run("next",""));
        previous.setContentDescription("Previous song");next.setContentDescription("Next song");
        transport.addView(previous,new LayoutParams(0,dp(48),1));
        transport.addView(next,new LayoutParams(0,dp(48),1));playerDetails.addView(transport);
        seek = new SeekBar(context);
        seek.setContentDescription("Playback position");
        seek.setProgressTintList(ColorStateList.valueOf(LIME));
        seek.setThumbTintList(ColorStateList.valueOf(LIME));
        seek.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            public void onProgressChanged(SeekBar bar, int progress, boolean fromUser) {}
            public void onStartTrackingTouch(SeekBar bar) { seeking = true; }
            public void onStopTrackingTouch(SeekBar bar) {
                seeking = false;
                actions.run("seek", String.valueOf(bar.getProgress()));
            }
        });
        playerDetails.addView(seek, new LayoutParams(-1, dp(38)));
        playingTime = text("", 11, Color.LTGRAY, false);
        playerDetails.addView(playingTime);
        Button playbackOptions=button("Queue · Repeat · Timer","player-options",v->actions.run("player-options",""));
        playbackOptions.setContentDescription("Queue, repeat, and sleep timer options");
        playerDetails.addView(playbackOptions);
        playerDetails.setVisibility(GONE);player.addView(playerDetails);
        player.setVisibility(GONE);
        addView(player);
        navigation = row();
        navigation.setPadding(0, dp(1), 0, 0);
        navigation.setBackgroundColor(PAPER);
        addView(navigation);
        render();
    }

    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private LinearLayout column() { LinearLayout v = new LinearLayout(getContext()); v.setOrientation(VERTICAL); return v; }
    private LinearLayout row() { LinearLayout v = new LinearLayout(getContext()); v.setGravity(Gravity.CENTER_VERTICAL); return v; }
    private TextView text(String value, int size, int color, boolean bold) {
        TextView view = new TextView(getContext()); view.setText(value); view.setTextSize(size); view.setTextColor(color);
        view.setTypeface(bold ? boldFace : bodyFace);
        return view;
    }
    private GradientDrawable background(int color, int radius) {
        GradientDrawable shape = new GradientDrawable(); shape.setColor(color); shape.setCornerRadius(dp(radius)); return shape;
    }
    private Button button(String title, String tag, View.OnClickListener click) {
        Button b = new Button(getContext()); b.setText(title); b.setTag(tag); b.setAllCaps(false);
        b.setTextSize(13); b.setMinHeight(dp(44)); b.setMinimumHeight(dp(44));
        b.setTextColor(INK); b.setTypeface(monoFace); b.setLetterSpacing(.04f);
        b.setStateListAnimator(null);
        GradientDrawable shape=background(PAPER,0); shape.setStroke(dp(1),INK);
        b.setBackground(new android.graphics.drawable.RippleDrawable(ColorStateList.valueOf(0x22000000),shape,null));
        b.setOnClickListener(click); return b;
    }
    private void gap(int height) { content.addView(new View(getContext()), new LayoutParams(1, dp(height))); }
    private LinearLayout card() {
        LinearLayout box = column(); box.setPadding(dp(12), dp(10), dp(12), dp(10));
        GradientDrawable shape=background(PAPER,0); shape.setStroke(dp(1),0xffb4b0a6);
        box.setBackground(shape);
        LayoutParams p = new LayoutParams(-1, -2); p.bottomMargin = dp(8); content.addView(box,p); return box;
    }
    private void heading(String title, String subtitle) {
        content.addView(text(title, 27, INK, true)); gap(2);
        content.addView(text(subtitle, 13, MUTED, false)); gap(16);
    }
    public String currentTab() { return tab; }
    public void showTab(String value) {
        EditText field = findViewWithTag("query"); if (field != null) query = field.getText().toString();
        tab = value; render(); scroll.scrollTo(0,0); actions.run("tab", value);
    }
    public void notice(String value, boolean error) {
        int version=++noticeVersion;
        message.setText(value); message.setTextColor(error ? ORANGE_TEXT : MUTED);
        message.setVisibility(value.startsWith("Local library ready") ? GONE : VISIBLE);
        if(!error)message.postDelayed(()->{if(version==noticeVersion)message.setVisibility(GONE);},5000);
    }
    public void setBusy(boolean value) {
        busy = value;
        Button submit = findViewWithTag("search");
        if (submit != null) { submit.setEnabled(!value); submit.setText(value ? "Searching…" : "Find music  →"); }
        Button savePlaylist=findViewWithTag("playlist-save");
        if(savePlaylist!=null){stylePlaylistSave(savePlaylist);savePlaylist.setText(value?"Queueing…":"Save selected songs");}
        Button saveBottom=findViewWithTag("playlist-save-bottom");if(saveBottom!=null)stylePlaylistSave(saveBottom);
    }
    public void setResults(JSONArray value) {
        playlistPreview = null; selectedPlaylistTracks.clear(); results = value; remember(value);
        if (tab.equals("find")) { EditText input = findViewWithTag("query"); if (input != null) query = input.getText().toString(); render(); }
    }
    public void setPlaylistPreview(JSONObject value) {
        playlistPreview = value; results = new JSONArray(); selectedPlaylistTracks.clear();
        JSONArray entries=value.optJSONArray("entries");if(entries==null)entries=new JSONArray();remember(entries);
        for(int i=0;i<entries.length();i++){JSONObject item=entries.optJSONObject(i);if(item!=null)selectedPlaylistTracks.add(item.optString("video_id"));}
        if(tab.equals("find")){EditText input=findViewWithTag("query");if(input!=null)query=input.getText().toString();render();}
    }
    public void remember(JSONArray entries) {
        for (int i=0;i<entries.length();i++) { JSONObject item = entries.optJSONObject(i); if(item != null) titles.put(item.optString("video_id"),item.optString("title")); }
    }
    public void setTracks(JSONArray value) {
        boolean changed = !tracks.toString().equals(value.toString()); tracks = value; remember(value);
        Set<String> available=new java.util.HashSet<>();
        for(int i=0;i<tracks.length();i++)available.add(tracks.optJSONObject(i).optString("id"));
        selectedTracks.retainAll(available);
        if(changed && tab.equals("library")) render();
    }
    public void setJobs(JSONArray value) {
        boolean changed = !jobs.toString().equals(value.toString()); jobs = value;
        if(changed && tab.equals("downloads")) render();
    }
    public void playback(String title, boolean running, int position, int duration) {
        player.setVisibility(VISIBLE); playingTitle.setText(title); toggle.setText(running ? "Pause" : "Play");
        toggle.setContentDescription((running ? "Pause " : "Play ") + title);
        if (!seeking) { seek.setMax(Math.max(0,duration)); seek.setProgress(Math.max(0,position)); }
        playingTime.setText(time(position/1000) + " / " + time(duration/1000) + "   •   "+queueDescription);
        playerHint.setText(time(position/1000)+" / "+time(duration/1000)+"  ·  Controls "+(playerExpanded?"↓":"↑"));
    }
    public void queueDescription(String value){queueDescription=value;}
    public void setAudioFormatLabel(String value){audioFormatLabel=value;if(tab.equals("find"))render();}
    public void setMetadataEnabled(boolean value){metadataEnabled=value;if(tab.equals("find"))render();}
    public void hidePlayer() { player.setVisibility(GONE); }
    private static String time(int seconds) { return String.format(Locale.ROOT,"%d:%02d",seconds/60,seconds%60); }

    private void render() {
        content.removeAllViews(); navigation.removeAllViews();
        String[] tabs = {"find","downloads","library"}; String[] labels = {"Find","Downloads","Library"};
        for (int i=0;i<tabs.length;i++) {
            String key = tabs[i]; Button b = button(labels[i],"tab-"+key,v -> showTab(key));
            b.setSelected(tab.equals(key));
            b.setBackgroundTintList(ColorStateList.valueOf(tab.equals(key) ? INK : PAPER));
            b.setTextColor(tab.equals(key) ? LIME : INK);
            navigation.addView(b, new LayoutParams(0, dp(50), 1));
        }
        if (tab.equals("find")) renderFind();
        else if(tab.equals("library")) renderLibrary();
        else renderDownloads();
    }
    private void renderFind() {
        TextView eyebrow=text("FIND IT.  SAVE IT.  PLAY IT.",10,ORANGE_TEXT,true);
        eyebrow.setTypeface(monoFace);eyebrow.setTag("brand-headline");content.addView(eyebrow);gap(5);
        content.addView(text("Find music",30,INK,true));gap(3);
        content.addView(text("Search songs or paste a playlist link.",13,MUTED,false));gap(16);
        LinearLayout box = card();
        TextView label = text("SONG, ARTIST OR LINK",10,ORANGE_TEXT,true);label.setTypeface(monoFace);box.addView(label);
        EditText input = new EditText(getContext()); input.setTag("query"); input.setText(query);
        input.setTypeface(bodyFace);
        input.setHint("What do you want to hear?"); input.setTextSize(16); input.setSingleLine(true);
        input.setInputType(android.text.InputType.TYPE_CLASS_TEXT); input.setImeOptions(EditorInfo.IME_ACTION_SEARCH);
        input.setContentDescription("Search songs or paste a playlist link");
        box.addView(input, new LayoutParams(-1,dp(52)));
        Button search = button(busy ? "Searching…" : "Find music  →","search",v -> {
            String clean = input.getText().toString().trim();
            if(clean.length()<2) { input.setError("Enter a song name or link"); return; }
            android.view.inputmethod.InputMethodManager keyboard=(android.view.inputmethod.InputMethodManager)getContext().getSystemService(Context.INPUT_METHOD_SERVICE);
            if(keyboard!=null)keyboard.hideSoftInputFromWindow(input.getWindowToken(),0);
            input.clearFocus();
            query = clean; actions.run("search",clean);
        });
        search.setEnabled(!busy); search.setTextColor(INK); search.setBackgroundTintList(ColorStateList.valueOf(ORANGE));
        box.addView(search,new LayoutParams(-1,dp(48)));
        input.setOnEditorActionListener((v,id,event) -> { if(id==EditorInfo.IME_ACTION_SEARCH) { search.performClick(); return true; } return false; });
        gap(5);
        TextView preferences=text("SAVE OPTIONS",10,MUTED,true);preferences.setTypeface(monoFace);content.addView(preferences);gap(6);
        LinearLayout settings=row();
        Button format=button(audioFormatLabel+"  ▾","audio-format",v->actions.run("audio-format",""));
        format.setContentDescription("Save format: "+audioFormatLabel+". Tap to change.");
        Button details=button("Details  "+(metadataEnabled?"On":"Off"),"embed-metadata",v->actions.run("embed-metadata",""));
        details.setContentDescription("Music details and artwork "+(metadataEnabled?"on":"off")+". Tap to toggle.");
        settings.addView(format,new LayoutParams(0,dp(46),1));settings.addView(details,new LayoutParams(0,dp(46),1));content.addView(settings);
        gap(18);
        if(playlistPreview!=null) renderPlaylistPreview();
        else if(results.length()==0) {
            content.addView(text("Your next listen starts here",17,INK,true));gap(4);
            content.addView(text("Find a song, or paste a YouTube, Spotify, or SoundCloud playlist. Review matches before saving.",13,MUTED,false));
        } else {
            content.addView(text(results.length()+" results",15,INK,true)); gap(10);
            for(int i=0;i<results.length();i++) trackCard(results.optJSONObject(i),false);
        }
    }
    private void renderPlaylistPreview() {
        JSONArray entries=playlistPreview.optJSONArray("entries");if(entries==null)entries=new JSONArray();
        content.addView(text(playlistPreview.optString("title","Playlist"),21,INK,true));
        TextView count=text(selectedPlaylistTracks.size()+" selected",14,MUTED,true);count.setTag("playlist-selected-count");content.addView(count);gap(8);
        JSONArray unmatched=playlistPreview.optJSONArray("unmatched");
        if(unmatched!=null && unmatched.length()>0){content.addView(text(unmatched.length()+" tracks could not be matched. Check the songs below before saving.",12,ORANGE_TEXT,false));gap(8);}
        LinearLayout controls=row();
        JSONArray previewEntries=entries;
        Button selectAll=button("Select all","playlist-select-all",v->{selectedPlaylistTracks.clear();for(int i=0;i<previewEntries.length();i++)selectedPlaylistTracks.add(previewEntries.optJSONObject(i).optString("video_id"));render();});
        Button deselectAll=button("Deselect all","playlist-deselect-all",v->{selectedPlaylistTracks.clear();render();});
        controls.addView(selectAll,new LayoutParams(0,dp(44),1));controls.addView(deselectAll,new LayoutParams(0,dp(44),1));content.addView(controls);gap(8);
        Button save=button("Save selected songs","playlist-save",v->actions.run("save-playlist",playlistSelectionJson()));
        stylePlaylistSave(save);content.addView(save,new LayoutParams(-1,dp(48)));gap(12);
        for(int i=0;i<entries.length();i++) {
            JSONObject item=entries.optJSONObject(i);if(item==null)continue;
            String id=item.optString("video_id");LinearLayout box=card();LinearLayout line=row();
            line.addView(artworkTile(item,id),new LayoutParams(dp(54),dp(54)));
            LinearLayout labels=column();labels.setPadding(dp(10),0,dp(4),0);
            TextView title=text(item.optString("title","Untitled"),14,INK,true);title.setMaxLines(2);title.setEllipsize(android.text.TextUtils.TruncateAt.END);labels.addView(title);
            TextView meta=text(metadataLine(item),11,MUTED,false);meta.setSingleLine(true);meta.setEllipsize(android.text.TextUtils.TruncateAt.END);labels.addView(meta);
            line.addView(labels,new LayoutParams(0,-2,1));
            CheckBox selected=new CheckBox(getContext());selected.setTag("playlist-select-"+id);selected.setChecked(selectedPlaylistTracks.contains(id));
            selected.setContentDescription("Save "+item.optString("title","Untitled"));
            selected.setOnCheckedChangeListener((button,checked)->{if(checked)selectedPlaylistTracks.add(id);else selectedPlaylistTracks.remove(id);updatePlaylistSelectionControls();});
            line.addView(selected,new LayoutParams(dp(48),dp(48)));box.addView(line);box.setOnClickListener(v->selected.setChecked(!selected.isChecked()));
        }
        Button saveBottom=button("Save selected songs","playlist-save-bottom",v->actions.run("save-playlist",playlistSelectionJson()));
        stylePlaylistSave(saveBottom);content.addView(saveBottom,new LayoutParams(-1,dp(48)));
    }
    private String playlistSelectionJson() {
        JSONArray ids=new JSONArray();for(String id:selectedPlaylistTracks)ids.put(id);
        try{return new JSONObject().put("preview_id",playlistPreview.optString("preview_id")).put("video_ids",ids).toString();}
        catch(org.json.JSONException impossible){throw new IllegalStateException(impossible);}
    }
    private void updatePlaylistSelectionControls() {
        Button save=findViewWithTag("playlist-save");if(save!=null)stylePlaylistSave(save);
        Button saveBottom=findViewWithTag("playlist-save-bottom");if(saveBottom!=null)stylePlaylistSave(saveBottom);
        TextView count=findViewWithTag("playlist-selected-count");if(count!=null)count.setText(selectedPlaylistTracks.size()+" selected");
    }
    private void stylePlaylistSave(Button button) {
        boolean enabled=!busy && !selectedPlaylistTracks.isEmpty();
        button.setEnabled(enabled);
        button.setBackgroundTintList(ColorStateList.valueOf(enabled?ORANGE:0xffd5d0c4));
        button.setTextColor(enabled?INK:MUTED);
    }
    private void renderLibrary() {
        heading("Library",tracks.length()+" saved songs on this phone");
        LinearLayout controls=row();
        Button all=button("▶  Play all","library-play-all",v->actions.run("play-all",""));
        Button shuffle=button("⇄  Shuffle","library-shuffle",v->actions.run("shuffle-all",""));
        all.setEnabled(tracks.length()>0);shuffle.setEnabled(tracks.length()>0);
        all.setBackgroundTintList(ColorStateList.valueOf(INK));all.setTextColor(LIME);
        controls.addView(all,new LayoutParams(0,dp(48),1));controls.addView(shuffle,new LayoutParams(0,dp(48),1));
        content.addView(controls);gap(8);
        LinearLayout tools=row();
        Button filter=button("⌕  Search","library-filter",v->actions.run("library-filter",""));
        filter.setContentDescription("Search and sort library");
        tools.addView(filter,new LayoutParams(0,dp(45),1));
        tools.addView(button("♫  Playlists","library-playlists",v->actions.run("playlists","")),new LayoutParams(0,dp(45),1));
        content.addView(tools);gap(8);
        LinearLayout manage=row();
        if(!selectingTracks)manage.addView(button("Select songs","library-select",v->{selectingTracks=true;selectedTracks.clear();render();}),new LayoutParams(-1,dp(44)));
        else {
            Button selectAll=button("Select all","select-all",v->{for(JSONObject song:visibleLibrary())selectedTracks.add(song.optString("id"));render();});
            Button delete=button("Delete","delete-selected",v->actions.run("delete-selected",selectedTrackJson()));
            delete.setEnabled(!selectedTracks.isEmpty());
            manage.addView(selectAll,new LayoutParams(0,dp(44),1));manage.addView(delete,new LayoutParams(0,dp(44),1));
        }
        content.addView(manage);gap(8);
        LinearLayout storage=row();
        Button backup=button("Backup","library-backup",v->actions.run("library-backup",""));
        backup.setContentDescription("Backup and restore music");
        storage.addView(backup,new LayoutParams(0,dp(44),1));
        storage.addView(button("Music folder","music-folder",v->actions.run("music-folder","")),new LayoutParams(0,dp(44),1));
        content.addView(storage);
        if(selectingTracks)content.addView(button("Done · "+selectedTracks.size()+" selected","selection-done",v->{selectingTracks=false;selectedTracks.clear();render();}));
        gap(16);
        if(!libraryQuery.isEmpty()){content.addView(text("Matching “"+libraryQuery+"”",12,MUTED,false));gap(8);}
        if(tracks.length()==0) {
            TextView empty = text("No songs saved yet. Find something you love and it will show up here.",16,MUTED,false);
            empty.setTag("empty-library"); content.addView(empty);
            content.addView(button("Find music","empty-find",v -> showTab("find")));
        }
        java.util.List<JSONObject> visible=visibleLibrary();
        for(JSONObject track:visible)trackCard(track,true);
        if(!libraryQuery.isEmpty() && visible.isEmpty())content.addView(text("No saved songs match this search.",14,MUTED,false));
    }
    void filterLibrary(String query,String sort){libraryQuery=query.trim();librarySort=sort;render();}
    String libraryQuery(){return libraryQuery;}
    String librarySort(){return librarySort;}
    void finishSelection(){selectingTracks=false;selectedTracks.clear();if(tab.equals("library"))render();}
    private java.util.List<JSONObject> visibleLibrary() {
        java.util.List<JSONObject> visible=new java.util.ArrayList<>();
        for(int i=0;i<tracks.length();i++) {
            JSONObject track=tracks.optJSONObject(i);
            if(track!=null && (track.optString("title")+" "+track.optString("artist")).toLowerCase(Locale.ROOT).contains(libraryQuery.toLowerCase(Locale.ROOT)))visible.add(track);
        }
        if(librarySort.equals("oldest"))java.util.Collections.reverse(visible);
        else if(librarySort.equals("title") || librarySort.equals("artist"))visible.sort(java.util.Comparator.comparing(t->t.optString(librarySort).toLowerCase(Locale.ROOT)));
        return visible;
    }
    private String selectedTrackJson() {
        JSONArray ids=new JSONArray();for(String id:selectedTracks)ids.put(id);return ids.toString();
    }
    private void updateDeleteSelected() {
        Button delete=findViewWithTag("delete-selected");if(delete!=null)delete.setEnabled(!selectedTracks.isEmpty());
        Button done=findViewWithTag("selection-done");if(done!=null)done.setText("Done · "+selectedTracks.size()+" selected");
    }
    private void trackCard(JSONObject item, boolean saved) {
        if(item==null) return;
        String id = item.optString(saved ? "id" : "video_id");
        LinearLayout box = card();LinearLayout line=row();
        line.addView(artworkTile(item,id),new LayoutParams(dp(58),dp(58)));
        LinearLayout labels=column();labels.setPadding(dp(10),0,dp(6),0);
        TextView title=text(item.optString("title","Untitled"),14,INK,true);title.setMaxLines(2);title.setEllipsize(android.text.TextUtils.TruncateAt.END);labels.addView(title);
        TextView metadata=text(metadataLine(item),11,MUTED,false);metadata.setSingleLine(true);metadata.setEllipsize(android.text.TextUtils.TruncateAt.END);metadata.setTag("metadata-"+id);labels.addView(metadata);
        line.addView(labels,new LayoutParams(0,-2,1));
        if(saved && selectingTracks) {
            CheckBox selected=new CheckBox(getContext());selected.setTag("select-"+id);selected.setContentDescription("Select "+item.optString("title"));selected.setChecked(selectedTracks.contains(id));
            selected.setOnCheckedChangeListener((button,checked)->{if(checked)selectedTracks.add(id);else selectedTracks.remove(id);updateDeleteSelected();});
            line.addView(selected,new LayoutParams(dp(48),dp(48)));box.addView(line);box.setOnClickListener(v->selected.setChecked(!selected.isChecked()));return;
        }
        String existingId="";
        if(!saved)for(int i=0;i<tracks.length();i++){JSONObject local=tracks.optJSONObject(i);if(local!=null && id.equals(local.optString("video_id"))){existingId=local.optString("id");break;}}
        final String localId=existingId;
        Button primary = button(saved || !localId.isEmpty() ? "▶" : "Save",(saved ? "play-" : "save-")+id,
                v -> actions.run(saved || !localId.isEmpty() ? "play" : "save",localId.isEmpty()?id:localId));
        primary.setContentDescription((saved || !localId.isEmpty() ? "Play " : "Save ")+item.optString("title"));
        if(saved || !localId.isEmpty()){primary.setBackgroundTintList(ColorStateList.valueOf(INK));primary.setTextColor(LIME);}
        line.addView(primary,new LayoutParams(saved ? dp(48) : dp(62),dp(46)));
        if(saved) {
            Button more = button("⋮","more-"+id,v -> actions.run("more",id));
            more.setContentDescription("More options for "+item.optString("title")); line.addView(more,new LayoutParams(dp(46),dp(46)));
        }
        box.addView(line);
    }
    private String metadataLine(JSONObject item) {
        java.util.List<String> details=new java.util.ArrayList<>();
        String artist=item.optString("artist").trim();details.add(usefulMetadata(artist)?artist:"Unknown artist");
        String album=item.optString("album").trim();if(usefulMetadata(album))details.add(album);
        String date=item.optString("release_date").trim();if(usefulMetadata(date) && date.length()>=4)details.add(date.substring(0,4));
        int duration=item.optInt("duration");if(duration>0)details.add(time(duration));
        return android.text.TextUtils.join("  ·  ",details);
    }
    private static boolean usefulMetadata(String value) {
        return !value.isEmpty() && !value.equalsIgnoreCase("null") && !value.equalsIgnoreCase("none");
    }
    static boolean isTrustedArtworkUrl(String value) {
        try {
            java.net.URL url=new java.net.URL(value);
            if(!"https".equalsIgnoreCase(url.getProtocol()))return false;
            String host=url.getHost().toLowerCase(Locale.ROOT);
            return host.equals("i.ytimg.com") || host.equals("lh3.googleusercontent.com")
                    || host.equals("i.scdn.co") || host.equals("image-cdn-ak.spotifycdn.com")
                    || host.equals("mosaic.scdn.co") || host.equals("i1.sndcdn.com");
        } catch(java.net.MalformedURLException ignored) {
            return false;
        }
    }
    private FrameLayout artworkTile(JSONObject item,String id) {
        FrameLayout tile=new FrameLayout(getContext());tile.setBackground(background(0xffe6e0d2,0));
        TextView mark=text("♪",22,ORANGE,true);mark.setGravity(Gravity.CENTER);tile.addView(mark,new FrameLayout.LayoutParams(-1,-1));
        String artwork=item.optString("artwork_url",item.optString("thumbnail")).trim();
        if(!isTrustedArtworkUrl(artwork))return tile;
        ImageView image=new ImageView(getContext());image.setTag("artwork-"+id);image.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        image.setScaleType(ImageView.ScaleType.CENTER_CROP);
        image.setBackground(background(Color.TRANSPARENT,0));image.setClipToOutline(true);
        tile.addView(image,new FrameLayout.LayoutParams(-1,-1));
        android.graphics.Bitmap cached=ART_CACHE.get(artwork);if(cached!=null){image.setImageBitmap(cached);return tile;}
        ARTWORK.execute(()->{
            java.net.HttpURLConnection connection=null;
            try {
                connection=(java.net.HttpURLConnection)new java.net.URL(artwork).openConnection();connection.setConnectTimeout(5000);connection.setReadTimeout(10000);
                connection.setInstanceFollowRedirects(false);
                if(connection.getResponseCode()!=java.net.HttpURLConnection.HTTP_OK)return;
                long size=connection.getContentLengthLong();if(size>5L*1024L*1024L)return;
                java.io.ByteArrayOutputStream bytes=new java.io.ByteArrayOutputStream();
                try(java.io.InputStream input=connection.getInputStream()){
                    byte[] buffer=new byte[8192];int count;
                    while((count=input.read(buffer))!=-1){if(bytes.size()+count>5L*1024L*1024L)return;bytes.write(buffer,0,count);}
                }
                byte[] data=bytes.toByteArray();BitmapFactory.Options options=new BitmapFactory.Options();options.inJustDecodeBounds=true;
                BitmapFactory.decodeByteArray(data,0,data.length,options);options.inSampleSize=1;
                while(options.outWidth/options.inSampleSize>256 || options.outHeight/options.inSampleSize>256)options.inSampleSize*=2;
                options.inJustDecodeBounds=false;
                android.graphics.Bitmap bitmap=BitmapFactory.decodeByteArray(data,0,data.length,options);
                if(bitmap!=null){ART_CACHE.put(artwork,bitmap);image.post(()->image.setImageBitmap(bitmap));}
            }catch(Exception ignored){}finally{if(connection!=null)connection.disconnect();}
        });
        return tile;
    }
    private void renderDownloads() {
        int complete=0,failed=0;
        for(int i=0;i<jobs.length();i++) { String status=jobs.optJSONObject(i).optString("status"); if(status.equals("complete"))complete++; if(status.equals("error"))failed++; }
        heading("Downloads", jobs.length()==0 ? "Your saved music starts here." : complete+" saved  ·  "+failed+" failed  ·  "+(jobs.length()-complete-failed)+" pending");
        if(jobs.length()==0) { content.addView(text("Nothing queued yet. Search for a song or paste a playlist in Find.",15,MUTED,false));content.addView(button("Find music","empty-downloads-find",v->showTab("find"))); return; }
        if(failed>0)content.addView(button("Retry failed","retry-failed",v->actions.run("retry-failed","")));
        content.addView(text("RECENT ACTIVITY",10,MUTED,true));gap(8);
        for(int i=0;i<jobs.length();i++) {
            JSONObject job=jobs.optJSONObject(i); if(job==null)continue;
            String id=job.optString("id"), video=job.optString("video_id"), status=job.optString("status");
            LinearLayout box=card();LinearLayout line=row();LinearLayout labels=column();
            TextView title=text(titles.getOrDefault(video,job.optString("title",video)),14,INK,true);title.setMaxLines(2);title.setEllipsize(android.text.TextUtils.TruncateAt.END);labels.addView(title);
            String label = status.equals("complete") ? "Saved · ready to play" : status.equals("starting") ? "Preparing audio…" : status.equals("processing") ? "Finishing…" : status.equals("error") ? "Couldn't save this song" : status.equals("queued") ? "Waiting in queue" : "Downloading · "+job.optInt("percent")+"%";
            if(status.equals("complete") && !job.optString("format_fallback").isEmpty())
                label = "Saved as "+job.optString("format_fallback").toUpperCase(Locale.ROOT)+" · M4A unavailable";
            labels.addView(text(label,11,status.equals("error")?ORANGE_TEXT:MUTED,false));line.addView(labels,new LayoutParams(0,-2,1));
            if(status.equals("error")) {
                line.addView(button("Retry","retry-"+id,v -> actions.run("save",video)),new LayoutParams(dp(62),dp(44)));
                box.addView(line);TextView error=text(job.optString("error","Please try again."),11,MUTED,false); error.setTag("error-"+id);box.addView(error);
            } else if(status.equals("complete")) {
                Button play=button("▶","play-job-"+id,v -> actions.run("play",job.optString("track_id")));
                play.setContentDescription("Play "+title.getText());line.addView(play,new LayoutParams(dp(48),dp(44)));box.addView(line);
            } else {
                line.addView(button("Cancel","cancel-"+id,v->actions.run("cancel-download",id)),new LayoutParams(dp(70),dp(44)));box.addView(line);
                ProgressBar progress=new ProgressBar(getContext(),null,android.R.attr.progressBarStyleHorizontal);
                progress.setMax(100); progress.setProgress(Math.max(0,Math.min(100,job.optInt("percent"))));
                progress.setIndeterminate(status.equals("starting") || status.equals("processing"));
                box.addView(progress,new LayoutParams(-1,dp(10)));
            }
        }
    }
}
