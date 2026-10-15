package io.github.gr33nops.sonkip;

import android.app.*;
import android.content.*;
import android.content.pm.ServiceInfo;
import android.media.*;
import android.media.session.MediaSession;
import android.media.session.PlaybackState;
import android.net.Uri;
import android.os.*;

/** Owns playback independently of the activity, including lock-screen controls. */
public class PlaybackService extends Service {
    static PlaybackService current;
    static String error;
    String trackId = "", title = "";
    private MediaPlayer player;
    private MediaSession session;
    private AudioManager audio;
    private AudioFocusRequest focus;
    private boolean prepared, resumeOnFocus;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Runnable idleStop = () -> { if (!isPlaying()) stopSelf(); };
    private final AudioManager.OnAudioFocusChangeListener focusListener = change -> {
        if (change == AudioManager.AUDIOFOCUS_GAIN) {
            if (resumeOnFocus) resume();
        } else if (change < 0) {
            boolean resume = change != AudioManager.AUDIOFOCUS_LOSS && isPlaying();
            pause(); resumeOnFocus = resume;
        }
    };
    private final BroadcastReceiver noisy = new BroadcastReceiver() {
        @Override public void onReceive(Context context, Intent intent) { pause(); }
    };

    @Override public void onCreate() {
        super.onCreate(); current = this;
        audio = (AudioManager)getSystemService(AUDIO_SERVICE);
        if (Build.VERSION.SDK_INT >= 26) {
            getSystemService(NotificationManager.class).createNotificationChannel(
                new NotificationChannel("playback", "Music playback", NotificationManager.IMPORTANCE_LOW));
            focus = new AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN)
                .setAudioAttributes(attributes()).setOnAudioFocusChangeListener(focusListener).build();
        }
        session = new MediaSession(this, "Sonkip");
        session.setCallback(new MediaSession.Callback() {
            @Override public void onPlay() { resume(); }
            @Override public void onPause() { pause(); }
            @Override public void onStop() { stopSelf(); }
            @Override public void onSeekTo(long position) { seek((int)position); }
        });
        session.setFlags(MediaSession.FLAG_HANDLES_MEDIA_BUTTONS | MediaSession.FLAG_HANDLES_TRANSPORT_CONTROLS);
        IntentFilter filter = new IntentFilter(AudioManager.ACTION_AUDIO_BECOMING_NOISY);
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(noisy, filter, Context.RECEIVER_NOT_EXPORTED);
        else registerReceiver(noisy, filter);
    }
    private static AudioAttributes attributes() {
        return new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA)
            .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build();
    }
    static void play(Context context, String id, String title) {
        Intent intent = new Intent(context, PlaybackService.class).setAction("play")
            .putExtra("id", id).putExtra("title", title);
        if (Build.VERSION.SDK_INT >= 26) context.startForegroundService(intent); else context.startService(intent);
    }
    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent == null ? "stop" : intent.getAction();
        if ("stop".equals(action)) { stopSelf(); return START_NOT_STICKY; }
        if ("pause".equals(action)) pause();
        else if ("resume".equals(action)) resume();
        else if ("play".equals(action)) {
            trackId = intent.getStringExtra("id"); title = intent.getStringExtra("title");
            error = null; prepared = false; resumeOnFocus = false;
            handler.removeCallbacks(idleStop);
            promote();
            if (player != null) player.release();
            player = new MediaPlayer();
            player.setAudioAttributes(attributes());
            player.setWakeMode(this, PowerManager.PARTIAL_WAKE_LOCK);
            try {
                if (trackId == null || !trackId.matches("[0-9a-f]{32}")) throw new IllegalArgumentException("Invalid saved song");
                player.setDataSource(this, Uri.parse("http://127.0.0.1:8765/api/tracks/" + trackId + "/audio"));
                player.setOnPreparedListener(p -> { if (p == player) { prepared = true; resume(); } });
                player.setOnCompletionListener(p -> pause());
                player.setOnErrorListener((p, what, extra) -> { failPlayback(); return true; });
                player.prepareAsync();
            } catch (Exception e) { failPlayback(); }
        }
        return START_NOT_STICKY;
    }
    private void failPlayback() {
        error = "Android could not play this file. Try exporting it to another player.";
        stopSelf();
    }
    boolean isPlaying() { return prepared && player != null && player.isPlaying(); }
    boolean isPrepared() { return prepared; }
    int position() { return prepared ? player.getCurrentPosition() : 0; }
    int duration() { return prepared ? player.getDuration() : 0; }
    void toggle() { if (isPlaying()) pause(); else resume(); }
    void seek(int position) { if (prepared) { player.seekTo(Math.max(0, Math.min(position, duration()))); publish(); } }
    private void resume() {
        if (!prepared) return;
        promote();
        int granted = Build.VERSION.SDK_INT >= 26 ? audio.requestAudioFocus(focus)
            : audio.requestAudioFocus(focusListener, AudioManager.STREAM_MUSIC, AudioManager.AUDIOFOCUS_GAIN);
        if (granted != AudioManager.AUDIOFOCUS_REQUEST_GRANTED) { pause(); return; }
        handler.removeCallbacks(idleStop); resumeOnFocus = false;
        player.start(); session.setActive(true); publish();
    }
    private void pause() {
        resumeOnFocus = false;
        if (isPlaying()) player.pause();
        publish(); stopForeground(STOP_FOREGROUND_DETACH);
        handler.removeCallbacks(idleStop); handler.postDelayed(idleStop, 300000);
    }
    private PendingIntent command(String action) {
        Intent intent = new Intent(this, PlaybackService.class).setAction(action);
        return PendingIntent.getService(this, action.hashCode(), intent, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }
    private Notification notification() {
        Notification.Builder builder = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(this, "playback") : new Notification.Builder(this);
        if(Build.VERSION.SDK_INT>=26)builder.setColorized(true);
        boolean playing = isPlaying();
        return builder.setSmallIcon(R.drawable.ic_stat_music).setLargeIcon(NotificationBrand.artwork())
            .setColor(NotificationBrand.ORANGE).setSubText("sonkip. · LOCAL ONLY").setShowWhen(false)
            .setContentTitle(title.isEmpty() ? "Sonkip" : title)
            .setContentText(prepared ? (playing ? "Playing on this phone" : "Paused") : "Opening audio…")
            .setContentIntent(PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class), PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT))
            .setVisibility(Notification.VISIBILITY_PUBLIC).setOnlyAlertOnce(true).setOngoing(playing)
            .addAction(playing ? android.R.drawable.ic_media_pause : android.R.drawable.ic_media_play,
                playing ? "Pause" : "Play", command(playing ? "pause" : "resume"))
            .addAction(android.R.drawable.ic_menu_close_clear_cancel, "Stop", command("stop"))
            .setStyle(new Notification.MediaStyle().setMediaSession(session.getSessionToken()).setShowActionsInCompactView(0, 1)).build();
    }
    private void promote() {
        if (Build.VERSION.SDK_INT >= 29) startForeground(201, notification(), ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK);
        else startForeground(201, notification());
    }
    private void publish() {
        session.setMetadata(new MediaMetadata.Builder().putString(MediaMetadata.METADATA_KEY_TITLE, title)
            .putLong(MediaMetadata.METADATA_KEY_DURATION, duration()).build());
        session.setPlaybackState(new PlaybackState.Builder().setActions(PlaybackState.ACTION_PLAY | PlaybackState.ACTION_PAUSE
            | PlaybackState.ACTION_PLAY_PAUSE | PlaybackState.ACTION_STOP | PlaybackState.ACTION_SEEK_TO)
            .setState(isPlaying() ? PlaybackState.STATE_PLAYING : PlaybackState.STATE_PAUSED, position(), isPlaying() ? 1f : 0f).build());
        getSystemService(NotificationManager.class).notify(201, notification());
    }
    @Override public void onDestroy() {
        handler.removeCallbacksAndMessages(null);
        if (player != null) { player.release(); player = null; }
        prepared = false;
        if (Build.VERSION.SDK_INT >= 26) audio.abandonAudioFocusRequest(focus); else audio.abandonAudioFocus(focusListener);
        unregisterReceiver(noisy); session.release(); stopForeground(STOP_FOREGROUND_REMOVE);
        getSystemService(NotificationManager.class).cancel(201);
        if (current == this) current = null;
        super.onDestroy();
    }
    @Override public IBinder onBind(Intent intent) { return null; }
}
