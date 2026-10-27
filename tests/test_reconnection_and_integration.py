"""
Reconnection & End-to-End Integration Test Suite (Layer 2 Verification).
Covers every subsystem integration and disconnect/reconnect edge case:
1. Raw Fast-Track TCP stream (Android Native USB port 8766):
   - Connect -> stream PCM (including fragmented TCP reads) -> abrupt disconnect -> immediate reconnect -> stream PCM
   - Stale/half-open TCP socket timeout cleanup (verifying a zombie socket never blocks WebSocket or new TCP connections)
   - Native TCP preemption of existing browser WebSocket connections ("replaced" notification)
2. Browser WebSocket stream (/ws):
   - Connect -> handshake -> ping/pong RTT -> stream PCM -> disconnect -> reconnect -> verify audio engine & telemetry
   - Duplicate browser tab preemption ("replaced" notification)
3. Bidirectional Max for Live OSC Bridge (UDP 9003 <-> Python <-> M4L Dynamic Port):
   - Dynamic M4L receiver port registration (/live/port) and reception of 128-sample Float32 /airmic/pcm blocks
   - M4L -> OSC -> Server -> WebSocket broadcast for /live/transport and /live/arm
   - Remote REC trigger (/airmic/remote_rec) and Direct 48kHz WAV Clip Recorder lifecycle + /airmic/import_clip
4. Live FX & Multi-Track Mixer HTTP/OSC control API (/api/fx).
"""

import asyncio
import time
import wave
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch
import numpy as np
from aiohttp import web
from aiohttp.test_utils import TestServer, TestClient
from pythonosc import dispatcher, osc_server, udp_client

from server.bridge import LiveAirMicServer


@asynccontextmanager
async def create_live_bridge_env(tmp_recordings_dir: Path | None = None):
    """Spin up an isolated LiveAirMicServer with ephemeral ports for integration testing."""
    srv = LiveAirMicServer(
        port=0,
        sample_rate=48000,
        block_size=128,
        target_buffer_ms=6.0,
        m4l_osc_in=19102,
        m4l_osc_out=0,  # Bind ephemeral OSC listen port
        use_https=False,
    )
    if tmp_recordings_dir is not None:
        srv.recordings_dir = tmp_recordings_dir
        srv.recordings_dir.mkdir(parents=True, exist_ok=True)

    srv.raw_tcp_port = 0  # Ephemeral TCP port
    srv.loop = asyncio.get_running_loop()
    srv.osc.start_listener()
    actual_osc_listen_port = srv.osc.server.server_address[1]
    srv.osc.listen_port = actual_osc_listen_port

    app = web.Application()
    app.router.add_get("/ws", srv.handle_ws)
    app.router.add_get("/api/status", srv.handle_status_api)
    app.router.add_get("/api/fx", srv.handle_fx_api)

    tcp_server = await asyncio.start_server(
        srv.handle_raw_tcp_client, "127.0.0.1", 0
    )
    tcp_port = tcp_server.sockets[0].getsockname()[1]
    srv.raw_tcp_port = tcp_port

    test_server = TestServer(app)
    client = TestClient(test_server)
    await client.start_server()

    try:
        yield srv, client, tcp_port, actual_osc_listen_port
    finally:
        await client.close()
        tcp_server.close()
        await tcp_server.wait_closed()
        srv.osc.stop()


def test_websocket_disconnect_and_immediate_reconnect():
    """
    Regression test: Verify that when a WebSocket client disconnects and reconnects,
    the server cleans up the old client, accepts the new connection, sends a fresh
    handshake, and continues ingesting PCM audio without error.
    """
    async def _run():
        async with create_live_bridge_env() as (srv, client, _, _):
            ws1 = await client.ws_connect("/ws")
            hs1 = await ws1.receive_json()
            assert hs1["type"] == "handshake"

            # Ping/Pong RTT measurement
            t0 = time.time() * 1000.0
            await ws1.send_json({"type": "ping", "time": t0, "rtt": 3.4})
            pong = await ws1.receive_json()
            assert pong["type"] == "pong"
            assert srv.last_latency_ms == 3.4

            # Stream 4 chunks of 128-sample Int16 PCM
            sine_chunk = (np.sin(np.linspace(0, np.pi, 128)) * 16000).astype(np.int16).tobytes()
            header = bytes([0, 1, 1, 0])
            for _ in range(4):
                await ws1.send_bytes(header + sine_chunk)

            await asyncio.sleep(0.05)
            st1 = await (await client.get("/api/status")).json()
            assert st1["connected_clients"] == 1
            assert srv.audio.samples_available == srv.audio.target_buffer_samples
            assert srv.audio.total_frames_played == 512 - srv.audio.target_buffer_samples

            # Abrupt disconnect
            await ws1.close()
            await asyncio.sleep(0.05)
            st_disc = await (await client.get("/api/status")).json()
            assert st_disc["connected_clients"] == 0
            assert st_disc["connected_device"] == "None"

            # Immediate reconnect
            srv.audio.samples_available = 0
            ws2 = await client.ws_connect("/ws")
            hs2 = await ws2.receive_json()
            assert hs2["type"] == "handshake"
            await ws2.send_json({"type": "device_info", "device": "Reconnected Android", "sample_rate": 48000})

            for _ in range(4):
                await ws2.send_bytes(header + sine_chunk)

            await asyncio.sleep(0.05)
            st2 = await (await client.get("/api/status")).json()
            assert st2["connected_clients"] == 1
            assert st2["connected_device"] == "Reconnected Android"
            assert srv.audio.samples_available == srv.audio.target_buffer_samples
            assert srv.audio.total_frames_played == 2 * (512 - srv.audio.target_buffer_samples)

            await ws2.close()

    asyncio.run(_run())


