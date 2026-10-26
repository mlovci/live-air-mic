#!/usr/bin/env bash
# ==============================================================================
# LiveAirMic — Zero-Latency USB Tethering Mode (Android ADB Reverse)
# Bridges localhost:8765 directly across USB cable to Android.
# Bypasses Wi-Fi packet jitter and SSL warnings completely!
# ==============================================================================

set -e

PORT=${1:-8765}

echo "=========================================================="
echo "  LIVE AIR MIC — Ultra-Low-Latency USB Mode (ADB Reverse)  "
echo "=========================================================="

# Check ADB
if ! command -v adb &> /dev/null; then
    echo "[ERROR] 'adb' command not found in PATH."
    echo "  Please install Android platform-tools (e.g. brew install android-platform-tools)"
    exit 1
fi

# Check connected device
DEVICES=$(adb devices | grep -v "List" | grep "device$" | awk '{print $1}')

if [ -z "$DEVICES" ]; then
    echo "[!] No Android devices detected via USB."
    echo "  1. Connect your Android phone via USB cable."
    echo "  2. Ensure 'Developer Options' and 'USB Debugging' are enabled."
    echo "  3. Accept the 'Allow USB debugging' prompt on your phone."
    exit 1
fi

echo "[*] Connected Android device found: $DEVICES"
echo "[*] Setting up reverse TCP port tunnel: phone:tcp:$PORT -> mac:tcp:$PORT..."
adb reverse tcp:$PORT tcp:$PORT

echo "[*] Successfully tunneled port $PORT!"
echo ""
echo "You can now open Chrome on your Android phone and visit:"
echo "  http://localhost:$PORT"
echo ""
echo "Attempting to launch Chrome on Android device automatically..."
adb shell am start -a android.intent.action.VIEW -d "http://localhost:$PORT" 2>/dev/null || true

echo "[*] USB Tethering active. Zero Wi-Fi jitter mode engaged!"
