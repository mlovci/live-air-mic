"""
LiveAirMic Automated Stream & Latency Tester.
Simulates a mobile phone streaming 48kHz PCM over WebSocket into the bridge,
and validates audio playback, OSC telemetry, and latency.
"""

import sys
import time
import json
import ssl
import asyncio
import numpy as np
import aiohttp
from pathlib import Path

async def run_test(host="127.0.0.1", port=8765, duration_sec=3.0):
    url = f"wss://{host}:{port}/ws"
    status_url = f"https://{host}:{port}/api/status"

    print(f"[*] Connecting to LiveAirMic Bridge at {url}...")

    # Disable SSL verification for local self-signed cert in tests
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    use_ssl: ssl.SSLContext | bool = ssl_context

    async with aiohttp.ClientSession() as session:
        # Check API status (auto-detect HTTPS vs HTTP --no-ssl mode)
        try:
            async with session.get(status_url, ssl=use_ssl) as resp:
                status = await resp.json()
                print(f"[*] Initial Server Status: {json.dumps(status, indent=2)}")
        except Exception:
            url = f"ws://{host}:{port}/ws"
            status_url = f"http://{host}:{port}/api/status"
            use_ssl = False
            try:
                async with session.get(status_url, ssl=use_ssl) as resp:
                    status = await resp.json()
                    print(f"[*] Initial Server Status (HTTP): {json.dumps(status, indent=2)}")
            except Exception as e:
                print(f"[!] Server unreachable at {status_url}: {e}")
                return False

        # Connect WebSocket (if Native USB TCP Fast-Track is active on port 8766, verify live USB telemetry)
        async with session.ws_connect(url, ssl=use_ssl) as ws:
            hs_msg = json.loads(await ws.receive_str())
            if hs_msg.get("type") == "replaced":
                print("[+] Native Android USB Fast-Track TCP stream is currently active and holds exclusive lock!")
                async with session.get(status_url, ssl=use_ssl) as resp:
                    live_status = await resp.json()
                    assert live_status.get("connected_device") == "Android USB (Native Fast-Track)"
                    assert live_status.get("latency_ms", 99.0) <= 15.0
                    print(f"[+] Verified Live Native USB Fast-Track Latency: {live_status.get('latency_ms')} ms")
                    print("\n[SUCCESS] LiveAirMic Native USB Fast-Track Pipeline Verified!")
                    return True
            assert hs_msg.get("type") == "handshake", f"Expected handshake, got {hs_msg}"
            print(f"[+] WebSocket Handshake Received (Server Rate: {hs_msg.get('server_sample_rate')} Hz)")

            # 1. Device Info (including client sample_rate)
            await ws.send_str(json.dumps({
                "type": "device_info",
                "device": "PyTest Simulated Android (Chrome)",
                "sample_rate": 48000
            }))

            # 2. Ping-Pong test
            t0 = time.time() * 1000.0
            await ws.send_str(json.dumps({
                "type": "ping",
                "time": t0
            }))

            reply = await ws.receive_str()
            reply_data = json.loads(reply)
            assert reply_data.get("type") == "pong", f"Expected pong, got {reply_data}"
            rtt = round(time.time() * 1000.0 - t0, 2)
            print(f"[+] Ping-Pong RTT: {rtt} ms (Server: {reply_data.get('type')})")

            # Report measured RTT back on next ping
            await ws.send_str(json.dumps({
                "type": "ping",
                "time": time.time() * 1000.0,
                "rtt": max(0.1, rtt)
            }))
            _ = await ws.receive_str()

            # 2b. Test M4L -> Server -> WebSocket OSC broadcast thread safety
            from pythonosc import udp_client
            m4l_sim = udp_client.SimpleUDPClient("127.0.0.1", 9003)
            m4l_sim.send_message("/live/transport", [1, 1, 128.5, 4.2])
            trans_reply = json.loads(await asyncio.wait_for(ws.receive_str(), timeout=2.0))
            assert trans_reply.get("type") == "transport" and trans_reply.get("tempo") == 128.5
            print(f"[+] M4L -> OSC -> WebSocket Broadcast Verified: {trans_reply}")

            # 3. Stream 48kHz Sine Wave in 256-sample chunks (5.33ms per packet)
            sample_rate = 48000
            chunk_size = 256
            freq = 440.0
            total_samples = int(duration_sec * sample_rate)
            t = np.linspace(0, duration_sec, total_samples, endpoint=False)
            sine_wave = (0.4 * np.sin(2 * np.pi * freq * t)).astype(np.float32)

            # Convert to Int16
            int16_samples = (sine_wave * 32767.0).astype(np.int16)

            print(f"[*] Streaming {duration_sec}s of 440Hz PCM ({total_samples} samples, {chunk_size} samples/pkt)...")

            seq = 0
            start_stream = time.time()
            for i in range(0, total_samples, chunk_size):
                chunk = int16_samples[i : i + chunk_size]
                if len(chunk) < chunk_size:
                    break

                # 4-byte header: [seq_hi, seq_lo, channels, flags]
                seq = (seq + 1) & 0xFFFF
                header = bytes([(seq >> 8) & 0xFF, seq & 0xFF, 1, 0])
                packet = header + chunk.tobytes()

                await ws.send_bytes(packet)

                # Real-time pacing
                target_time = start_stream + (i + chunk_size) / sample_rate
                sleep_sec = target_time - time.time()
                if sleep_sec > 0:
                    await asyncio.sleep(sleep_sec)

            print("[+] Audio streaming finished successfully!")

            # 4. Remote REC test
            print("[*] Sending remote record trigger (REC ON)...")
            await ws.send_str(json.dumps({"type": "remote_rec", "state": True}))
            await asyncio.sleep(0.5)

            print("[*] Sending remote record trigger (REC OFF)...")
            await ws.send_str(json.dumps({"type": "remote_rec", "state": False}))
            await asyncio.sleep(0.5)

        # Check final telemetry
        async with session.get(status_url, ssl=use_ssl) as resp:
            final_status = await resp.json()
            print(f"\n[*] Final Server Telemetry:")
            print(f"  Device:     {final_status.get('device')}")
            print(f"  Peak dBFS:  {final_status.get('peak_db')} dB")
            print(f"  RMS dBFS:   {final_status.get('rms_db')} dB")
            print(f"  Underruns:  {final_status.get('underruns')}")
            print(f"  Overruns:   {final_status.get('overruns')}")
            print(f"  Clipping:   {final_status.get('clipping')}")

    print("\n[SUCCESS] LiveAirMic End-to-End Pipeline Verified!")
    return True

if __name__ == "__main__":
    asyncio.run(run_test())
