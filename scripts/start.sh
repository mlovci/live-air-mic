#!/usr/bin/env bash
# ==============================================================================
# LiveAirMic — One-Click Startup Script
# Starts the high-speed wireless microphone server, displays QR code,
# and streams directly into Ableton Live via Max for Live (LiveAirMic.amxd).
# ==============================================================================

set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$DIR"

echo "=========================================================="
echo "  LIVE AIR MIC — Wireless Studio Microphone for Ableton   "
echo "=========================================================="

# 1. Check Python Dependencies
python3 -c "
import aiohttp, qrcode, cryptography, pythonosc, numpy
" 2>/dev/null || {
    echo "[!] Missing required Python dependencies. Installing..."
    python3 -m pip install aiohttp qrcode cryptography python-osc numpy
}

# 2. Launch Bridge Server
echo "[*] Launching LiveAirMic Server & Max for Live Audio Bridge..."
python3 server/bridge.py "$@"
