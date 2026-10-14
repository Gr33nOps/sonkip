package io.github.gr33nops.sonkip;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.DownloadManager;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Build;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.widget.FrameLayout;
import android.widget.TextView;
import android.widget.Toast;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import java.io.File;
import java.net.HttpURLConnection;
import java.net.URL;

public class MainActivity extends Activity {
    private static final String LOCAL_URL = "http://127.0.0.1:8765/";
    private static final int FILE_PICKER_REQUEST = 42;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private WebView webView;
    private TextView statusView;
    private ValueCallback<Uri[]> filePickerCallback;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        createInterface();
        startLocalApp();
    }

    @SuppressLint("SetJavaScriptEnabled")
    private void createInterface() {
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.rgb(243, 240, 232));

        webView = new WebView(this);
        webView.setVisibility(View.INVISIBLE);
        webView.setBackgroundColor(Color.rgb(243, 240, 232));
        webView.getSettings().setJavaScriptEnabled(true);
        webView.getSettings().setDomStorageEnabled(true);
        webView.getSettings().setMediaPlaybackRequiresUserGesture(false);
        webView.getSettings().setAllowFileAccess(false);
        webView.getSettings().setAllowContentAccess(false);
        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(
                    WebView view,
                    ValueCallback<Uri[]> callback,
                    WebChromeClient.FileChooserParams params) {
                if (filePickerCallback != null) {
                    filePickerCallback.onReceiveValue(null);
                }
                filePickerCallback = callback;
                Intent picker = new Intent(Intent.ACTION_OPEN_DOCUMENT);
                picker.addCategory(Intent.CATEGORY_OPENABLE);
                picker.setType("text/plain");
                startActivityForResult(picker, FILE_PICKER_REQUEST);
                return true;
            }
        });
        webView.setDownloadListener((url, userAgent, contentDisposition, mimeType, contentLength) -> {
            try {
                String filename = URLUtil.guessFileName(url, contentDisposition, mimeType);
                DownloadManager.Request request = new DownloadManager.Request(Uri.parse(url));
                request.setMimeType(mimeType);
                request.setTitle(filename);
                request.setDescription("Exporting from Sonkip");
                request.setNotificationVisibility(
                        DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    request.setDestinationInExternalPublicDir(Environment.DIRECTORY_MUSIC, filename);
                }
                DownloadManager manager = (DownloadManager) getSystemService(DOWNLOAD_SERVICE);
                manager.enqueue(request);
                Toast.makeText(this, "Saving " + filename, Toast.LENGTH_SHORT).show();
            } catch (Exception error) {
                Toast.makeText(this, "Could not export this song", Toast.LENGTH_LONG).show();
            }
        });
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if ("127.0.0.1".equals(uri.getHost())) {
                    return false;
                }
                if ("http".equals(uri.getScheme()) || "https".equals(uri.getScheme())) {
                    startActivity(new Intent(Intent.ACTION_VIEW, uri));
                    return true;
                }
                return true;
            }
        });

        statusView = new TextView(this);
        statusView.setText("SONKIP\nSTARTING LOCALLY…");
        statusView.setTextColor(Color.rgb(22, 22, 22));
        statusView.setTextSize(16);
        statusView.setGravity(Gravity.CENTER);

        root.addView(webView, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT));
        root.addView(statusView, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT));
        setContentView(root);
    }

    private void startLocalApp() {
        Thread serverThread = new Thread(() -> {
            try {
                if (!Python.isStarted()) {
                    Python.start(new AndroidPlatform(getApplicationContext()));
                }
                Python python = Python.getInstance();
                python.getModule("os").get("environ").callAttr("__setitem__",
                        "SONKIP_QUICKJS", getApplicationInfo().nativeLibraryDir + "/libqjs.so");
                PyObject module = python.getModule("app.android_server");
                File moduleFile = new File(module.get("__file__").toString());
                File staticDir = new File(moduleFile.getParentFile(), "static");
                File musicDir = new File(getFilesDir(), "music");
                PyObject server = module.callAttr(
                        "create_android_server",
                        musicDir.getAbsolutePath(),
                        staticDir.getAbsolutePath(),
                        "127.0.0.1",
                        8765);
                new Thread(this::waitUntilReady, "sonkip-ready-check").start();
                server.callAttr("serve_forever");
            } catch (Exception error) {
                showError(error.getMessage());
            }
        }, "sonkip-local-server");
        serverThread.setDaemon(true);
        serverThread.start();
    }

    private void waitUntilReady() {
        for (int attempt = 0; attempt < 80; attempt++) {
            try {
                HttpURLConnection connection = (HttpURLConnection)
                        new URL(LOCAL_URL + "api/health").openConnection();
                connection.setConnectTimeout(250);
                connection.setReadTimeout(250);
                if (connection.getResponseCode() == 200) {
                    mainHandler.post(() -> {
                        webView.loadUrl(LOCAL_URL);
                        webView.setVisibility(View.VISIBLE);
                        statusView.setVisibility(View.GONE);
                    });
                    return;
                }
            } catch (Exception ignored) {
                // The embedded server is still loading Python modules.
            }
            try {
                Thread.sleep(100);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                return;
            }
        }
        showError("The local server did not start in time.");
    }

    private void showError(String detail) {
        mainHandler.post(() -> statusView.setText(
                "SONKIP COULD NOT START\n\n" + (detail == null ? "Unknown error" : detail)));
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == FILE_PICKER_REQUEST && filePickerCallback != null) {
            Uri[] result = WebChromeClient.FileChooserParams.parseResult(resultCode, data);
            filePickerCallback.onReceiveValue(result);
            filePickerCallback = null;
            return;
        }
        super.onActivityResult(requestCode, resultCode, data);
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onDestroy() {
        if (webView != null) {
            webView.destroy();
        }
        super.onDestroy();
    }
}
