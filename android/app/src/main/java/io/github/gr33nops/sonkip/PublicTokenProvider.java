package io.github.gr33nops.sonkip;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.Context;
import android.graphics.Bitmap;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.WebResourceError;
import android.webkit.WebResourceResponse;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import org.json.JSONObject;
import org.json.JSONTokener;
import java.io.InputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/** Internal browser only for public YouTube attestation; never exposes a JavaScript bridge. */
public final class PublicTokenProvider {
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    // This process-lifetime WebView deliberately uses only the application
    // context; activities attach and detach it without being retained.
    @SuppressLint("StaticFieldLeak")
    private static WebView browser;
    private static volatile boolean loaded;
    private static volatile String loadError;
    private static long loadStarted;
    private static String script;

    @SuppressLint("SetJavaScriptEnabled")
    public static void initialize(Context context) throws Exception {
        if (browser != null) { attach(context); return; }
        try (InputStream input = context.getAssets().open("mint-token.js")) {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            byte[] buffer = new byte[4096];
            int count;
            while ((count = input.read(buffer)) != -1) bytes.write(buffer, 0, count);
            script = bytes.toString(StandardCharsets.UTF_8.name());
        }
        browser = new WebView(context.getApplicationContext());
        browser.getSettings().setJavaScriptEnabled(true);
        browser.getSettings().setDomStorageEnabled(true);
        browser.getSettings().setAllowFileAccess(false);
        browser.getSettings().setAllowContentAccess(false);
        browser.getSettings().setUserAgentString(browser.getSettings().getUserAgentString()
                .replace("; wv", "").replace("Version/4.0 ", ""));
        browser.setWebViewClient(new WebViewClient() {
            @Override public void onPageStarted(WebView view, String url, Bitmap favicon) {
                loaded = false;
            }
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri url = request.getUrl();
                return !"https".equals(url.getScheme()) ||
                        !("www.youtube.com".equals(url.getHost()) || "m.youtube.com".equals(url.getHost()));
            }
            @Override public void onPageFinished(WebView view, String url) {
                Uri uri = Uri.parse(url);
                if ("https".equals(uri.getScheme()) && ("www.youtube.com".equals(uri.getHost()) || "m.youtube.com".equals(uri.getHost()))) {
                    view.evaluateJavascript(script + "; !!window.top['havuokmhhs-0']?.bevasrs?.wpc",
                            result -> loaded = "true".equals(result));
                }
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) {
                    loaded = false;
                    loadError = "YouTube connection failed (" + error.getErrorCode() + "). Check your connection, then tap Retry.";
                }
            }
            @Override public void onReceivedHttpError(WebView view, WebResourceRequest request, WebResourceResponse response) {
                if (request.isForMainFrame()) {
                    loaded = false;
                    loadError = "YouTube page returned HTTP " + response.getStatusCode() + ". Please try again later.";
                }
            }
        });
        attach(context);
        reload();
    }

    private static void attach(Context context) {
        if (!(context instanceof Activity)) return;
        ViewGroup host = ((Activity)context).findViewById(android.R.id.content);
        if (browser.getParent() != host) {
            if (browser.getParent() instanceof ViewGroup) ((ViewGroup)browser.getParent()).removeView(browser);
            // Keep the engine in the live window behind the opaque native UI.
            // GONE/detached WebViews may be suspended by the renderer.
            browser.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS);
            browser.setFocusable(false);
            browser.setFocusableInTouchMode(false);
            host.addView(browser, 0, new ViewGroup.LayoutParams(1, 1));
        }
        browser.onResume();
    }

    public static void detach(Activity activity) {
        if (browser != null && browser.getParent() == activity.findViewById(android.R.id.content)) {
            ((ViewGroup)browser.getParent()).removeView(browser);
        }
    }

    private static void reload() {
        loaded = false;
        loadError = null;
        loadStarted = SystemClock.elapsedRealtime();
        browser.loadUrl("https://www.youtube.com?themeRefresh=1");
    }

    public static void awaitReady() throws Exception {
        if (Looper.myLooper() == Looper.getMainLooper()) throw new IllegalStateException("Token work must run in background");
        if (browser == null) throw new Exception("YouTube connection is not initialized. Reopen Sonkip.");
        if (loaded) return;
        CountDownLatch prepared = new CountDownLatch(1);
        MAIN.post(() -> {
            if (loadError != null || (!loaded && SystemClock.elapsedRealtime() - loadStarted > 35000)) reload();
            prepared.countDown();
        });
        if (!prepared.await(5, TimeUnit.SECONDS)) throw new Exception("YouTube connection could not start. Tap Retry.");
        long deadline = SystemClock.elapsedRealtime() + 30000;
        while (!loaded && SystemClock.elapsedRealtime() < deadline) {
            if (loadError != null) throw new Exception(loadError);
            // YouTube can keep background assets loading after its token API is
            // ready. Do not rely exclusively on onPageFinished.
            if (Boolean.TRUE.equals(evaluate("!!window.top['havuokmhhs-0']?.bevasrs?.wpc"))) {
                evaluate(script);
                loaded = true;
                return;
            }
            Thread.sleep(500);
        }
        if (!loaded) {
            loadError = "YouTube connection could not start within 30 seconds. Keep Sonkip open and tap Retry.";
            throw new Exception(loadError);
        }
    }

    private static Object evaluate(String code) throws Exception {
        CountDownLatch ready = new CountDownLatch(1);
        AtomicReference<String> value = new AtomicReference<>();
        MAIN.post(() -> browser.evaluateJavascript(code, result -> {
            value.set(result);
            ready.countDown();
        }));
        if (!ready.await(8, TimeUnit.SECONDS)) throw new Exception("YouTube browser response timed out");
        return new JSONTokener(value.get()).nextValue();
    }

    public static synchronized String requestToken(String binding) throws Exception {
        if (Looper.myLooper() == Looper.getMainLooper()) throw new IllegalStateException("Token work must run in background");
        awaitReady();
        String id = UUID.randomUUID().toString();
        evaluate("window.__sonkipResult = null; sonkipMint(" + JSONObject.quote(binding) + ")"
                + ".then(t => window.__sonkipResult = {id:" + JSONObject.quote(id) + ",token:t})"
                + ".catch(e => window.__sonkipResult = {id:" + JSONObject.quote(id) + ",error:String(e)}); null;");
        for (int i = 0; i < 65; i++) {
            Object value = evaluate("window.__sonkipResult");
            if (value instanceof JSONObject) {
                JSONObject result = (JSONObject) value;
                if (id.equals(result.optString("id"))) {
                    if (result.has("error")) throw new Exception(result.getString("error"));
                    return result.getString("token");
                }
            }
            Thread.sleep(500);
        }
        throw new Exception("YouTube token request timed out. Please try again.");
    }
}
