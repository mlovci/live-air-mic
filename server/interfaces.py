"""
Protocol & Pipeline Interfaces for LiveAirMic.
Defines runtime-checkable structural contracts (PEP 544 Protocols) for
Audio Sources, DSP Conditioners, Audio Sinks, and DAW Control Surfaces.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable, Optional
import numpy as np


@dataclass(frozen=True)
class AudioFormatSpec:
    """Immutable specification of a real-time PCM audio stream."""
    sample_rate: int = 48000
    channels: int = 1
    block_size: int = 128
    is_int16: bool = True

    @property
    def block_duration_ms(self) -> float:
        return (self.block_size / float(self.sample_rate)) * 1000.0


@dataclass
class FeedbackDetectionTelemetry:
    """Real-time telemetry from the PEM Autoregressive & Q=45 Notch Anti-Feedback engine."""
    enabled: bool = True
    state: str = "CLEAR"  # "CLEAR", "TRACKING", or "LOCKED"
    papr: float = 0.0
    papr_threshold: float = 42.0
    candidate_freq_hz: float = 0.0
    candidate_streak: int = 0
    active_notches: int = 0
    notch_freqs_hz: list[float] | None = None
    noise_floor_db: float = -60.0
    iso_gain_db: float = 0.0


@dataclass
class StreamTelemetry:
    """Snapshot of real-time audio engine and transport metrics."""
    device_name: str
    sample_rate: int
    block_size: int
    buffered_ms: float
    peak_db: float
    rms_db: float
    clipping: bool
    underruns: int
    overruns: int
    connected_clients: int = 0
    connected_device: str = "None"
    connected_ip: str = ""
    latency_ms: float = 0.0
    afc: Optional[FeedbackDetectionTelemetry] = None


@runtime_checkable
class AudioSink(Protocol):
    """Contract for any destination receiving real-time PCM audio frames."""

    def start(self) -> None:
        """Initialize and start the audio sink."""
        ...

    def stop(self) -> None:
        """Stop and release audio sink resources."""
        ...

    def write_pcm_bytes(
        self,
        pcm_data: bytes,
        is_int16: bool = True,
        source_sample_rate: Optional[int] = None,
    ) -> None:
        """Ingest raw PCM bytes into the sink."""
        ...


@runtime_checkable
class DSPConditioner(Protocol):
    """Contract for zero-latency in-place or buffer-to-buffer audio conditioning."""

    def process(self, samples: np.ndarray, sample_rate: int) -> np.ndarray:
        """Transform a normalized float32 sample array in [-1.0, 1.0]."""
        ...


@runtime_checkable
class DAWControlBridge(Protocol):
    """Contract for bidirectional DAW telemetry, transport, and FX automation."""

    def start_listener(self) -> None:
        """Start listening for incoming DAW state updates."""
        ...

    def stop(self) -> None:
        """Stop listener and release transport sockets."""
        ...

    def send_meter(self, peak_db: float, rms_db: float, is_clipping: bool) -> None:
        """Push real-time dBFS peak and RMS metering to the DAW UI."""
        ...

    def send_status(
        self,
        is_connected: bool,
        client_ip: str,
        latency_ms: float,
        buffer_ms: float,
        rec_status: str = "",
    ) -> None:
        """Push connection state and latency diagnostics to the DAW UI."""
        ...

    def send_remote_rec_trigger(self, state: bool) -> None:
        """Trigger or stop DAW recording from a remote performer device."""
        ...
