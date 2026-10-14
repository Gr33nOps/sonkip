"""Build the pinned QuickJS runtime before assembling the APK (no pip deps)."""
import os
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parent
sdk = Path(os.environ.get("ANDROID_HOME") or os.environ["ANDROID_SDK_ROOT"])
ndk = sdk / "ndk" / "28.2.13676358"
cmake = shutil.which("cmake") or str(sdk / "cmake/3.22.1/bin/cmake")
ninja = shutil.which("ninja") or str(sdk / "cmake/3.22.1/bin/ninja")
output = root / "app/build/generated/runtime"
for abi in ("arm64-v8a", "armeabi-v7a"):
    build = root / "app/build/quickjs" / abi
    subprocess.run([cmake, "-S", str(root / "native"), "-B", str(build),
                    "-G", "Ninja", f"-DCMAKE_MAKE_PROGRAM={ninja}",
                    f"-DCMAKE_TOOLCHAIN_FILE={ndk}/build/cmake/android.toolchain.cmake",
                    f"-DANDROID_ABI={abi}", "-DANDROID_PLATFORM=android-24",
                    "-DCMAKE_BUILD_TYPE=Release"], check=True)
    subprocess.run([cmake, "--build", str(build), "--target", "qjs_exe", "--parallel", "2"], check=True)
    target = output / abi
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(build / "_deps/quickjs-build/libqjs.so", target / "libqjs.so")
license_dir = root / "app/build/generated/runtimeLicenses"
license_dir.mkdir(parents=True, exist_ok=True)
shutil.copy2(build / "_deps/quickjs-src/LICENSE", license_dir / "QuickJS.txt")
