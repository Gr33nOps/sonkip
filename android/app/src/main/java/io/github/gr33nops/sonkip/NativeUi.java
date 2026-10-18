package io.github.gr33nops.sonkip;

import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.widget.*;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

/** Native Android widgets only. The internal token browser is never the app UI. */
public class NativeUi extends LinearLayout {
    public interface Actions { void run(String action, String value); }
    private static final int INK = Color.rgb(20,20,18), PAPER = Color.rgb(244,241,232),
            MUTED = Color.rgb(100,98,90), ORANGE = Color.rgb(255,80,0), LIME = Color.rgb(220,255,0);
    private final Actions actions;
    private final LinearLayout content, navigation, player;
    private final TextView message, playingTitle, playingTime;
    private final Button toggle;
    private final SeekBar seek;
    private JSONArray tracks = new JSONArray(), jobs = new JSONArray(), results = new JSONArray();
    private final Map<String,String> titles = new HashMap<>();
    private String tab = "find", query = "";
    private String libraryQuery="", librarySort="newest";
    private String queueDescription="Saved on this phone";
    private String audioFormatLabel="Original audio";
    private boolean busy, seeking;

    public NativeUi(Context context, Actions actions) {
        super(context);
        this.actions = actions;
        setOrientation(VERTICAL);
        setBackgroundColor(PAPER);
        LinearLayout brand = row();
        brand.setPadding(dp(22), dp(14), dp(22), dp(10));
        TextView logo = text("sonkip.", 29, INK, true);
        brand.addView(logo, new LayoutParams(0, -2, 1));
        TextView local = text("LOCAL ONLY", 10, MUTED, true);
        local.setTypeface(Typeface.MONOSPACE);
        brand.addView(local);
        addView(brand);
        message = text("Starting your local library…", 12, MUTED, false);
        message.setPadding(dp(22), 0, dp(22), dp(8));
        message.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        addView(message);
        ScrollView scroll = new ScrollView(context);
        scroll.setFillViewport(true);
        content = column();
        content.setPadding(dp(20), dp(14), dp(20), dp(20));
        scroll.addView(content);
        addView(scroll, new LayoutParams(-1, 0, 1));

        player = column();
        player.setPadding(dp(18), dp(10), dp(18), dp(6));
        player.setBackgroundColor(INK);
        LinearLayout playerRow = row();
        playingTitle = text("", 14, Color.WHITE, true);
        playingTitle.setMaxLines(2);
        playerRow.addView(playingTitle, new LayoutParams(0, -2, 1));
        toggle = button("Play", "player-toggle", v -> actions.run("toggle", ""));
        toggle.setBackgroundTintList(ColorStateList.valueOf(Color.rgb(220,245,98)));
        toggle.setTextColor(INK);
        playerRow.addView(toggle);
        player.addView(playerRow);
        LinearLayout transport=row();
        Button previous=button("← Previous","player-previous",v->actions.run("previous",""));
        Button next=button("Next →","player-next",v->actions.run("next",""));
        transport.addView(previous,new LayoutParams(0,dp(48),1));
        transport.addView(next,new LayoutParams(0,dp(48),1));player.addView(transport);
        seek = new SeekBar(context);
        seek.setContentDescription("Playback position");
        seek.setProgressTintList(ColorStateList.valueOf(Color.rgb(220,245,98)));
        seek.setThumbTintList(ColorStateList.valueOf(Color.rgb(220,245,98)));
        seek.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            public void onProgressChanged(SeekBar bar, int progress, boolean fromUser) {}
            public void onStartTrackingTouch(SeekBar bar) { seeking = true; }
            public void onStopTrackingTouch(SeekBar bar) {
                seeking = false;
                actions.run("seek", String.valueOf(bar.getProgress()));
            }
        });
        player.addView(seek, new LayoutParams(-1, dp(32)));
        playingTime = text("", 11, Color.LTGRAY, false);
        player.addView(playingTime);
        player.addView(button("Queue · Repeat · Sleep timer","player-options",v->actions.run("player-options","")));
        player.setVisibility(GONE);
        addView(player);
        navigation = row();
        navigation.setPadding(dp(8), dp(5), dp(8), dp(7));
        navigation.setBackgroundColor(PAPER);
        addView(navigation);
        render();
    }

    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private LinearLayout column() { LinearLayout v = new LinearLayout(getContext()); v.setOrientation(VERTICAL); return v; }
    private LinearLayout row() { LinearLayout v = new LinearLayout(getContext()); v.setGravity(Gravity.CENTER_VERTICAL); return v; }
    private TextView text(String value, int size, int color, boolean bold) {
        TextView view = new TextView(getContext()); view.setText(value); view.setTextSize(size); view.setTextColor(color);
        if (bold) view.setTypeface(Typeface.create("sans-serif", Typeface.BOLD));
        return view;
    }
    private GradientDrawable background(int color, int radius) {
        GradientDrawable shape = new GradientDrawable(); shape.setColor(color); shape.setCornerRadius(dp(radius)); return shape;
    }
    private Button button(String title, String tag, View.OnClickListener click) {
        Button b = new Button(getContext()); b.setText(title); b.setTag(tag); b.setAllCaps(false);
        b.setTextSize(13); b.setMinHeight(dp(48)); b.setMinimumHeight(dp(48));
        b.setTextColor(INK); b.setTypeface(Typeface.MONOSPACE); b.setLetterSpacing(.04f);
        GradientDrawable shape=background(PAPER,2); shape.setStroke(dp(1),INK);
        b.setBackground(new android.graphics.drawable.RippleDrawable(ColorStateList.valueOf(0x22000000),shape,null));
        b.setOnClickListener(click); return b;
    }
    private void gap(int height) { content.addView(new View(getContext()), new LayoutParams(1, dp(height))); }
    private LinearLayout card() {
        LinearLayout box = column(); box.setPadding(dp(16), dp(14), dp(16), dp(12));
        GradientDrawable shape=background(PAPER,2); shape.setStroke(dp(1),Color.rgb(190,187,178));
        box.setBackground(shape);
        LayoutParams p = new LayoutParams(-1, -2); p.bottomMargin = dp(10); content.addView(box,p); return box;
    }
    private void heading(String title, String subtitle) {
        content.addView(text(title, 32, INK, true)); gap(4);
        content.addView(text(subtitle, 14, MUTED, false)); gap(22);
    }
    public String currentTab() { return tab; }
    public void showTab(String value) {
        EditText field = findViewWithTag("query"); if (field != null) query = field.getText().toString();
        tab = value; render(); actions.run("tab", value);
    }
    public void notice(String value, boolean error) { message.setText(value); message.setTextColor(error ? ORANGE : MUTED); }
    public void setBusy(boolean value) {
        busy = value;
        Button submit = findViewWithTag("search");
        if (submit != null) { submit.setEnabled(!value); submit.setText(value ? "Working…" : "Find music  →"); }
    }
    public void setResults(JSONArray value) {
        results = value; remember(value);
        if (tab.equals("find")) { EditText input = findViewWithTag("query"); if (input != null) query = input.getText().toString(); render(); }
    }
    public void remember(JSONArray entries) {
        for (int i=0;i<entries.length();i++) { JSONObject item = entries.optJSONObject(i); if(item != null) titles.put(item.optString("video_id"),item.optString("title")); }
    }
    public void setTracks(JSONArray value) {
        boolean changed = !tracks.toString().equals(value.toString()); tracks = value; remember(value);
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
    }
    public void queueDescription(String value){queueDescription=value;}
    public void setAudioFormatLabel(String value){audioFormatLabel=value;if(tab.equals("find"))render();}
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
            navigation.addView(b, new LayoutParams(0, dp(54), 1));
        }
        if (tab.equals("find")) renderFind();
        else if(tab.equals("library")) renderLibrary();
        else renderDownloads();
    }
    private void renderFind() {
        TextView eyebrow=text("YOUR MUSIC, ON YOUR DEVICE",10,MUTED,false);
        eyebrow.setTypeface(Typeface.MONOSPACE); content.addView(eyebrow); gap(16);
        LinearLayout hero=row();
        TextView headline=text("FIND IT.\nSAVE IT.\nPLAY IT.",42,INK,true);
        headline.setTag("brand-headline"); headline.setLetterSpacing(-.065f);
        headline.setLineSpacing(0,.88f);
        android.text.SpannableString lines=new android.text.SpannableString(headline.getText());
        lines.setSpan(new android.text.style.ForegroundColorSpan(ORANGE),9,17,0);
        headline.setText(lines);
        hero.addView(headline,new LayoutParams(0,-2,1));
        View record=new View(getContext()) {
            private final android.graphics.Paint paint=new android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG);
            @Override protected void onDraw(android.graphics.Canvas canvas) {
                float r=Math.min(getWidth(),getHeight())*.44f,cx=getWidth()*.47f,cy=getHeight()*.47f;
                paint.setStyle(android.graphics.Paint.Style.FILL);paint.setColor(ORANGE);canvas.drawCircle(cx+dp(5),cy+dp(7),r,paint);
                paint.setColor(INK);canvas.drawCircle(cx,cy,r,paint);
                paint.setStyle(android.graphics.Paint.Style.STROKE);paint.setStrokeWidth(dp(1));paint.setColor(0xff373732);
                for(float groove=r-dp(4);groove>r*.37f;groove-=dp(4))canvas.drawCircle(cx,cy,groove,paint);
                paint.setStyle(android.graphics.Paint.Style.FILL);paint.setColor(LIME);canvas.drawCircle(cx,cy,r*.33f,paint);
                paint.setColor(INK);paint.setTypeface(Typeface.DEFAULT_BOLD);paint.setTextSize(r*.32f);paint.setTextAlign(android.graphics.Paint.Align.CENTER);canvas.drawText("SK",cx,cy+r*.1f,paint);
            }
        };
        record.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        hero.addView(record,new LayoutParams(dp(118),dp(140)));content.addView(hero);gap(24);
        LinearLayout box = card();
        TextView label = text("SONGS & PLAYLISTS",11,ORANGE,true); box.addView(label);
        EditText input = new EditText(getContext()); input.setTag("query"); input.setText(query);
        input.setHint("Song, artist, or playlist link"); input.setTextSize(16); input.setSingleLine(true);
        input.setInputType(android.text.InputType.TYPE_CLASS_TEXT); input.setImeOptions(EditorInfo.IME_ACTION_SEARCH);
        input.setContentDescription("Search songs or paste a playlist link");
        box.addView(input, new LayoutParams(-1,dp(60)));
        Button search = button(busy ? "Working…" : "Find music  →","search",v -> {
            String clean = input.getText().toString().trim();
            if(clean.length()<2) { input.setError("Enter a song name or link"); return; }
            query = clean; actions.run("search",clean);
        });
        search.setEnabled(!busy); search.setTextColor(INK); search.setBackgroundTintList(ColorStateList.valueOf(ORANGE));
        box.addView(search,new LayoutParams(-1,dp(54)));
        input.setOnEditorActionListener((v,id,event) -> { if(id==EditorInfo.IME_ACTION_SEARCH) { search.performClick(); return true; } return false; });
        gap(8);
        content.addView(button("Save as · "+audioFormatLabel,"audio-format",v->actions.run("audio-format","")));
        gap(14);
        if(results.length()==0) {
            content.addView(text("Save a song or a whole playlist.",18,INK,true)); gap(8);
            content.addView(text("YouTube, Spotify, or SoundCloud playlists. Spotify and SoundCloud tracks are matched on YouTube; versions may differ. Downloads continue while you use other apps.",14,MUTED,false));
        } else {
            content.addView(text(results.length()+" results",14,MUTED,true)); gap(10);
            for(int i=0;i<results.length();i++) trackCard(results.optJSONObject(i),false);
        }
    }
    private void renderLibrary() {
        heading("SAVED.",tracks.length()+" songs on this phone");
        LinearLayout controls=row();
        Button all=button("Play all","library-play-all",v->actions.run("play-all",""));
        Button shuffle=button("Shuffle","library-shuffle",v->actions.run("shuffle-all",""));
        all.setEnabled(tracks.length()>0);shuffle.setEnabled(tracks.length()>0);
        controls.addView(all,new LayoutParams(0,dp(48),1));controls.addView(shuffle,new LayoutParams(0,dp(48),1));
        content.addView(controls);gap(8);
        content.addView(button("My playlists","library-playlists",v->actions.run("playlists","")));
        content.addView(button("Search & sort","library-filter",v->actions.run("library-filter","")));
        content.addView(button("Backup & restore","library-backup",v->actions.run("library-backup","")));
        content.addView(button("Music folder","music-folder",v->actions.run("music-folder","")));
        if(!libraryQuery.isEmpty())content.addView(text("Matching: "+libraryQuery,12,MUTED,false));
        content.addView(text("Play all follows download order, oldest first.",12,MUTED,false));gap(16);
        if(tracks.length()==0) {
            TextView empty = text("No saved songs yet.\nSearch for a song in Find.",18,MUTED,false);
            empty.setTag("empty-library"); content.addView(empty);
            content.addView(button("Find music","empty-find",v -> showTab("find")));
        }
        java.util.List<JSONObject> visible=new java.util.ArrayList<>();
        for(int i=0;i<tracks.length();i++) {
            JSONObject track=tracks.optJSONObject(i);
            if(track!=null && (track.optString("title")+" "+track.optString("artist")).toLowerCase(Locale.ROOT).contains(libraryQuery.toLowerCase(Locale.ROOT)))visible.add(track);
        }
        if(librarySort.equals("oldest"))java.util.Collections.reverse(visible);
        else if(librarySort.equals("title") || librarySort.equals("artist"))visible.sort(java.util.Comparator.comparing(t->t.optString(librarySort).toLowerCase(Locale.ROOT)));
        for(JSONObject track:visible)trackCard(track,true);
        if(!libraryQuery.isEmpty() && visible.isEmpty())content.addView(text("No saved songs match this search.",14,MUTED,false));
    }
    void filterLibrary(String query,String sort){libraryQuery=query.trim();librarySort=sort;render();}
    private void trackCard(JSONObject item, boolean saved) {
        if(item==null) return;
        String id = item.optString(saved ? "id" : "video_id");
        LinearLayout box = card(); box.addView(text(item.optString("title","Untitled"),17,INK,true));
        box.addView(text(item.optString("artist","Unknown artist")+"  ·  "+time(item.optInt("duration")),12,MUTED,false));
        LinearLayout buttons = row();
        String existingId="";
        if(!saved)for(int i=0;i<tracks.length();i++){JSONObject local=tracks.optJSONObject(i);if(local!=null && id.equals(local.optString("video_id"))){existingId=local.optString("id");break;}}
        final String localId=existingId;
        Button primary = button(saved ? "Play" : localId.isEmpty()?"Save":"Play saved",(saved ? "play-" : "save-")+id,
                v -> actions.run(saved || !localId.isEmpty() ? "play" : "save",localId.isEmpty()?id:localId));
        buttons.addView(primary,new LayoutParams(0,dp(48),1));
        if(saved) {
            buttons.addView(button("Export","export-"+id,v -> actions.run("export",id)),new LayoutParams(0,dp(48),1));
            Button more = button("More","more-"+id,v -> actions.run("more",id));
            more.setContentDescription("More options for "+item.optString("title")); buttons.addView(more);
        }
        box.addView(buttons);
    }
    private void renderDownloads() {
        int complete=0,failed=0;
        for(int i=0;i<jobs.length();i++) { String status=jobs.optJSONObject(i).optString("status"); if(status.equals("complete"))complete++; if(status.equals("error"))failed++; }
        heading("DOWNLOADS.", jobs.length()==0 ? "Songs you save appear here." : complete+" saved  ·  "+failed+" failed  ·  "+(jobs.length()-complete-failed)+" pending");
        if(jobs.length()==0) { content.addView(text("Nothing queued yet.\nSave a song or paste a playlist in Find.",18,MUTED,false)); return; }
        content.addView(text("You can switch apps. Check progress in your notifications.",12,MUTED,false)); gap(12);
        if(failed>0)content.addView(button("Retry failed","retry-failed",v->actions.run("retry-failed","")));
        for(int i=jobs.length()-1;i>=0;i--) {
            JSONObject job=jobs.optJSONObject(i); if(job==null)continue;
            String id=job.optString("id"), video=job.optString("video_id"), status=job.optString("status");
            LinearLayout box=card(); box.addView(text(titles.getOrDefault(video,job.optString("title",video)),16,INK,true));
            String label = status.equals("complete") ? "Saved · ready to play" : status.equals("starting") ? "Preparing audio…" : status.equals("processing") ? "Finishing…" : status.equals("error") ? "Couldn't save this song" : status.equals("queued") ? "Waiting in queue" : "Downloading · "+job.optInt("percent")+"%";
            box.addView(text(label,12,status.equals("error")?ORANGE:MUTED,false));
            if(status.equals("error")) {
                TextView error=text(job.optString("error","Please try again."),12,MUTED,false); error.setTag("error-"+id); box.addView(error);
                box.addView(button("Retry","retry-"+id,v -> actions.run("save",video)));
            } else if(status.equals("complete")) {
                box.addView(button("Play","play-job-"+id,v -> actions.run("play",job.optString("track_id"))));
            } else {
                ProgressBar progress=new ProgressBar(getContext(),null,android.R.attr.progressBarStyleHorizontal);
                progress.setMax(100); progress.setProgress(Math.max(0,Math.min(100,job.optInt("percent"))));
                progress.setIndeterminate(status.equals("starting") || status.equals("processing"));
                box.addView(progress,new LayoutParams(-1,dp(16)));
                box.addView(button("Cancel","cancel-"+id,v->actions.run("cancel-download",id)));
            }
        }
    }
}
