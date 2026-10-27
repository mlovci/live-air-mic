# LiveAirMic — Wireless & USB Studio Microphone for Ableton Live & Max for Live

> **Zero-Driver, Ultra-Low-Latency Microphone Streaming from Android / Mobile Directly into Ableton Live**

**LiveAirMic** turns your Android phone (or any mobile device) into a studio microphone that streams uncompressed 48kHz PCM audio directly into Ableton Live via a custom **Max for Live (`LiveAirMic.amxd`)** Audio Effect device—with **zero virtual audio drivers (`BlackHole`) or macOS CoreAudio routing required**.

---

## Key Features

- **Zero-Driver Direct Max for Live Audio Injection**:
  - Drop [`m4l/LiveAirMic.amxd`](m4l/LiveAirMic.amxd) onto any Ableton Audio Track and audio streams directly out of the device via `jit.release~`.
  - No `BlackHole`, no Aggregate Devices, and no changes to Ableton's global Audio Input Device preferences.
- **Dual Transport Modes (USB Fast-Track & Zero-Install Wi-Fi PWA)**:
  - **USB Native Fast-Track (`~8.5 – 11.5 ms` total acoustic latency)**: Native C/JNI `AAudio` MMAP capture over `adb reverse` TCP (`128 samples` / `2.67 ms` per quantum) with built-in 85Hz high-pass rumble filter, warm ribbon low-pass conditioning, live Vocal FX pads, and a 7-track Ableton mixer console.
  - **Zero-Install Cross-Platform PWA (`~11.8 – 14.3 ms` network/bridge latency)**: Open in Chrome/Safari over 5GHz Wi-Fi via terminal QR code—no APK sideloading required.
- **Performer Remote Control & Live Transport Sync**:
  - Trigger Ableton Live clip/session recording and toggle vocal FX (`Tune Smooth`, `Dub Syndicate`, `Spring Parade`, `Warm Tube`) directly from your phone screen.
  - Real-time 120fps LED peak/RMS metering and Ableton tempo/beat readout.

---

## System Architecture

```
[ Phone Microphone (48kHz Unprocessed PCM) ]
         │
         ├──► (USB Native APK: AAudio MMAP 128f) ──► [ Raw TCP Port 8766 (USB ADB Reverse) ]
         │
         └──► (Mobile Browser PWA: AudioWorklet) ──► [ Binary WebSocket Port 8765 (5GHz Wi-Fi) ]
                                                                │
                                                                ▼
                                                    [ Python Audio Bridge ]
                                                                │
                                     (128-sample Float32 UDP OSC + Bidirectional LOM Telemetry)
                                                                │
                                                                ▼
                                         [ LiveAirMic.amxd (jit.fill -> jit.release~) ]
                                                                │
                                                                ▼
                                              [ Ableton Live Audio Track Chain ]
```

---

## Quickstart Guide

### 1. Drop `LiveAirMic.amxd` into Ableton Live
1. Drag and drop [`m4l/LiveAirMic.amxd`](m4l/LiveAirMic.amxd) onto any Audio Track in Ableton Live.
2. The embedded Node for Max controller ([`m4l/server_ctl.js`](m4l/server_ctl.js)) automatically starts the Python bridge server (`server/bridge.py`) and sets up the USB `adb reverse` tunnel whenever an Android phone is plugged in.

### 2. Connect Your Phone (USB Fast-Track or Wi-Fi)
- **USB Mode (Lowest Latency)**:
  - Plug your Android phone in via USB-C with **USB Debugging** enabled, or click **USB Connect** on the `LiveAirMic.amxd` device in Ableton.
- **Wi-Fi Browser Mode (Zero Install)**:
  - Run `./scripts/start.sh` in a terminal to view the local 5GHz Wi-Fi QR code (e.g. `https://192.168.1.100:8765`), scan it with your phone camera, and tap **START MIC**.

---

## Directory Structure

```
liveairmic/
├── README.md                      # Project documentation and quickstart
├── AGENTS.md                      # Enterprise engineering & agent directive
├── pyproject.toml                 # Standard Python package & pytest configuration
├── server/
│   ├── bridge.py                  # Main server (WebSocket, Raw TCP 8766, OSC, WAV recorder)
│   ├── audio_engine.py            # Pure-NumPy ring buffer, resampler, and dBFS metering engine
│   ├── osc_controller.py          # Bi-directional OSC bridge with Max for Live
│   ├── cert_gen.py                # Self-signed X.509 SSL generator with IP SAN support
│   └── interfaces.py              # PEP 544 structural Protocols for sinks, DSP, and DAW control
├── web/
│   ├── index.html                 # Studio-grade dark theme mobile web application
│   ├── app.js                     # PWA client logic (WebSocket, auto-reconnect, VU meter)
│   ├── audio-worklet.js           # AudioWorkletProcessor running on dedicated audio thread
│   ├── styles.css                 # Ableton Live-inspired dark UI with 24-segment LED meter
│   └── manifest.json              # Full-screen PWA manifest
├── android-native/
│   ├── jni/aaudio_mic.c           # Lock-free C/JNI AAudio MMAP low-latency capture & watchdog
│   └── src/com/liveairmic/pro/    # Android Native Fast-Track Studio UI, DSP filters & mixer
├── m4l/
│   ├── LiveAirMic.amxd            # Max for Live Audio Effect device for Ableton Live
│   ├── LiveAirMic.maxpat          # Raw Max patcher file
│   ├── server_ctl.js              # Embedded Node for Max server & self-healing ADB controller
│   ├── clip_align.js              # LiveAPI vocal FX chain controller & clip compensator
│   └── build_amxd.py              # Automated generator for the M4L device
├── tests/
│   ├── test_unit_core.py          # Layer 1 unit tests (ring buffer, resampling, SAN certs, AMXD)
│   └── test_reconnection_and_integration.py # Layer 2 disconnect/reconnect integration tests
├── scripts/
│   ├── start.sh                   # One-click startup script
│   ├── usb_tether.sh              # Instant ADB reverse setup for wired mode
│   ├── build_apk.sh               # Reproducible Android Native APK builder
│   └── test_stream.py             # Layer 3 live end-to-end streaming benchmark
└── docs/
    ├── ARCHITECTURE.md            # Deep dive into network protocols, buffers, and signal chain
    └── LATENCY_TUNING.md          # Guide for 5GHz Wi-Fi tuning, buffer sizes, and Android audio
```

---

## Automated Verification

Run the automated unit and reconnection test suite via `pytest`:
```bash
pytest -v
```
Or run the live end-to-end stream benchmark against a running server:
```bash
python3 scripts/test_stream.py
```

---

## Documentation Links

- [System Architecture & Protocol Specification](docs/ARCHITECTURE.md)
- [Latency Optimization & Tuning Guide](docs/LATENCY_TUNING.md)
- [Engineering & Agent Directive](AGENTS.md)
