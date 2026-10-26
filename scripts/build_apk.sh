#!/usr/bin/env bash
# ==============================================================================
# LiveAirMic — Android Native Fast-Track APK Builder
# Compiles MainActivity.java + AAudio JNI into android-native/LiveAirMic.apk
# without leaving temporary keystores or build artifacts in the repository.
# ==============================================================================

set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
ANDROID_DIR="$DIR/android-native"
SDK_DIR="${ANDROID_HOME:-$HOME/Library/Android/sdk}"

# Locate JDK 17+
if [ -d "/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home" ]; then
    export JAVA_HOME="/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home"
elif [ -d "/usr/local/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home" ]; then
    export JAVA_HOME="/usr/local/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home"
fi
if [ -n "$JAVA_HOME" ]; then
    export PATH="$JAVA_HOME/bin:$PATH"
fi

BUILD_TOOLS=$(ls -d "$SDK_DIR/build-tools/"* 2>/dev/null | sort -V | tail -n 1)
PLATFORM_DIR=$(ls -d "$SDK_DIR/platforms/android-"* 2>/dev/null | sort -V | tail -n 1)
PLATFORM_JAR="$PLATFORM_DIR/android.jar"

if [ -z "$BUILD_TOOLS" ] || [ ! -f "$PLATFORM_JAR" ]; then
    echo "[ERROR] Android SDK build-tools or android.jar not found under $SDK_DIR"
    exit 1
fi

BUILD_TMP=$(mktemp -d)
trap "rm -rf $BUILD_TMP" EXIT

echo "[*] Building LiveAirMic Native Fast-Track APK..."

# 1. Compile or preserve arm64-v8a/libaaudiomic.so
mkdir -p "$BUILD_TMP/apk_root/lib/arm64-v8a"
NDK_LLD=$(find "$SDK_DIR" -name "lld" 2>/dev/null | head -n 1)
if [ -n "$NDK_LLD" ] && [ -f "$ANDROID_DIR/jni/aaudio_mic.c" ] && command -v adb >/dev/null 2>&1 && adb get-state >/dev/null 2>&1; then
    echo "[*] Compiling android-native/jni/aaudio_mic.c for ARM64-v8a (NEON + Vocal Isolation + AFC)..."
    mkdir -p "$BUILD_TMP/syslib"
    adb pull /system/lib64/libaaudio.so "$BUILD_TMP/syslib/libaaudio.so" >/dev/null 2>&1 || true
    adb pull /system/lib64/liblog.so "$BUILD_TMP/syslib/liblog.so" >/dev/null 2>&1 || true
    adb pull /system/lib64/libm.so "$BUILD_TMP/syslib/libm.so" >/dev/null 2>&1 || true
    adb pull /system/lib64/libc.so "$BUILD_TMP/syslib/libc.so" >/dev/null 2>&1 || true
    if [ -f "$BUILD_TMP/syslib/libc.so" ]; then
        /usr/bin/clang --target=aarch64-linux-android35 -O3 -ffast-math -fPIC -march=armv8.2-a+fp16+dotprod \
            -c "$ANDROID_DIR/jni/aaudio_mic.c" -o "$BUILD_TMP/aaudio_mic.o"
        "$NDK_LLD" -flavor gnu -shared -soname libaaudiomic.so \
            "$BUILD_TMP/aaudio_mic.o" \
            "$BUILD_TMP/syslib/libaaudio.so" "$BUILD_TMP/syslib/liblog.so" \
            "$BUILD_TMP/syslib/libm.so" "$BUILD_TMP/syslib/libc.so" \
            -o "$BUILD_TMP/apk_root/lib/arm64-v8a/libaaudiomic.so"
    fi
fi
if [ ! -f "$BUILD_TMP/apk_root/lib/arm64-v8a/libaaudiomic.so" ] && [ -f "$ANDROID_DIR/LiveAirMic.apk" ]; then
    unzip -q "$ANDROID_DIR/LiveAirMic.apk" "lib/arm64-v8a/libaaudiomic.so" -d "$BUILD_TMP/apk_root" 2>/dev/null || true
fi

# 2. Compile MainActivity.java -> classes.dex
mkdir -p "$BUILD_TMP/classes" "$BUILD_TMP/apk_root"
javac --release 11 -cp "$PLATFORM_JAR" -d "$BUILD_TMP/classes" "$ANDROID_DIR/src/com/liveairmic/pro/MainActivity.java"
"$BUILD_TOOLS/d8" --lib "$PLATFORM_JAR" --output "$BUILD_TMP/apk_root" "$BUILD_TMP/classes/com/liveairmic/pro/"*.class

# 3. Link AndroidManifest.xml
"$BUILD_TOOLS/aapt2" link -I "$PLATFORM_JAR" --manifest "$ANDROID_DIR/AndroidManifest.xml" -o "$BUILD_TMP/base.apk"

# 4. Package classes.dex + native JNI library
(cd "$BUILD_TMP/apk_root" && zip -q -r "$BUILD_TMP/base.apk" classes.dex lib/)

# 5. Align and sign with persistent local debug keystore (ignored by git)
"$BUILD_TOOLS/zipalign" -f 4 "$BUILD_TMP/base.apk" "$BUILD_TMP/aligned.apk"
mkdir -p "$DIR/.certs"
KEYSTORE="$DIR/.certs/debug.keystore"
if [ ! -f "$KEYSTORE" ]; then
    keytool -genkeypair -v -keystore "$KEYSTORE" -alias airmic -keyalg RSA -keysize 2048 -validity 10000 -storepass android -keypass android -dname "CN=LiveAirMic, OU=Audio, O=LiveAirMic, L=Studio, S=CA, C=US" 2>/dev/null
fi
"$BUILD_TOOLS/apksigner" sign --ks "$KEYSTORE" --ks-pass pass:android --key-pass pass:android --out "$ANDROID_DIR/LiveAirMic.apk" "$BUILD_TMP/aligned.apk"
rm -f "$ANDROID_DIR/LiveAirMic.apk.idsig"

echo "[+] Successfully built $ANDROID_DIR/LiveAirMic.apk"
