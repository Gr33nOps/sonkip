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
