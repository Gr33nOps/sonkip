package io.github.gr33nops.sonkip;

import android.app.Service;
import android.app.Notification;
import android.content.Intent;
import android.os.Looper;
import org.robolectric.shadows.ShadowMediaPlayer;
import java.time.Duration;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;
import org.robolectric.annotation.Config;
import org.robolectric.annotation.Implements;
import static org.robolectric.Shadows.shadowOf;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk = 28, shadows = BackgroundServicesTest.BluetoothDeviceShadow.class)
public class BackgroundServicesTest {
    // Robolectric 4.17's Bluetooth shadow references a class absent on API 28.
    // These tests do not use Bluetooth; keep its unrelated shadow out of decoder setup.
    @Implements(android.bluetooth.BluetoothDevice.class)
    public static class BluetoothDeviceShadow {}
    @Test public void sleepTimerPausesBackgroundPlayback()throws Exception {
        ShadowMediaPlayer.setMediaInfoProvider(source -> new ShadowMediaPlayer.MediaInfo(180000,0));
        var controller=Robolectric.buildService(PlaybackService.class).create();
        PlaybackService service=controller.get();
        try {
            service.onStartCommand(new Intent().setAction("play").putExtra("id","aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa").putExtra("title","One"),0,1);
            shadowOf(Looper.getMainLooper()).idleFor(Duration.ofMillis(50));
            assertTrue(service.isPlaying());
            java.lang.reflect.Method timer=java.util.Arrays.stream(PlaybackService.class.getDeclaredMethods()).filter(m->m.getName().equals("sleepAfter")).findFirst().orElse(null);
            assertNotNull("Playback needs a sleep timer",timer);
            timer.invoke(service,1);
            shadowOf(Looper.getMainLooper()).idleFor(Duration.ofSeconds(59));assertTrue(service.isPlaying());
            shadowOf(Looper.getMainLooper()).idleFor(Duration.ofSeconds(2));assertFalse(service.isPlaying());
        } finally {controller.destroy();}
    }

    @Test public void repeatOneReplaysOnCompletionButNextStillSkips()throws Exception {
        ShadowMediaPlayer.setMediaInfoProvider(source -> new ShadowMediaPlayer.MediaInfo(1000,0));
        var controller=Robolectric.buildService(PlaybackService.class).create();
        PlaybackService service=controller.get();
        try {
            PlaybackService.playQueue(service,new org.json.JSONArray("[{\"id\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"title\":\"One\"},{\"id\":\"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\",\"title\":\"Two\"}]"),false,false);
            service.onStartCommand(new Intent().setAction("queue"),0,1);
            java.lang.reflect.Method repeat=java.util.Arrays.stream(PlaybackService.class.getDeclaredMethods()).filter(m->m.getName().equals("repeat")).findFirst().orElse(null);
            assertNotNull("Playback needs repeat controls",repeat);repeat.invoke(service,"one");
            shadowOf(Looper.getMainLooper()).idleFor(Duration.ofMillis(1100));
            assertEquals("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",service.trackId);
            service.next();assertEquals("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",service.trackId);
        } finally {controller.destroy();}
    }
    @Test public void completionAndNotificationNextAdvanceTheSameQueue()throws Exception {
        ShadowMediaPlayer.setMediaInfoProvider(source -> new ShadowMediaPlayer.MediaInfo(1000,0));
        var controller=Robolectric.buildService(PlaybackService.class).create();
        PlaybackService service=controller.get();
        org.json.JSONArray songs=new org.json.JSONArray("[{\"id\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"title\":\"One\"},{\"id\":\"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\",\"title\":\"Two\"},{\"id\":\"cccccccccccccccccccccccccccccccc\",\"title\":\"Three\"}]");
        java.lang.reflect.Method play;
        try{play=PlaybackService.class.getDeclaredMethod("playQueue",android.content.Context.class,org.json.JSONArray.class,boolean.class,boolean.class);}
        catch(NoSuchMethodException e){fail("Playback service does not accept a library queue");return;}
        play.invoke(null,service,songs,false,false);
        service.onStartCommand(new Intent().setAction("queue"),0,1);
        shadowOf(Looper.getMainLooper()).idleFor(Duration.ofMillis(50));
        assertEquals("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",service.trackId);
        shadowOf(Looper.getMainLooper()).idleFor(Duration.ofMillis(1000));
        assertEquals("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",service.trackId);
        service.onStartCommand(new Intent().setAction("next"),0,2);
        shadowOf(Looper.getMainLooper()).idleFor(Duration.ofMillis(50));
        assertEquals("cccccccccccccccccccccccccccccccc",service.trackId);
        service.onStartCommand(new Intent().setAction("previous"),0,3);
        shadowOf(Looper.getMainLooper()).idleFor(Duration.ofMillis(50));
        assertEquals("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",service.trackId);
        controller.destroy();
    }
    private Class<? extends Service> service(String name) {
        try { return Class.forName("io.github.gr33nops.sonkip." + name).asSubclass(Service.class); }
        catch (ClassNotFoundException e) { fail("Missing background service: " + name); return null; }
    }

    @Test public void downloadWorkImmediatelyGetsForegroundNotification() {
        var controller = Robolectric.buildService(service("DownloadService")).create();
        Service service = controller.get();
        service.onStartCommand(new Intent().setAction("begin"), 0, 1);
        Notification notification = shadowOf(service).getLastForegroundNotification();
        assertNotNull("Downloads need a foreground notification before network work", notification);
        assertTrue(notification.extras.getCharSequence(Notification.EXTRA_TEXT).toString().contains("Preparing"));
        controller.destroy();
        assertTrue(shadowOf(service).isForegroundStopped());
    }

    @Test public void playbackStopRemovesForegroundNotification() {
        var controller = Robolectric.buildService(service("PlaybackService")).create();
        Service service = controller.get();
        service.onStartCommand(new Intent().setAction("stop"), 0, 1);
        assertTrue(shadowOf(service).isStoppedBySelf());
        controller.destroy();
    }

    @Test public void servicesCannotBeStartedByOtherApps() {
        for (String name : new String[]{"PlaybackService", "DownloadService"}) {
            Intent intent = new Intent().setClassName(RuntimeEnvironment.getApplication(), "io.github.gr33nops.sonkip." + name);
            var resolved = RuntimeEnvironment.getApplication().getPackageManager().resolveService(intent, 0);
            assertNotNull("Service must be registered: " + name, resolved);
            assertFalse(resolved.serviceInfo.exported);
        }
    }

    @Test public void musicPlaysWithoutAnActivityAndNotificationCanPauseAndResume() {
        // Replace only Android's decoder: Robolectric cannot decode a real audio stream.
        ShadowMediaPlayer.setMediaInfoProvider(source -> new ShadowMediaPlayer.MediaInfo(180000, 0));
        var controller = Robolectric.buildService(PlaybackService.class).create();
        PlaybackService service = controller.get();
        service.onStartCommand(new Intent().setAction("play")
            .putExtra("id", "0123456789abcdef0123456789abcdef").putExtra("title", "A saved song"), 0, 1);
        shadowOf(Looper.getMainLooper()).idleFor(Duration.ofMillis(50));
        assertTrue(service.isPlaying());
        assertEquals("A saved song", shadowOf(service).getLastForegroundNotification().extras.getString(Notification.EXTRA_TITLE));
        service.onStartCommand(new Intent().setAction("pause"), 0, 2);
        assertFalse(service.isPlaying());
        service.onStartCommand(new Intent().setAction("resume"), 0, 3);
        assertTrue(service.isPlaying());
        controller.destroy();
        assertNull(PlaybackService.current);
    }
}
