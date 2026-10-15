package io.github.gr33nops.sonkip;

import android.app.Activity;
import android.webkit.WebView;
import org.junit.After;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;
import java.lang.reflect.Field;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk = 28)
public class PublicTokenProviderTest {
    @Test public void appCanInspectNetworkConfigurationForBrowserDns() {
        android.content.Context context=org.robolectric.RuntimeEnvironment.getApplication();
        assertEquals("Browser DNS needs access to the active network configuration",
                android.content.pm.PackageManager.PERMISSION_GRANTED,
                context.getPackageManager().checkPermission(android.Manifest.permission.ACCESS_NETWORK_STATE,
                        context.getPackageName()));
    }
    private Field browserField() throws Exception {
        Field field=PublicTokenProvider.class.getDeclaredField("browser");field.setAccessible(true);return field;
    }
    @After public void cleanBrowser() throws Exception {
        WebView browser=(WebView)browserField().get(null);
        if(browser!=null)browser.destroy();
        browserField().set(null,null);
    }
    @Test public void tokenBrowserParticipatesInActivityLifecycle() throws Exception {
        Activity activity=Robolectric.buildActivity(Activity.class).setup().visible().get();
        PublicTokenProvider.initialize(activity);
        WebView browser=(WebView)browserField().get(null);
        assertNotNull("Token browser must be attached even though the app uses native screens",browser.getParent());
        activity.finish();
    }
}
