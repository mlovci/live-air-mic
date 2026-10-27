# Latency Optimization & Tuning Guide for LiveAirMic

Achieving seamless, live-monitoring studio audio requires tuning three stages: **the phone capture**, **the local network/USB transport**, and **the Ableton Live buffer pipeline**.

---

## 1. Transport Latency: USB Fast-Track vs. 5GHz Wi-Fi

### Option A: USB Cable + Native Fast-Track APK (`~8.5 – 11.5 ms` Total Acoustic Latency)
For live vocal monitoring or RF-crowded stages:
1. Plug your Android phone into your Mac via a USB-C cable with **USB Debugging** enabled.
2. Drop [`m4l/LiveAirMic.amxd`](../m4l/LiveAirMic.amxd) onto your Ableton track (or click **USB Connect** on the device UI).
3. **Why it is fastest**:
   - Uses Android's C/JNI `AAudio` MMAP hardware path (`~2.0 ms` capture burst) instead of the browser's WebAudio stack.
   - Tunnels raw 128-sample (`2.67 ms`) PCM frames over physical USB (`adb reverse tcp:8766 tcp:8766`) with `< 0.3 ms` transit latency and zero Wi-Fi jitter.

### Option B: 5GHz / 6GHz Wi-Fi Browser PWA (`~11.8 – 14.3 ms` Network/Bridge Latency)
When using the zero-install mobile web app (`https://<mac-ip>:8765`) across the room:
1. **Always connect to 5GHz or 6GHz, NEVER 2.4GHz**:
   - 2.4GHz suffers from Bluetooth interference and narrow channel contention.
   - 5GHz/6GHz keeps one-way packet transit between `1.5 – 4.0 ms`.
2. **Disable Router "Band Steering" / "Smart Connect"**:
   - Prevents the router from hopping your phone between 2.4GHz and 5GHz mid-take.
3. **Note on Mobile Browser Input Buffering**:
   - Mobile browsers (Chrome/Safari) add an OS-enforced `10 – 25 ms` input capture buffer before `AudioWorklet` receives frames, bringing total acoustic glass-to-ear latency in Wi-Fi mode to `~22 – 38 ms`.

---

## 2. Ableton Live Buffer Configuration

Because [`LiveAirMic.amxd`](../m4l/LiveAirMic.amxd) injects audio directly into the Ableton track via `jit.release~`, **no virtual audio driver (`BlackHole`) is needed**.
1. In Ableton Live, open **Preferences $\rightarrow$ Audio** (`Cmd + ,`).
2. Keep your normal **Audio Output Device** (your wired studio headphones or audio interface).
3. Set **Buffer Size**:
   - **64 Samples** (`1.33 ms` at 48kHz) or **128 Samples** (`2.67 ms` at 48kHz) for ultra-low live monitoring.
   - Avoid 512 or 1024 samples while recording vocals, as large host buffers add audible slapback delay.
4. Set **In/Out Sample Rate** to **48,000 Hz**.

---

## 3. Monitoring Rule: Wired Headphones Only

> [!CAUTION]
> **NEVER monitor through Bluetooth headphones or Bluetooth earbuds (AirPods, Galaxy Buds) while recording!**
> Bluetooth audio codecs introduce a mandatory **`150 – 250 ms`** hardware delay. Always plug wired headphones directly into your Mac or audio interface.