def test_raw_tcp_usb_disconnect_reconnect_and_fragmentation():
    """
    Regression test: Verify Android Native Fast-Track TCP stream (port 8766)
    handles arbitrary TCP packet fragmentation (e.g., 100-byte + 156-byte splits),
    disconnects cleanly when USB is unplugged, and immediately reconnects when re-plugged.
    """
    async def _run():
        async with create_live_bridge_env() as (srv, client, tcp_port, _):
            pcm_block = (np.full(128, 12000, dtype=np.int16)).tobytes()  # 256 bytes

            # 1. Connect native TCP client #1 and send fragmented 256-byte blocks (100B + 156B)
            _, writer1 = await asyncio.open_connection("127.0.0.1", tcp_port)
            writer1.write(pcm_block[:100])
            await writer1.drain()
            await asyncio.sleep(0.01)
            writer1.write(pcm_block[100:] + pcm_block)
            await writer1.drain()
            await asyncio.sleep(0.05)

            st1 = await (await client.get("/api/status")).json()
            assert st1["connected_clients"] == 1
            assert "USB Native" in st1["connected_ip"]
            assert srv.audio.samples_available == 256

            # 2. Simulate USB cable unplug (close TCP stream)
            writer1.close()
            await writer1.wait_closed()
            await asyncio.sleep(0.05)

            st_disc = await (await client.get("/api/status")).json()
            assert st_disc["connected_clients"] == 0

            # 3. Simulate USB cable re-plug (immediate new TCP connection)
            _, writer2 = await asyncio.open_connection("127.0.0.1", tcp_port)
            for _ in range(2):
                writer2.write(pcm_block)
            await writer2.drain()
            await asyncio.sleep(0.05)

            st2 = await (await client.get("/api/status")).json()
            assert st2["connected_clients"] == 1
            assert srv.audio.samples_available == srv.audio.target_buffer_samples
            assert srv.audio.total_frames_played == 512 - srv.audio.target_buffer_samples

            writer2.close()
            await writer2.wait_closed()

    asyncio.run(_run())


def test_half_open_tcp_socket_does_not_block_new_connections():
    """
    Regression test: If a USB cable is yanked without sending a TCP FIN packet,
    verify that:
      a) An idle half-open TCP socket automatically times out and releases its lock
         within 2.5s so browser WebSocket clients are no longer rejected with 'replaced'.
    """
    async def _run():
        async with create_live_bridge_env() as (srv, client, tcp_port, _):
            _, writer_stale = await asyncio.open_connection("127.0.0.1", tcp_port)
            await asyncio.sleep(0.05)
            assert len(srv.raw_tcp_clients) == 1

            # Wait for the 2.5s server read timeout to evict the silent zombie connection
            await asyncio.sleep(2.65)
            assert len(srv.raw_tcp_clients) == 0

            # Verify a browser WebSocket client can connect freely without being rejected
            ws = await client.ws_connect("/ws")
            hs = await ws.receive_json()
            assert hs["type"] == "handshake"
            await ws.close()
            writer_stale.close()

    asyncio.run(_run())


def test_duplicate_tab_and_native_tcp_preemption():
    """
    Verify single-stream exclusivity:
    1. Opening a second browser WebSocket tab sends {"type": "replaced"} to the first tab.
    2. Connecting the Native USB Fast-Track TCP client sends {"type": "replaced"} to the browser tab
       and rejects new browser tabs while Native USB is actively streaming.
    """
    async def _run():
        async with create_live_bridge_env() as (_, client, tcp_port, _):
            # Tab 1 connects
            ws1 = await client.ws_connect("/ws")
            assert (await ws1.receive_json())["type"] == "handshake"

            # Tab 2 connects -> Tab 1 receives "replaced"
            ws2 = await client.ws_connect("/ws")
            assert (await ws2.receive_json())["type"] == "handshake"
            replaced_msg = await ws1.receive_json()
            assert replaced_msg["type"] == "replaced"

            # Native TCP connects -> Tab 2 receives "replaced"
            _, writer = await asyncio.open_connection("127.0.0.1", tcp_port)
            replaced_msg_2 = await ws2.receive_json()
            assert replaced_msg_2["type"] == "replaced"

            # Tab 3 attempts to connect while Native TCP is active -> immediately receives "replaced"
            ws3 = await client.ws_connect("/ws")
            replaced_msg_3 = await ws3.receive_json()
            assert replaced_msg_3["type"] == "replaced"

            writer.close()
            await writer.wait_closed()
            await ws1.close()
            await ws2.close()
            await ws3.close()

    asyncio.run(_run())


