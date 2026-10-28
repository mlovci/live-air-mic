# Copyright 2026 Michael Lovci
# SPDX-License-Identifier: Apache-2.0
"""
OSC Controller for LiveAirMic.
Bridges telemetry, metering, and Ableton Live transport between Python and Max for Live (M4L).
Uses python-osc with non-blocking UDP sockets.
"""

import time
import logging
from typing import Callable, Optional
from pythonosc import udp_client, dispatcher, osc_server
import threading

logger = logging.getLogger("LiveAirMic.OSC")

class OSCBridge:
    def __init__(
        self,
        m4l_host: str = "127.0.0.1",
        m4l_port: int = 9002,   # Python -> Max for Live
        listen_port: int = 9003, # Max for Live -> Python
    ):
        self.m4l_host = m4l_host
        self.m4l_port = m4l_port
        self.listen_port = listen_port

        self.client: Optional[udp_client.SimpleUDPClient] = None
        self.default_client: Optional[udp_client.SimpleUDPClient] = None
        self.dynamic_clients: dict[int, tuple[udp_client.SimpleUDPClient, float]] = {}
        self.server: Optional[osc_server.ThreadingOSCUDPServer] = None
        self.server_thread: Optional[threading.Thread] = None

        # Callbacks triggered when M4L sends messages
        self.on_transport_update: Optional[Callable[[bool, bool, float, float], None]] = None
        self.on_arm_update: Optional[Callable[[bool], None]] = None
        self.on_m4l_heartbeat: Optional[Callable[[], None]] = None
        self.on_rec_toggle: Optional[Callable[[bool], None]] = None

        self._setup_client()

    def _setup_client(self):
        try:
            self.default_client = udp_client.SimpleUDPClient(self.m4l_host, 9002)
            self.client = self.default_client
            self.dynamic_clients[9002] = (self.default_client, time.time())
            logger.info(f"OSC client targeting M4L at {self.m4l_host}:{self.m4l_port}")
        except Exception as e:
            logger.error(f"Failed to initialize OSC client: {e}")

    def _send_osc(self, address: str, arg):
        if self.client:
            try:
                self.client.send_message(address, arg)
            except Exception:
                pass

    def start_listener(self):
        """Start listening for incoming OSC from Max for Live."""
        disp = dispatcher.Dispatcher()
        disp.map("/live/transport", self._handle_transport)
        disp.map("/live/arm", self._handle_arm)
        disp.map("/live/heartbeat", self._handle_heartbeat)
        disp.map("/live/rec_toggle", self._handle_rec_toggle)
        disp.map("/live/port", self._handle_port)

        try:
            self.server = osc_server.ThreadingOSCUDPServer(("127.0.0.1", self.listen_port), disp)
            self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.server_thread.start()
            logger.info(f"OSC server listening for M4L on 127.0.0.1:{self.listen_port}")
        except Exception as e:
            logger.error(f"Failed to start OSC server: {e}")

    def stop(self):
        """Stop the OSC server."""
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception as e:
                logger.error(f"Error shutting down OSC server: {e}")
            self.server = None
        logger.info("OSC bridge stopped.")

    def _handle_transport(self, address, is_playing, is_recording, tempo, beat):
        """Called when Ableton Live transport changes."""
        if self.on_transport_update:
            self.on_transport_update(bool(is_playing), bool(is_recording), float(tempo), float(beat))

    def _handle_arm(self, address, is_armed):
        """Called when Ableton track arm status changes."""
        if self.on_arm_update:
            self.on_arm_update(bool(is_armed))

    def _handle_heartbeat(self, address, *args):
        if self.on_m4l_heartbeat:
            self.on_m4l_heartbeat()

    def _handle_rec_toggle(self, address, state):
        if self.on_rec_toggle:
            self.on_rec_toggle(bool(state))

    def _handle_port(self, address, port_num):
        try:
            new_port = int(port_num)
            if new_port > 0:
                now = time.time()
                # Ignore fallback 9002 pings if an active dynamic port (>9002) is registered
                if new_port == 9002 and self.m4l_port > 9002:
                    _, last_dyn = self.dynamic_clients.get(self.m4l_port, (None, 0.0))
                    if (now - last_dyn) < 3.0:
                        return
                if new_port not in self.dynamic_clients:
                    cli = udp_client.SimpleUDPClient(self.m4l_host, new_port)
                    self.dynamic_clients[new_port] = (cli, now)
                    self.m4l_port = new_port
                    self.client = cli
                    logger.info(f"Registered active M4L UDP receiver port {self.m4l_host}:{new_port}")
                else:
                    cli, _ = self.dynamic_clients[new_port]
                    self.dynamic_clients[new_port] = (cli, now)
                    self.m4l_port = new_port
                    self.client = cli
        except Exception as e:
            logger.error(f"Error updating M4L port: {e}")

    def send_meter(self, peak_db: float, rms_db: float, is_clipping: bool):
        """Send live audio metering to Max for Live."""
        try:
            meter_str = f"Mic: {peak_db:.1f} dB Peak | {rms_db:.1f} dB RMS"
            self._send_osc("/airmic/meter_text", meter_str.split())
        except Exception:
            pass

    def send_status(self, is_connected: bool, client_ip: str, latency_ms: float, buffer_ms: float, rec_status: str = ""):
        """Send compact Green/Red connection status and stream telemetry to Max for Live."""
        try:
            if is_connected:
                status_str = "● ONLINE"
                lat_str = f"Latency: {latency_ms:.1f} ms"
            else:
                status_str = "● OFFLINE"
                lat_str = "Latency: -- ms"
            self._send_osc("/airmic/status_text", status_str.split())
            self._send_osc("/airmic/latency_text", lat_str.split())
            self._send_osc("/airmic/fx_ctl", ["fx_ctl", "status_led", 1.0 if is_connected else 0.0])
        except Exception:
            pass

    def send_import_clip(self, wav_path: str):
        """Instruct M4L to import a recorded WAV clip into the track's clip slot."""
        try:
            self._send_osc("/airmic/import_clip", str(wav_path))
        except Exception:
            pass

    def send_remote_rec_trigger(self, state: bool):
        """Send remote record toggle triggered from phone to Max for Live."""
        try:
            self._send_osc("/airmic/remote_rec", [1 if state else 0])
        except Exception:
            pass

    def send_pcm_block(self, samples: list[float]):
        """Stream a 256-sample Float32 PCM block directly into M4L jit.fill -> jit.release~."""
        try:
            self._send_osc("/airmic/pcm", samples)
        except Exception:
            pass

    def send_playhead(self, playhead: int):
        """Synchronize M4L count~ playhead position in buffer~ airmic_ring."""
        try:
            self._send_osc("/airmic/playhead", int(playhead))
        except Exception:
            pass

    def send_active(self, active: bool):
        """Gate M4L direct audio output on/off when stream starts or stops."""
        try:
            self._send_osc("/airmic/active", 1 if active else 0)
        except Exception:
            pass

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bridge = OSCBridge()
    bridge.start_listener()
    print("Testing OSC Bridge... sending meter packet to M4L port 9002.")
    bridge.send_meter(-12.4, -18.2, False)
    bridge.send_status(True, "127.0.0.1", 2.6, 6.0)
    time.sleep(0.5)
    bridge.stop()
    print("OSC Bridge test complete.")
