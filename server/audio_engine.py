# Copyright 2026 Michael Lovci
# SPDX-License-Identifier: Apache-2.0
"""
Direct Max for Live (M4L) DSP & Ring Buffer Audio Engine for LiveAirMic.
Provides pure-Python/NumPy PCM ingestion, sample-rate conversion, circular ring buffering,
and real-time Peak/RMS dBFS metering without requiring BlackHole or external virtual audio drivers.
"""

import time
import math
import logging
import threading
import numpy as np
from typing import Optional

logger = logging.getLogger("LiveAirMic.AudioEngine")


class AudioEngine:
    """
    Zero-driver PCM conditioning, ring buffer, and dBFS metering engine.
    Feeds Ableton Live directly via Max for Live (`LiveAirMic.amxd` jit.release~)
    with zero external CoreAudio virtual driver dependencies.
    """

    def __init__(
        self,
        sample_rate: int = 48000,
        channels: int = 2,
        block_size: int = 128,
        target_buffer_ms: float = 6.0,
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.block_size = block_size
        self.target_buffer_samples = max(block_size, int((target_buffer_ms / 1000.0) * sample_rate))
        # Clamp maximum latency buildup to ~3x target jitter buffer (or at least 4 blocks)
        self.max_buffer_samples = max(self.target_buffer_samples * 3, block_size * 4)

        # Ring buffer for incoming PCM (Float32 in range [-1.0, 1.0])
        # Ring buffer capacity: ~500ms of audio
        self.buffer_capacity = sample_rate // 2
        self.ring_buffer = np.zeros(self.buffer_capacity, dtype=np.float32)
        self.write_pos = 0
        self.read_pos = 0
        self.samples_available = 0
        self.is_buffering = True
        self._lock = threading.Lock()

        # Metering metrics (in linear and dBFS)
        self.peak_db = -96.0
        self.rms_db = -96.0
        self.peak_linear = 0.0
        self.is_clipping = False
        self.last_meter_update = time.time()
        self.last_packet_time = 0.0

        # Telemetry stats
        self.underruns = 0
        self.overruns = 0
        self.total_frames_played = 0
        self.is_running = False
        self.device_info: dict = {"name": "Max for Live Direct (jit.release~)"}

        # Real-Time Anti-Feedback (AFC) & Vocal Isolation Telemetry
        self.afc_enabled: bool = True
        self.afc_papr: float = 1.0
        self.afc_candidate_freq_hz: float = 0.0
        self.afc_candidate_bin: int = 0
        self.afc_candidate_streak: int = 0
        self.afc_notch_freqs: list[float] = [0.0, 0.0, 0.0, 0.0]
        self.afc_notch_persistence: list[float] = [0.0, 0.0, 0.0, 0.0]
        self.afc_noise_floor_db: float = -62.0
        self.afc_iso_gain_db: float = 0.0
        self._afc_ar_prev: float = 0.0
        self._afc_hist = np.zeros(256, dtype=np.float32)

    def write_pcm_bytes(
        self,
        pcm_data: bytes,
        is_int16: bool = True,
        source_sample_rate: Optional[int] = None,
    ) -> None:
        """
        Ingest raw PCM bytes from the network socket into the ring buffer.
        Converts 16-bit integer PCM or 32-bit float PCM into normalized float32,
        and resamples if source_sample_rate differs from self.sample_rate.
        """
        if not pcm_data:
            return

        if is_int16:
            int16_arr = np.frombuffer(pcm_data, dtype=np.int16)
            float_arr = int16_arr.astype(np.float32) / 32768.0
        else:
            float_arr = np.frombuffer(pcm_data, dtype=np.float32)

        n_samples = len(float_arr)
        if n_samples == 0:
            return

        # Resample on-the-fly if client AudioContext is locked to a different hardware rate (e.g. 44.1kHz)
        if source_sample_rate and source_sample_rate != self.sample_rate and source_sample_rate > 0:
            target_len = max(1, int(round(n_samples * (self.sample_rate / source_sample_rate))))
            x_old = np.linspace(0.0, 1.0, n_samples, endpoint=False)
            x_new = np.linspace(0.0, 1.0, target_len, endpoint=False)
            float_arr = np.interp(x_new, x_old, float_arr).astype(np.float32)
            n_samples = len(float_arr)

        now = time.time()
        self.last_packet_time = now

        # Slowly decay peak hold before applying new peak
        dt = now - self.last_meter_update
        if dt > 0.05:
            self.peak_linear = max(0.0, self.peak_linear - 0.5 * dt)
            self.last_meter_update = now

        # Measure instantaneous peak of incoming chunk
        max_val = float(np.max(np.abs(float_arr)))
        if max_val > self.peak_linear:
            self.peak_linear = max_val

        # Compute RMS
        mean_square = float(np.mean(float_arr ** 2))
        rms_val = math.sqrt(max(1e-12, mean_square))
        self.rms_db = max(-96.0, 20.0 * math.log10(rms_val))
        self.peak_db = max(-96.0, 20.0 * math.log10(max(1e-6, self.peak_linear)))
        self.is_clipping = self.peak_linear >= 0.999

        # Update PEM Pre-Whitened Autoregressive Feedback Howl Detector & MCRA Noise Floor
        self._update_feedback_detector(float_arr)

        with self._lock:
            # Clamp latency buildup / clock drift if buffer exceeds max_buffer_samples
            if self.samples_available + n_samples > self.max_buffer_samples:
                target_keep = max(0, self.target_buffer_samples - n_samples)
                excess = max(0, self.samples_available - target_keep)
                if excess > 0:
                    self.read_pos = (self.read_pos + excess) % self.buffer_capacity
                    self.samples_available -= excess
                    self.overruns += 1
                if n_samples > self.max_buffer_samples:
                    float_arr = float_arr[-self.target_buffer_samples :]
                    n_samples = len(float_arr)
                    self.overruns += 1

            # Write data in 1 or 2 contiguous chunks
            first_chunk = min(n_samples, self.buffer_capacity - self.write_pos)
            self.ring_buffer[self.write_pos : self.write_pos + first_chunk] = float_arr[:first_chunk]

            second_chunk = n_samples - first_chunk
            if second_chunk > 0:
                self.ring_buffer[:second_chunk] = float_arr[first_chunk:]

            self.write_pos = (self.write_pos + n_samples) % self.buffer_capacity
            self.samples_available += n_samples

            if self.is_buffering and self.samples_available >= self.target_buffer_samples:
                self.is_buffering = False

    def read_frames(self, outdata: np.ndarray, frames: int) -> None:
        """
        Read `frames` samples from the circular ring buffer into `outdata` (shape: [frames, channels]).
        Pads with silence on underrun and re-engages pre-buffering.
        """
        with self._lock:
            if self.is_buffering:
                if self.samples_available < self.target_buffer_samples:
                    outdata.fill(0.0)
                    return
                self.is_buffering = False

            if self.samples_available < frames:
                available = self.samples_available
                if self.total_frames_played > 0 and (time.time() - self.last_packet_time) < 0.25:
                    self.underruns += 1
                self.is_buffering = True

                if available > 0:
                    first_chunk = min(available, self.buffer_capacity - self.read_pos)
                    samples_1 = self.ring_buffer[self.read_pos : self.read_pos + first_chunk]
                    second_chunk = available - first_chunk
                    if second_chunk > 0:
                        samples_2 = self.ring_buffer[:second_chunk]
                        mono_data = np.concatenate([samples_1, samples_2])
                    else:
                        mono_data = samples_1.copy()
                    self.read_pos = (self.read_pos + available) % self.buffer_capacity
                    self.samples_available = 0

                    outdata[:available, :] = mono_data[:, np.newaxis]
                    outdata[available:, :] = 0.0
                else:
                    outdata.fill(0.0)
                return

            first_chunk = min(frames, self.buffer_capacity - self.read_pos)
            samples_1 = self.ring_buffer[self.read_pos : self.read_pos + first_chunk]
            second_chunk = frames - first_chunk

            if second_chunk > 0:
                samples_2 = self.ring_buffer[:second_chunk]
                mono_data = np.concatenate([samples_1, samples_2])
            else:
                mono_data = samples_1.copy()

            self.read_pos = (self.read_pos + frames) % self.buffer_capacity
            self.samples_available -= frames
            self.total_frames_played += frames

        outdata[:, :] = mono_data[:, np.newaxis]

    def consume_samples(self, count: int) -> None:
        """
        Advance the ring buffer read pointer when a downstream consumer (such as
        direct M4L jit.release~ UDP streaming) dispatches a block of samples,
        keeping `samples_available` at the target jitter depth without false overruns.
        """
        with self._lock:
            if self.samples_available > self.target_buffer_samples:
                drain = min(count, self.samples_available - self.target_buffer_samples)
                if drain > 0:
                    self.read_pos = (self.read_pos + drain) % self.buffer_capacity
                    self.samples_available -= drain
                    self.total_frames_played += drain

    def start(self) -> None:
        """Mark the audio engine active."""
        self.is_running = True
        logger.info(
            f"AudioEngine active: Direct M4L stream (sample_rate={self.sample_rate}, block_size={self.block_size})"
        )

    def stop(self) -> None:
        """Stop the audio engine."""
        self.is_running = False
        logger.info("AudioEngine stopped.")

    def _update_feedback_detector(self, samples: np.ndarray) -> None:
        """
        Monitor PEM pre-whitened spectrum (> 1125 Hz, PAPR > 42.0, >= 5 consecutive blocks)
        and MCRA noise floor for real-time feedback detection telemetry.
        """
        n = len(samples)
        if n == 0:
            return

        # Track MCRA ambient noise floor
        if self.rms_db < -32.0:
            self.afc_noise_floor_db = 0.92 * self.afc_noise_floor_db + 0.08 * max(-80.0, self.rms_db)
        snr_db = self.rms_db - self.afc_noise_floor_db
        self.afc_iso_gain_db = 0.0 if snr_db > 4.5 else max(-15.0, (snr_db - 4.5) * 2.5)

        # Pre-whiten signal: y[n] = x[n] - 0.85 * x[n-1]
        prev = np.empty(n, dtype=np.float32)
        prev[0] = self._afc_ar_prev
        if n > 1:
            prev[1:] = samples[:-1]
        self._afc_ar_prev = float(samples[-1])
        pem = samples - 0.85 * prev

        if n >= 256:
            self._afc_hist[:] = pem[-256:]
        else:
            self._afc_hist[:-n] = self._afc_hist[n:]
            self._afc_hist[-n:] = pem

        # FFT power spectrum over 256-sample sliding window (bins 6..32 => >= 1125 Hz @ 48 kHz)
        spec_pwr = (np.abs(np.fft.rfft(self._afc_hist)) ** 2) / 256.0
        avg_pwr = float(np.mean(spec_pwr)) + 1e-10
        band = spec_pwr[6:33]
        best_rel = int(np.argmax(band))
        best_bin = 6 + best_rel
        max_bin_pwr = float(band[best_rel])

        papr = max_bin_pwr / avg_pwr
        self.afc_papr = round(float(papr), 1)
        self.afc_candidate_freq_hz = round((best_bin * self.sample_rate) / 256.0, 1)

        total_energy = float(np.sum(self._afc_hist ** 2))
        if papr > 42.0 and total_energy > 4e-4:
            if best_bin == self.afc_candidate_bin:
                self.afc_candidate_streak += 1
            else:
                self.afc_candidate_bin = best_bin
                self.afc_candidate_streak = 1

            if self.afc_candidate_streak >= 5:
                slot = 0
                min_pers = 1e9
                for k in range(4):
                    if abs(self.afc_notch_freqs[k] - self.afc_candidate_freq_hz) < 160.0 and self.afc_notch_persistence[k] > 0.1:
                        slot = k
                        break
                    if self.afc_notch_persistence[k] < min_pers:
                        min_pers = self.afc_notch_persistence[k]
                        slot = k
                self.afc_notch_freqs[slot] = self.afc_candidate_freq_hz
                self.afc_notch_persistence[slot] = 1.0
        else:
            self.afc_candidate_streak = 0

        for k in range(4):
            self.afc_notch_persistence[k] *= 0.96
            if self.afc_notch_persistence[k] < 0.15:
                self.afc_notch_persistence[k] = 0.0
                self.afc_notch_freqs[k] = 0.0

    def get_afc_telemetry(self) -> dict:
        """Return structured feedback detection & vocal isolation telemetry."""
        active_freqs = [round(f, 0) for f, p in zip(self.afc_notch_freqs, self.afc_notch_persistence) if p >= 0.15 and f > 0]
        if len(active_freqs) > 0:
            state = "LOCKED"
        elif self.afc_candidate_streak > 0 or self.afc_papr > 28.0:
            state = "TRACKING"
        else:
            state = "CLEAR"
        return {
            "enabled": self.afc_enabled,
            "state": state,
            "papr": round(self.afc_papr, 1),
            "papr_threshold": 42.0,
            "candidate_freq_hz": round(self.afc_candidate_freq_hz, 0),
            "candidate_streak": self.afc_candidate_streak,
            "active_notches": len(active_freqs),
            "notch_freqs_hz": active_freqs,
            "noise_floor_db": round(self.afc_noise_floor_db, 1),
            "iso_gain_db": round(self.afc_iso_gain_db, 1),
        }

    def get_telemetry(self) -> dict:
        """Return current real-time telemetry dictionary."""
        current_buffered_ms = (self.samples_available / self.sample_rate) * 1000.0
        return {
            "device": self.device_info.get("name", "Max for Live Direct (jit.release~)"),
            "sample_rate": self.sample_rate,
            "block_size": self.block_size,
            "buffered_ms": round(current_buffered_ms, 2),
            "peak_db": round(self.peak_db, 1),
            "rms_db": round(self.rms_db, 1),
            "clipping": self.is_clipping,
            "underruns": self.underruns,
            "overruns": self.overruns,
            "afc": self.get_afc_telemetry(),
        }
