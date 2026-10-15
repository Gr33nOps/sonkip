package io.github.gr33nops.sonkip;

import android.app.*;
import android.content.*;
import android.content.pm.ServiceInfo;
import android.os.*;
import org.json.JSONArray;
import java.net.*;
import java.io.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

/** Keeps user-started imports/downloads alive after the screen closes. */
public class DownloadService extends Service {
    private static final AtomicInteger pending = new AtomicInteger();
    private final Handler main = new Handler(Looper.getMainLooper());
    private final ScheduledExecutorService worker = Executors.newSingleThreadScheduledExecutor();
    private PowerManager.WakeLock wake;
    private boolean destroyed;
    private int failures;

    static void begin(Context context) {
        pending.incrementAndGet();
        Intent intent = new Intent(context, DownloadService.class).setAction("begin");
        try {
            if (Build.VERSION.SDK_INT >= 26) context.startForegroundService(intent); else context.startService(intent);
        } catch (RuntimeException e) { pending.decrementAndGet(); throw e; }
    }
    static void end() { pending.updateAndGet(n -> Math.max(0, n - 1)); }
    @Override public void onCreate() {
        super.onCreate();
        if (Build.VERSION.SDK_INT >= 26) getSystemService(NotificationManager.class).createNotificationChannel(
            new NotificationChannel("downloads", "Downloads", NotificationManager.IMPORTANCE_LOW));
        wake = getSystemService(PowerManager.class).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "Sonkip:downloads");
        wake.setReferenceCounted(false);
        worker.scheduleWithFixedDelay(this::poll, 1, 1, TimeUnit.SECONDS);
    }
    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        Notification notification = DownloadNotice.build(this, new JSONArray(), false);
        if (Build.VERSION.SDK_INT >= 29) startForeground(202, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
        else startForeground(202, notification);
        wake.acquire(10 * 60 * 1000L);
        return START_NOT_STICKY;
    }
    private void poll() {
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection)new URL("http://127.0.0.1:8765/api/jobs").openConnection();
            connection.setConnectTimeout(3000); connection.setReadTimeout(5000);
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            try (InputStream input = connection.getInputStream()) { byte[] b = new byte[8192]; int n; while ((n = input.read(b)) != -1) bytes.write(b, 0, n); }
            JSONArray jobs = new org.json.JSONObject(bytes.toString("UTF-8")).getJSONArray("jobs");
            int active = 0, done = 0, errors = 0;
            for (int i = 0; i < jobs.length(); i++) {
                String status = jobs.getJSONObject(i).optString("status");
                if (status.equals("complete")) done++; else if (status.equals("error")) errors++; else active++;
            }
            final int remaining = active, completed = done, failed = errors;
            main.post(() -> {
                if (destroyed) return;
                failures = 0;
                if (remaining == 0 && pending.get() == 0) { stopSelf(); return; }
                wake.acquire(10 * 60 * 1000L);
                getSystemService(NotificationManager.class).notify(202, DownloadNotice.build(this, jobs, pending.get() > 0));
            });
        } catch (Exception e) {
            main.post(() -> {
                if(destroyed)return;
                if(++failures>=3) {
                    Notification.Builder builder=Build.VERSION.SDK_INT>=26?new Notification.Builder(this,"downloads"):new Notification.Builder(this);
                    getSystemService(NotificationManager.class).notify(202,builder.setSmallIcon(R.drawable.ic_stat_music)
                        .setColor(NotificationBrand.ORANGE).setContentTitle("Waiting for Sonkip")
                        .setContentText("Cannot read download progress. Reopen the app to check.").setOnlyAlertOnce(true).build());
                }
                if(failures>=15 && pending.get()==0)stopSelf();
            });
        } finally { if (connection != null) connection.disconnect(); }
    }
    @Override public void onTimeout(int startId, int type) {
        // Android 15 limits data-sync foreground execution. Never restart around that limit.
        stopSelf();
    }
    @Override public void onDestroy() {
        destroyed = true; worker.shutdownNow(); main.removeCallbacksAndMessages(null);
        if (wake != null && wake.isHeld()) wake.release();
        stopForeground(STOP_FOREGROUND_REMOVE); super.onDestroy();
    }
    @Override public IBinder onBind(Intent intent) { return null; }
}
