"""
Unit Tests for LiveAirMic Core Subsystems (Layer 1 Verification).
Tests AudioEngine ring buffer, wrap-around, underrun/overrun recovery,
sample-rate conversion, dBFS metering, X.509 SAN cert generation,
and Max for Live .amxd binary container generation.
"""

from pathlib import Path
import numpy as np
import pytest

from server.audio_engine import AudioEngine
from server.cert_gen import ensure_ssl_certificates, _cert_covers_ips, get_local_ip_addresses
from server.interfaces import AudioSink, DAWControlBridge, AudioFormatSpec
from server.osc_controller import OSCBridge
from m4l.build_amxd import generate_patcher, build_amxd_binary


@pytest.fixture
def audio_engine():
    """Create a pure-NumPy AudioEngine instance (zero external driver dependencies)."""
    return AudioEngine(
        sample_rate=48000,
        channels=2,
        block_size=128,
        target_buffer_ms=6.0,
    )


def test_interfaces_structural_conformance(audio_engine):
    """Verify AudioEngine and OSCBridge satisfy PEP 544 structural Protocols."""
    assert isinstance(audio_engine, AudioSink)
    osc = OSCBridge(m4l_port=19002, listen_port=19003)
    assert isinstance(osc, DAWControlBridge)
    spec = AudioFormatSpec(sample_rate=48000, channels=1, block_size=128)
    assert pytest.approx(spec.block_duration_ms, rel=1e-3) == 2.6667


def test_audio_engine_ring_buffer_read_write_and_wrap(audio_engine):
    """Verify ring buffer write, pre-buffer threshold, frame read, and circular wrap-around."""
    eng = audio_engine
    # Write 512 samples of a 0.5 amplitude signal (exceeds target_buffer_samples = 288)
    samples = np.full(512, int(0.5 * 32767), dtype=np.int16)
    eng.write_pcm_bytes(samples.tobytes(), is_int16=True)

    assert not eng.is_buffering
    assert eng.samples_available == 512
    assert eng.peak_db == pytest.approx(-6.0, abs=0.2)
    assert eng.rms_db == pytest.approx(-6.0, abs=0.2)

    # Read 128 frames from ring buffer
    out = np.zeros((128, 2), dtype=np.float32)
    eng.read_frames(out, 128)
    assert eng.samples_available == 384
    assert np.allclose(out[:, 0], 0.5, atol=1e-3)
    assert np.allclose(out[:, 1], 0.5, atol=1e-3)

    # Test wrap-around across buffer_capacity boundary
    eng.write_pos = eng.buffer_capacity - 64
    eng.read_pos = eng.write_pos
    eng.samples_available = 0
    eng.is_buffering = False

    ramp = np.arange(1, 129, dtype=np.float32) / 256.0
    eng.write_pcm_bytes(ramp.tobytes(), is_int16=False)
    assert eng.write_pos == 64
    assert eng.samples_available == 128

    eng.read_frames(out, 128)
    assert np.allclose(out[:, 0], ramp, atol=1e-5)
    assert eng.samples_available == 0


def test_audio_engine_underrun_and_overrun_recovery(audio_engine):
    """Verify graceful zero-padding on underrun and latency clamping on overrun."""
    eng = audio_engine
    # Trigger pre-buffer release then underrun
    samples = np.full(300, 10000, dtype=np.int16)
    eng.write_pcm_bytes(samples.tobytes(), is_int16=True)

    out = np.zeros((128, 2), dtype=np.float32)
    eng.read_frames(out, 128)  # 172 left
    eng.read_frames(out, 128)  # 44 left
    eng.read_frames(out, 128)  # Underrun! Drains 44, pads 84 with 0.0

    assert eng.is_buffering is True
    assert eng.samples_available == 0
    assert eng.underruns >= 1
    assert np.all(out[44:, :] == 0.0)

    # Overrun test: write more than max_buffer_samples and ensure buffer is clamped to low latency
    huge_chunk = np.full(eng.max_buffer_samples + 1024, 8000, dtype=np.int16)
    eng.write_pcm_bytes(huge_chunk.tobytes(), is_int16=True)
    assert eng.overruns >= 1
    assert eng.samples_available <= eng.max_buffer_samples


def test_audio_engine_sample_rate_conversion(audio_engine):
    """Verify automatic on-the-fly resampling when client sends 44.1kHz audio to 48kHz server."""
    eng = audio_engine
    samples_44k = np.full(441, 16000, dtype=np.int16)
    eng.write_pcm_bytes(samples_44k.tobytes(), is_int16=True, source_sample_rate=44100)
    assert eng.samples_available == 480


def test_ssl_certificate_generation_and_san_validation(tmp_path: Path):
    """Verify X.509 certificate generator creates valid SAN certificates covering local IPs."""
    cert_path, key_path = ensure_ssl_certificates(tmp_path)
    assert Path(cert_path).exists()
    assert Path(key_path).exists()

    local_ips = get_local_ip_addresses()
    assert _cert_covers_ips(Path(cert_path), local_ips) is True
    assert _cert_covers_ips(Path(cert_path), ["203.0.113.99"]) is False