def test_m4l_osc_bidirectional_telemetry_and_pcm_stream():
    """
    Verify full bidirectional OSC integration with Max for Live:
    1. M4L registers a dynamic UDP port via `/live/port <port>`.
    2. Server streams 128-sample Float32 `/airmic/pcm` blocks to that dynamic port.
    3. M4L sends `/live/transport` and `/live/arm` to Server -> Server broadcasts to WebSocket client.
    """
    async def _run():
        received_pcm_blocks = []
        received_fx_cmds = []

        disp = dispatcher.Dispatcher()
        disp.map("/airmic/pcm", lambda addr, *args: received_pcm_blocks.append(args))
        disp.map("/airmic/fx_ctl", lambda addr, *args: received_fx_cmds.append(args))

        m4l_mock_server = osc_server.ThreadingOSCUDPServer(("127.0.0.1", 0), disp)
        m4l_dyn_port = m4l_mock_server.server_address[1]
        import threading
        t = threading.Thread(target=m4l_mock_server.serve_forever, daemon=True)
        t.start()

        try:
            async with create_live_bridge_env() as (_, client, _, osc_listen_port):
                ws = await client.ws_connect("/ws")
                assert (await ws.receive_json())["type"] == "handshake"

                # 1. M4L registers its dynamic UDP port with the Python bridge
                m4l_sender = udp_client.SimpleUDPClient("127.0.0.1", osc_listen_port)
                m4l_sender.send_message("/live/port", m4l_dyn_port)
                await asyncio.sleep(0.05)

                # 2. Send 128-sample Int16 PCM over WebSocket -> verify M4L receives 128 Float32 samples via OSC
                pcm_128 = (np.full(128, 16384, dtype=np.int16)).tobytes()
                await ws.send_bytes(bytes([0, 1, 1, 0]) + pcm_128)
                await asyncio.sleep(0.05)

                assert len(received_pcm_blocks) == 1
                assert len(received_pcm_blocks[0]) == 128
                assert abs(received_pcm_blocks[0][0] - 0.5) < 1e-3

                # 3. M4L sends transport and arm updates -> verify WebSocket client receives broadcasts
                m4l_sender.send_message("/live/transport", [1, 1, 126.0, 2.5])
                trans_msg = await asyncio.wait_for(ws.receive_json(), timeout=1.5)
                assert trans_msg["type"] == "transport"
                assert trans_msg["is_playing"] is True
                assert trans_msg["is_recording"] is True
                assert trans_msg["tempo"] == 126.0

                m4l_sender.send_message("/live/arm", [1])
                arm_msg = await asyncio.wait_for(ws.receive_json(), timeout=1.5)
                assert arm_msg == {"type": "arm", "is_armed": True}

                # 4. Trigger FX API -> verify M4L receives /airmic/fx_ctl OSC message
                resp = await client.get("/api/fx?cmd=space_mix&val=0.75")
                assert resp.status == 200
                await asyncio.sleep(0.05)
                assert len(received_fx_cmds) >= 1
                assert received_fx_cmds[-1][1] == "space_mix"
                assert abs(received_fx_cmds[-1][2] - 0.75) < 1e-4

                await ws.close()
        finally:
            m4l_mock_server.shutdown()
            m4l_mock_server.server_close()

    asyncio.run(_run())


def test_direct_wav_clip_recorder_lifecycle(tmp_path: Path):
    """
    Verify that triggering remote recording (from phone or M4L) records incoming
    48kHz 16-bit PCM into a valid .wav file and dispatches clip import upon completion.
    """
    async def _run():
        async with create_live_bridge_env(tmp_recordings_dir=tmp_path) as (srv, client, _, _):
            with patch.object(srv, "_import_wav_to_ableton") as mock_import:
                ws = await client.ws_connect("/ws")
                assert (await ws.receive_json())["type"] == "handshake"

                # Start recording via phone remote_rec command
                await ws.send_json({"type": "remote_rec", "state": True})
                await asyncio.sleep(0.05)
                assert srv.is_recording_clip is True

                # Stream 12,000 samples (0.25s @ 48kHz) in 128-sample chunks
                chunk = (np.sin(np.linspace(0, np.pi, 128)) * 12000).astype(np.int16).tobytes()
                header = bytes([0, 1, 1, 0])
                for _ in range(95):
                    await ws.send_bytes(header + chunk)

                # Wait >0.2s minimum clip duration threshold
                await asyncio.sleep(0.25)

                # Stop recording
                await ws.send_json({"type": "remote_rec", "state": False})
                await asyncio.sleep(0.05)
                assert srv.is_recording_clip is False

                wav_files = list(tmp_path.glob("LiveAirMic_*.wav"))
                assert len(wav_files) == 1
                with wave.open(str(wav_files[0]), "rb") as wf:
                    assert wf.getnchannels() == 1
                    assert wf.getsampwidth() == 2
                    assert wf.getframerate() == 48000
                    assert wf.getnframes() == 95 * 128

                mock_import.assert_called_once()
                await ws.close()

    asyncio.run(_run())
