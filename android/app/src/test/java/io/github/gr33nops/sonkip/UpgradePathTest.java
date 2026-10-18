package io.github.gr33nops.sonkip;

import static org.junit.Assert.assertTrue;

import android.content.Context;
import android.content.pm.PackageInfo;

import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;

@RunWith(RobolectricTestRunner.class)
public class UpgradePathTest {
    @Test public void formatReleaseUpgradesTheInstalledRuntimeBundle() throws Exception {
        Context context = RuntimeEnvironment.getApplication();
        PackageInfo packageInfo = context.getPackageManager().getPackageInfo(context.getPackageName(), 0);
        assertTrue(
            "The fixed audio-format runtime must replace the earlier format build",
            packageInfo.getLongVersionCode() > 18
        );
    }
}