def test_m4l_amxd_binary_and_portable_paths():
    """Verify M4L patcher has no hardcoded user paths and packs into valid .amxd binary header."""
    patcher = generate_patcher()
    raw_json = str(patcher)
    assert "/Users/" not in raw_json
    assert "node.script server_ctl.js @autostart 1" in raw_json
    assert "js clip_align.js" in raw_json

    amxd_bytes = build_amxd_binary(patcher)
    assert amxd_bytes[:4] == b"ampf"
    assert amxd_bytes[8:12] == b"aaaa"
    assert b"ptch" in amxd_bytes[:32]


def test_android_native_vocal_isolation_jni_contract():
    """Verify AAudio JNI vocal isolation & anti-feedback DSP structure, telemetry, and +0dB default gain."""
    jni_src = (Path(__file__).resolve().parent.parent / "android-native" / "jni" / "aaudio_mic.c").read_text()
    assert "ZeroLatencyVocalIsoState" in jni_src
    assert "vocal_iso_process_quantum" in jni_src
    assert "Java_com_liveairmic_pro_MainActivity_nativeSetVocalIso" in jni_src
    assert "Java_com_liveairmic_pro_MainActivity_nativeGetDspTimeUs" in jni_src
    assert "Java_com_liveairmic_pro_MainActivity_nativeGetFeedbackStats" in jni_src
    assert "int channelCounts[2] = { 2, 1 };" in jni_src

    java_src = (
        Path(__file__).resolve().parent.parent
        / "android-native"
        / "src"
        / "com"
        / "liveairmic"
        / "pro"
        / "MainActivity.java"
    ).read_text()
    assert "nativeSetVocalIso" in java_src
    assert "nativeGetDspTimeUs" in java_src
    assert "nativeGetFeedbackStats" in java_src
    assert "AFC: CLEAR" in java_src
    assert 'gainLabel.setText("MIC GAIN: +0dB")' in java_src


def test_audio_engine_feedback_detection_telemetry():
    """Verify AudioEngine PEM pre-whitened PAPR howl detector & AFC telemetry structure."""
    engine = AudioEngine(sample_rate=48000, channels=2, block_size=128, target_buffer_ms=6.0)
    # Feed a pure 2250 Hz sinusoid (bin 12 at 48kHz / 256) for 8 blocks to trigger howl lock
    t = np.arange(128, dtype=np.float32) / 48000.0
    for b in range(8):
        phase = (b * 128) / 48000.0
        tone = (0.4 * np.sin(2.0 * np.pi * 2250.0 * (t + phase)) * 32767.0).astype(np.int16)
        engine.write_pcm_bytes(tone.tobytes(), is_int16=True, source_sample_rate=48000)

    afc = engine.get_afc_telemetry()
    assert afc["enabled"] is True
    assert afc["state"] == "LOCKED"
    assert afc["active_notches"] >= 1
    assert any(abs(f - 2250.0) < 200.0 for f in afc["notch_freqs_hz"])


def test_open_source_license_and_notice_compliance():
    """Verify Apache-2.0 LICENSE, NOTICE, pyproject.toml, and SPDX headers protect author rights."""
    repo_root = Path(__file__).resolve().parent.parent

    license_file = repo_root / "LICENSE"
    notice_file = repo_root / "NOTICE"
    pyproject_file = repo_root / "pyproject.toml"
    readme_file = repo_root / "README.md"

    assert license_file.exists(), "Root LICENSE file must exist"
    assert notice_file.exists(), "Root NOTICE file must exist"

    license_text = license_file.read_text()
    assert "Apache License" in license_text
    assert "Version 2.0, January 2004" in license_text
    assert "3. Grant of Patent License." in license_text
    assert "6. Trademarks." in license_text
    assert "7. Disclaimer of Warranty." in license_text
    assert "8. Limitation of Liability." in license_text
    assert "Copyright 2026 Michael Lovci" in license_text

    notice_text = notice_file.read_text()
    assert "Copyright 2026 Michael Lovci" in notice_text
    assert "TRADEMARK & BRAND RESERVATION" in notice_text
    assert "REAL-TIME AUDIO, ACOUSTIC FEEDBACK & HARDWARE SAFETY NOTICE" in notice_text
    assert "THIRD-PARTY OPEN-SOURCE SOFTWARE NOTICES" in notice_text

    pyproject_text = pyproject_file.read_text()
    assert 'license = { file = "LICENSE" }' in pyproject_text
    assert "License :: OSI Approved :: Apache Software License" in pyproject_text

    readme_text = readme_file.read_text()
    assert "Apache License, Version 2.0" in readme_text
    assert "SPDX-License-Identifier: Apache-2.0" in readme_text

    # Verify SPDX headers on core source files
    for rel_path in [
        "server/bridge.py",
        "server/audio_engine.py",
        "server/osc_controller.py",
        "web/app.js",
        "web/audio-worklet.js",
        "m4l/server_ctl.js",
        "m4l/clip_align.js",
        "android-native/jni/aaudio_mic.c",
    ]:
        src_text = (repo_root / rel_path).read_text()
        assert "SPDX-License-Identifier: Apache-2.0" in src_text, f"Missing SPDX header in {rel_path}"


