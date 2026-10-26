"""
LiveAirMic Server & Audio Bridge.
Coordinates HTTPS web server, WebAudio AudioWorklet WebSocket streaming,
Native USB Fast-Track TCP streaming, and bidirectional Max for Live (M4L) OSC synchronization.
"""

import os
import sys
import ssl
import time
import json
import wave
import socket
import asyncio
import logging
import argparse
import threading
from pathlib import Path
from aiohttp import web
import numpy as np
import qrcode
import io

try:
    from .cert_gen import ensure_ssl_certificates, get_local_ip_addresses
    from .audio_engine import AudioEngine
    from .osc_controller import OSCBridge
except ImportError:
    from cert_gen import ensure_ssl_certificates, get_local_ip_addresses
    from audio_engine import AudioEngine
    from osc_controller import OSCBridge

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("LiveAirMic.Bridge")

class LiveAirMicServer:
    def __init__(
        self,
        port: int = 8765,
        sample_rate: int = 48000,
        channels: int = 2,
        block_size: int = 128,
        target_buffer_ms: float = 6.0,
        m4l_osc_in: int = 9002,
        m4l_osc_out: int = 9003,
        use_https: bool = True,
    ):
        self.port = port
        self.use_https = use_https
        self.root_dir = Path(__file__).resolve().parent.parent
        self.web_dir = self.root_dir / "web"
        self.certs_dir = self.root_dir / ".certs"

        # Subsystems
        self.audio = AudioEngine(
            sample_rate=sample_rate,
            channels=channels,
            block_size=block_size,
            target_buffer_ms=target_buffer_ms,
        )
        self.osc = OSCBridge(
            m4l_host="127.0.0.1",
            m4l_port=m4l_osc_in,
            listen_port=m4l_osc_out,
        )

        # Connected mobile WebSocket clients
        self.active_clients = set()
        self.connected_device_name = "None"
        self.connected_ip = ""
        self.last_latency_ms = 0.0
        self.client_sample_rate = sample_rate
        self.loop = None
        self.raw_tcp_port = 8766
        self.raw_tcp_clients = set()

        # Direct M4L buffer~ airmic_ring streaming state (49152 = 192 * 256 samples)
        self.m4l_ring_size = 49152
        self.m4l_write_offset = 0
        self.m4l_stream_active = False
        self.m4l_chunks_written = 0

        # Direct 48kHz WAV Clip Recorder (auto-imports recorded takes into Ableton clip slots)
        self.recordings_dir = self.root_dir / "recordings"
        self.recordings_dir.mkdir(parents=True, exist_ok=True)
        self._rec_lock = threading.Lock()
        self._wav_file: wave.Wave_write | None = None
        self._wav_path: Path | None = None
        self._rec_start_time: float = 0.0
        self.is_recording_clip: bool = False

        # Ableton transport cache
        self.transport_state = {
            "is_playing": False,
            "is_recording": False,
            "tempo": 120.0,
            "beat": 1.0,
            "is_armed": False,
        }

        self._pcm_accum = np.zeros(0, dtype=np.float32)

        # Wire up OSC callbacks
        self.osc.on_transport_update = self._on_m4l_transport
        self.osc.on_arm_update = self._on_m4l_arm
        self.osc.on_m4l_heartbeat = self._on_m4l_init
        self.osc.on_rec_toggle = self._on_m4l_rec_toggle

    def _start_wav_recording(self):
        with self._rec_lock:
            if self.is_recording_clip:
                return
            ts = time.strftime("%Y%m%d_%H%M%S")
            self._wav_path = self.recordings_dir / f"LiveAirMic_{ts}.wav"
            wf = wave.open(str(self._wav_path), "wb")
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit PCM
            wf.setframerate(self.audio.sample_rate)
            self._wav_file = wf
            self._rec_start_time = time.time()
            self.is_recording_clip = True
            logger.info(f"Started direct WAV clip recording: {self._wav_path}")

    def _stop_wav_recording(self):
        wav_path = None
        duration = 0.0
        with self._rec_lock:
            if not self.is_recording_clip:
                return
            self.is_recording_clip = False
            duration = time.time() - self._rec_start_time
            if self._wav_file:
                try:
                    self._wav_file.close()
                except Exception as e:
                    logger.error(f"Error closing WAV file: {e}")
                self._wav_file = None
            wav_path = self._wav_path
            self._wav_path = None

        if wav_path and wav_path.exists() and duration >= 0.2:
            logger.info(f"Finished WAV clip recording ({duration:.1f}s): {wav_path}")
            self.osc.send_import_clip(str(wav_path))
            threading.Thread(
                target=self._import_wav_to_ableton,
                args=(str(wav_path),),
                daemon=True,
            ).start()

    def _import_wav_to_ableton(self, wav_path: str):
        """Automatically insert the recorded WAV clip into the LiveAirMic track in Ableton Live."""
        try:
            def send_ableton_cmd(cmd_type: str, params: dict | None = None) -> dict:
                with socket.create_connection(("127.0.0.1", 9877), timeout=2.0) as s:
                    payload = json.dumps({"type": cmd_type, "params": params or {}}).encode("utf-8")
                    s.sendall(payload)
                    chunks = []
                    while True:
                        data = s.recv(65536)
                        if not data:
                            break
                        chunks.append(data)
                        try:
                            return json.loads(b"".join(chunks).decode("utf-8"))
                        except json.JSONDecodeError:
                            continue
                return {}

            sess = send_ableton_cmd("get_session_info").get("result", {})
            track_count = sess.get("track_count", 0)
            target_track = None
            target_slot = 0

            for idx in range(track_count):
                tinfo = send_ableton_cmd("get_track_info", {"track_index": idx}).get("result", {})
                if not tinfo.get("is_audio_track"):
                    continue
                devices = tinfo.get("devices", [])
                has_airmic = any("LiveAirMic" in d.get("name", "") for d in devices)
                if has_airmic or target_track is None:
                    target_track = idx
                    for slot in tinfo.get("clip_slots", []):
                        if not slot.get("has_clip"):
                            target_slot = slot.get("index", 0)
                            break
                    if has_airmic:
                        break

            if target_track is not None:
                res = send_ableton_cmd(
                    "create_audio_clip",
                    {"track_index": target_track, "clip_index": target_slot, "path": wav_path},
                )
                logger.info(f"Imported recorded WAV into Ableton track {target_track} slot {target_slot}: {res}")
        except Exception as e:
            logger.warning(f"Could not auto-import clip via Ableton socket: {e}")

    def _on_m4l_rec_toggle(self, state: bool):
        logger.info(f"M4L REC button toggled: {state}")
        if state:
            self._start_wav_recording()
        else:
            self._stop_wav_recording()

    def _on_m4l_init(self):
        """Called once when LiveAirMic.amxd loads in Ableton (via live.thisdevice)."""
        if self.m4l_stream_active:
            playhead = (self.m4l_write_offset - 1024) % self.m4l_ring_size
            self.osc.send_playhead(playhead)
            self.osc.send_active(True)

    def _stream_pcm_to_m4l(self, pcm_bytes: bytes):
        """Stream 16-bit PCM bytes as 128-sample Float32 chunks into M4L jit.fill -> jit.release~."""
        if not pcm_bytes:
            return
        if self.is_recording_clip:
            with self._rec_lock:
                if self._wav_file:
                    try:
                        self._wav_file.writeframes(pcm_bytes)
                    except Exception:
                        pass
        int16_arr = np.frombuffer(pcm_bytes, dtype=np.int16)
        float_arr = (int16_arr.astype(np.float32) / 32768.0)
        if len(self._pcm_accum) > 0:
            float_arr = np.concatenate((self._pcm_accum, float_arr))
        step = 128
        n = len(float_arr)
        idx = 0
        while idx + step <= n:
            chunk = float_arr[idx : idx + step]
            self.osc.send_pcm_block(chunk.tolist())
            self.audio.consume_samples(step)
            idx += step
        self._pcm_accum = float_arr[idx:]

    def _schedule_broadcast(self, msg: dict):
        """Thread-safe scheduling of WebSocket broadcast from OSC listener thread."""
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self._broadcast_json(msg))
            )

    def _on_m4l_transport(self, is_playing: bool, is_recording: bool, tempo: float, beat: float):
        was_recording = self.transport_state.get("is_recording", False)
        self.transport_state["is_playing"] = is_playing
        self.transport_state["is_recording"] = is_recording
        self.transport_state["tempo"] = tempo
        self.transport_state["beat"] = beat

        if is_recording and not was_recording:
            self._start_wav_recording()
        elif not is_recording and was_recording:
            self._stop_wav_recording()

        # Broadcast transport change to all connected mobile clients
        msg = {
            "type": "transport",
            "is_playing": is_playing,
            "is_recording": is_recording,
            "tempo": tempo,
            "beat": beat,
        }
        self._schedule_broadcast(msg)

    def _on_m4l_arm(self, is_armed: bool):
        self.transport_state["is_armed"] = is_armed
        msg = {
            "type": "arm",
            "is_armed": is_armed,
        }
        self._schedule_broadcast(msg)

    async def _broadcast_json(self, data: dict):
        if not self.active_clients:
            return
        payload = json.dumps(data)
        for ws in list(self.active_clients):
            try:
                await ws.send_str(payload)
            except Exception:
                pass

    async def handle_ws(self, request):
        ws = web.WebSocketResponse(max_msg_size=1024 * 1024)
        await ws.prepare(request)

        # If native Android Fast-Track TCP app is active, reject browser WebSocket immediately
        if self.raw_tcp_clients:
            try:
                await ws.send_str(json.dumps({"type": "replaced"}))
                await ws.close()
            except Exception:
                pass
            return ws

        # Close any previous duplicate tabs so only 1 stream is ever active
        for old_ws in list(self.active_clients):
            self.active_clients.discard(old_ws)
            try:
                await old_ws.send_str(json.dumps({"type": "replaced"}))
                await old_ws.close()
            except Exception:
                pass

        client_ip = request.remote
        self.connected_ip = client_ip
        self.active_clients.add(ws)
        client_sr = self.audio.sample_rate
        logger.info(f"Mobile client connected from {client_ip}")

        # Send initial handshake with current transport and config
        await ws.send_str(json.dumps({
            "type": "handshake",
            "server_sample_rate": self.audio.sample_rate,
            "block_size": self.audio.block_size,
            "transport": self.transport_state,
            "auto_start": True,
        }))

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.BINARY:
                    # Ingest binary PCM audio frame directly into ring buffer
                    # First 4 bytes can optionally be a packet header:
                    # [seq_hi, seq_lo, flags, channel_mode]
                    data = msg.data
                    if len(data) > 4:
                        # Raw Int16 PCM chunk
                        pcm_payload = data[4:]
                        self.audio.write_pcm_bytes(
                            pcm_payload,
                            is_int16=True,
                            source_sample_rate=client_sr,
                        )
                        self._stream_pcm_to_m4l(pcm_payload)
                    else:
                        self.audio.write_pcm_bytes(
                            data,
                            is_int16=True,
                            source_sample_rate=client_sr,
                        )
                        self._stream_pcm_to_m4l(data)

                elif msg.type == web.WSMsgType.TEXT:
                    try:
                        pkt = json.loads(msg.data)
                        msg_type = pkt.get("type")

                        if msg_type == "ping":
                            # Measure round-trip network latency using client monotonic RTT
                            # (avoiding wall-clock skew between phone and Mac)
                            client_time = pkt.get("time", 0.0)
                            client_rtt = pkt.get("rtt")
                            now = time.time() * 1000.0
                            if client_rtt is not None and float(client_rtt) > 0:
                                self.last_latency_ms = round(float(client_rtt), 2)
                            elif client_time and abs(now - client_time) < 500.0:
                                self.last_latency_ms = round(abs(now - client_time), 2)

                            await ws.send_str(json.dumps({
                                "type": "pong",
                                "client_time": client_time,
                                "server_time": now,
                                "afc": self.audio.get_afc_telemetry(),
                            }))

                        elif msg_type == "fx":
                            cmd = str(pkt.get("cmd", ""))
                            val = float(pkt.get("val", 0.0))
                            if cmd:
                                self._dispatch_fx_command(cmd, val)

                        elif msg_type == "remote_rec":
                            # Phone user pressed REC
                            state = bool(pkt.get("state", False))
                            logger.info(f"Phone remote record trigger: {state}")
                            self.osc.send_remote_rec_trigger(state)
                            if state:
                                self._start_wav_recording()
                            else:
                                self._stop_wav_recording()

                        elif msg_type == "device_info":
                            self.connected_device_name = pkt.get("device", "Mobile Device")
                            reported_sr = pkt.get("sample_rate")
                            if reported_sr and isinstance(reported_sr, (int, float)) and reported_sr > 0:
                                client_sr = int(reported_sr)
                                self.client_sample_rate = client_sr
                            logger.info(
                                f"Client device identified: {self.connected_device_name} (rate={client_sr}Hz)"
                            )

                    except Exception as e:
                        logger.error(f"Error parsing text message: {e}")

                elif msg.type == web.WSMsgType.ERROR:
                    logger.warning(f"WebSocket connection closed with exception: {ws.exception()}")

        finally:
            self.active_clients.discard(ws)
            if not self.active_clients:
                self.connected_ip = ""
                self.connected_device_name = "None"
            logger.info(f"Mobile client disconnected: {client_ip}")

        return ws

    async def handle_raw_tcp_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Ultra-low-latency raw TCP PCM stream from native Android LiveAirMic APK (port 8766)."""
        sock = writer.get_extra_info("socket")
        if sock:
            try:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except Exception:
                pass

        # Close any previous TCP clients so only 1 stream is ever active
        for old_writer in list(self.raw_tcp_clients):
            self.raw_tcp_clients.discard(old_writer)
            try:
                old_writer.close()
            except Exception:
                pass

        # Close any browser WebSocket clients so native APK has exclusive low-latency access
        for old_ws in list(self.active_clients):
            self.active_clients.discard(old_ws)
            try:
                await old_ws.send_str(json.dumps({"type": "replaced"}))
                await old_ws.close()
            except Exception:
                pass

        self._pcm_accum = np.zeros(0, dtype=np.float32)
        self.raw_tcp_clients.add(writer)
        self.connected_ip = "127.0.0.1 (USB Native)"
        self.connected_device_name = "Android USB (Native Fast-Track)"
        self.last_latency_ms = 2.6
        logger.info("Native Android Fast-Track TCP client connected on port 8766")

        try:
            # Read 1024 bytes (4 x 128-sample blocks = 10.6ms) or whatever is immediately available (256-byte aligned).
            # Enforce a 2.5-second read timeout so half-open sockets from sudden USB cable disconnects are cleaned up
            # immediately and never block subsequent browser or USB reconnections.
            rem = b""
            while True:
                chunk = await asyncio.wait_for(reader.read(2048), timeout=2.5)
                if not chunk:
                    break
                buf = rem + chunk
                valid_len = (len(buf) // 256) * 256
                if valid_len > 0:
                    payload = buf[:valid_len]
                    rem = buf[valid_len:]
                    self.audio.write_pcm_bytes(
                        payload,
                        is_int16=True,
                        source_sample_rate=self.audio.sample_rate,
                    )
                    self._stream_pcm_to_m4l(payload)
                else:
                    rem = buf
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, ConnectionError, Exception):
            pass
        finally:
            self.raw_tcp_clients.discard(writer)
            try:
                writer.close()
            except Exception:
                pass
            if not self.raw_tcp_clients and not self.active_clients:
                self.connected_ip = ""
                self.connected_device_name = "None"
            logger.info("Native Android Fast-Track TCP client disconnected")

    def _dispatch_fx_command(self, cmd: str, val: float) -> None:
        """Dispatch vocal FX command via both OSC (/airmic/fx_ctl) and M4L fast-poll file."""
        try:
            if cmd == "remote_rec":
                state = val > 0.5
                self.osc.send_remote_rec_trigger(state)
                if state:
                    self._start_wav_recording()
                else:
                    self._stop_wav_recording()
                return
            ts = int(time.time() * 1000)
            with open("/tmp/airmic_fx_cmd.txt", "w", encoding="utf-8") as f:
                f.write(f"{cmd} {val} {ts}\n")
            self.osc._send_osc("/airmic/fx_ctl", ["fx_ctl", str(cmd), float(val)])
        except Exception as e:
            logger.error(f"Error handling FX command {cmd}={val}: {e}")

    async def handle_fx_api(self, request):
        """Instantaneous vocal FX control endpoint called from the Android Native App or Web PWA."""
        cmd = request.query.get("cmd", "")
        val = float(request.query.get("val", "0"))
        if cmd:
            self._dispatch_fx_command(cmd, val)
        return web.json_response({"ok": True, "cmd": cmd, "val": val})

    async def handle_usb_connect_api(self, request):
        """Re-establish USB ADB reverse tunnel and force-restart/foreground LiveAirMic on connected Android phone."""
        import subprocess
        import shutil
        adb_bin = shutil.which("adb")
        for cand in [
            "/opt/homebrew/bin/adb",
            "/usr/local/homebrew/bin/adb",
            "/usr/local/bin/adb",
            str(Path.home() / "Library/Android/sdk/platform-tools/adb"),
        ]:
            if Path(cand).exists():
                adb_bin = cand
                break

        if not adb_bin:
            return web.json_response({"ok": False, "error": "adb not found"}, status=500)

        apk_path = self.root_dir / "android-native" / "LiveAirMic.apk"
        cmd = (
            f'"{adb_bin}" reverse tcp:8765 tcp:8765 && '
            f'"{adb_bin}" reverse tcp:8766 tcp:8766 && '
            f'("{adb_bin}" shell am start -S -W -n com.liveairmic.pro/.MainActivity || '
            f'(("{adb_bin}" install -r -g "{apk_path}" || ("{adb_bin}" uninstall com.liveairmic.pro && "{adb_bin}" install -g "{apk_path}")) && "{adb_bin}" shell am start -n com.liveairmic.pro/.MainActivity))'
        )
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=8.0)
            return web.json_response({
                "ok": proc.returncode == 0,
                "stdout": stdout.decode("utf-8", errors="ignore").strip(),
                "stderr": stderr.decode("utf-8", errors="ignore").strip(),
            })
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_status_api(self, request):
        telemetry = self.audio.get_telemetry()
        telemetry["connected_clients"] = len(self.active_clients) + len(self.raw_tcp_clients)
        telemetry["connected_device"] = self.connected_device_name
        telemetry["connected_ip"] = self.connected_ip
        telemetry["latency_ms"] = self.last_latency_ms
        telemetry["transport"] = self.transport_state
        return web.json_response(telemetry)

    async def telemetry_loop(self):
        """High-rate loop (25-30 FPS) pushing audio metering and status to M4L via OSC."""
        while True:
            try:
                is_streaming_active = (time.time() - self.audio.last_packet_time) < 0.25
                self.osc.send_active(is_streaming_active)

                peak_db = self.audio.peak_db if is_streaming_active else -96.0
                rms_db = self.audio.rms_db if is_streaming_active else -96.0
                is_clipping = self.audio.is_clipping if is_streaming_active else False

                # Update OSC meter
                self.osc.send_meter(
                    peak_db=peak_db,
                    rms_db=rms_db,
                    is_clipping=is_clipping,
                )
                # Send connection status
                is_connected = (len(self.active_clients) + len(self.raw_tcp_clients)) > 0
                buffer_ms = (self.audio.samples_available / self.audio.sample_rate) * 1000.0
                rec_status = ""
                if self.is_recording_clip:
                    dur = time.time() - self._rec_start_time
                    rec_status = f"RECORDING CLIP ({dur:.1f}s)"
                self.osc.send_status(
                    is_connected=is_connected,
                    client_ip=self.connected_ip if is_connected else "0.0.0.0",
                    latency_ms=self.last_latency_ms,
                    buffer_ms=buffer_ms,
                    rec_status=rec_status,
                )
            except Exception:
                pass
            await asyncio.sleep(1.0) # 1 Hz UI telemetry so Max main-thread UI never steals time from jit.fill

    def print_terminal_banner(self, preferred_ip: str):
        scheme = "https" if self.use_https else "http"
        url = f"{scheme}://{preferred_ip}:{self.port}"
        local_url = f"{scheme}://localhost:{self.port}"

        # Generate ASCII QR Code in terminal
        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make(fit=True)
        f = io.StringIO()
        qr.print_ascii(out=f)
        qr_ascii = f.getvalue()

        print("\n" + "=" * 64)
        print("  LIVE AIR MIC -- Wireless Ableton Microphone Bridge")
        print("=" * 64)
        print(f"  Target Audio Device : {self.audio.device_info.get('name')}")
        print(f"  Sample Rate         : {self.audio.sample_rate} Hz (Block size: {self.audio.block_size})")
        print(f"  OSC to Max for Live : 127.0.0.1:{self.osc.m4l_port}")
        print(f"  OSC from M4L        : 127.0.0.1:{self.osc.listen_port}")
        print("-" * 64)
        print(f"  Local Mobile URL    : \033[1;32m{url}\033[0m")
        print(f"  Macbook Localhost   : {local_url}")
        print("-" * 64)
        print("  Scan this QR Code with your phone camera to connect:")
        print(qr_ascii)
        print("=" * 64 + "\n")

    def run(self):
        # 1. Start audio output stream
        self.audio.start()

        # 2. Start OSC receiver
        self.osc.start_listener()

        # 3. Setup web application with no-cache headers so phone browser always runs latest JS/Worklet
        @web.middleware
        async def no_cache_middleware(request, handler):
            response = await handler(request)
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response

        app = web.Application(middlewares=[no_cache_middleware])

        async def handle_index(request):
            return web.FileResponse(self.web_dir / "index.html")

        app.router.add_get("/", handle_index)
        app.router.add_get("/index.html", handle_index)
        app.router.add_get("/ws", self.handle_ws)
        app.router.add_get("/api/status", self.handle_status_api)
        app.router.add_get("/api/fx", self.handle_fx_api)
        app.router.add_get("/api/usb_connect", self.handle_usb_connect_api)

        # Serve static web frontend
        app.router.add_static("/", path=str(self.web_dir), name="web")

        # SSL Configuration
        ssl_ctx = None
        if self.use_https:
            cert_file, key_file = ensure_ssl_certificates(self.certs_dir)
            ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_ctx.load_cert_chain(cert_file, key_file)

        local_ips = get_local_ip_addresses()
        preferred_ip = "127.0.0.1"
        for ip in local_ips:
            if not ip.startswith("127."):
                preferred_ip = ip
                break

        self.print_terminal_banner(preferred_ip)

        # Start telemetry loop task and raw TCP server on the event loop
        async def on_startup(app):
            self.loop = asyncio.get_running_loop()
            app["telemetry_task"] = asyncio.create_task(self.telemetry_loop())
            app["raw_tcp_server"] = await asyncio.start_server(
                self.handle_raw_tcp_client, "127.0.0.1", self.raw_tcp_port
            )
            logger.info(f"Raw Fast-Track TCP server listening on 127.0.0.1:{self.raw_tcp_port}")

        async def on_cleanup(app):
            app["telemetry_task"].cancel()
            if "raw_tcp_server" in app:
                app["raw_tcp_server"].close()
            self.audio.stop()
            self.osc.stop()

        app.on_startup.append(on_startup)
        app.on_cleanup.append(on_cleanup)

        web.run_app(
            app,
            host="0.0.0.0",
            port=self.port,
            ssl_context=ssl_ctx,
            access_log=None, # Clean logs for high throughput
        )

def main():
    parser = argparse.ArgumentParser(description="LiveAirMic High-Speed Wireless Mic Bridge for Ableton Live")
    parser.add_argument("--port", type=int, default=8765, help="Web/WebSocket port (default: 8765)")
    parser.add_argument("--rate", type=int, default=48000, help="Sample rate in Hz (default: 48000)")
    parser.add_argument("--block-size", type=int, default=128, help="Block size in frames (default: 128)")
    parser.add_argument("--buffer-ms", type=float, default=6.0, help="Target jitter buffer in ms (default: 6.0)")
    parser.add_argument("--no-ssl", action="store_true", help="Disable HTTPS/WSS (use HTTP for USB reverse tether)")
    args = parser.parse_args()

    server = LiveAirMicServer(
        port=args.port,
        sample_rate=args.rate,
        block_size=args.block_size,
        target_buffer_ms=args.buffer_ms,
        use_https=not args.no_ssl,
    )
    server.run()

if __name__ == "__main__":
    main()
