/**
 * LiveAirMic Reggae Studio App Logic.
 * Handles WebAudio AudioWorklet pipeline, WebSocket binary PCM streaming,
 * compact horizontal 24-segment LED metering, traffic-light latency indicator,
 * real-time AFC feedback detector telemetry, Reggae/Dub FX macro synchronization,
 * and secondary Ableton Session Mixer view navigation.
 */

const state = {
  audioContext: null,
  mediaStream: null,
  workletNode: null,
  socket: null,
  isStreaming: false,
  isMuted: false,
  gainLinear: 1.0,
  chunkSize: 128,
  isStudioMode: true,
  packetSeq: 0,
  packetsSent: 0,
  wakeLock: null,
  isRecordingAbleton: false,
  pingInterval: null,
  lastPingSent: 0,
  lastRtt: 0,
  livePeak: 0.0,
  liveRms: 0.0,
  fx: {
    gateOn: true,
    tuneOn: true,
    echoOn: true,
    springOn: true,
    warmOn: true,
    afcOn: true,
    dryCut: false,
    echoRate: 0,
  },
  tracks: [
    { name: '1-Drums', color: '#fbbf24', vol: 85, mute: false, solo: false, arm: false },
    { name: '2-Bass', color: '#38bdf8', vol: 85, mute: false, solo: false, arm: false },
    { name: '3-LiveMic', color: '#34d399', vol: 85, mute: false, solo: false, arm: true },
    { name: '4-Lead Vocal', color: '#f43f5e', vol: 85, mute: false, solo: false, arm: false },
    { name: '5-Keys Skank', color: '#a78bfa', vol: 80, mute: false, solo: false, arm: false },
    { name: '6-Guitar Dub', color: '#fb923c', vol: 80, mute: false, solo: false, arm: false },
    { name: '7-Horns', color: '#2dd4bf', vol: 80, mute: false, solo: false, arm: false },
  ],
};

// DOM Elements
const statusBadge = document.getElementById('status-badge');
const statusText = document.getElementById('status-text');
const btnStream = document.getElementById('btn-stream');
const streamText = document.getElementById('stream-text');
const btnMute = document.getElementById('btn-mute');
const muteText = document.getElementById('mute-text');
const btnRecord = document.getElementById('btn-record');
const recordText = document.getElementById('record-text');
const sliderGain = document.getElementById('slider-gain');
const gainLabel = document.getElementById('gain-label');
const sliderBuffer = document.getElementById('slider-buffer');
const bufferLabel = document.getElementById('buffer-label');
const modeStudio = document.getElementById('mode-studio');
const modeSpeech = document.getElementById('mode-speech');
const dspModeLabel = document.getElementById('dsp-mode-label');

const transportTempo = document.getElementById('transport-tempo');
const transportBeat = document.getElementById('transport-beat');
const transportBadge = document.getElementById('transport-badge');

const clipLed = document.getElementById('clip-led');
const readoutPeak = document.getElementById('readout-peak');
const readoutRms = document.getElementById('readout-rms');
const telPing = document.getElementById('tel-ping');
const telRate = document.getElementById('tel-rate');
const telPackets = document.getElementById('tel-packets');
const meterContainer = document.getElementById('meter-container');

// AFC Monitor Elements
const afcStateBadge = document.getElementById('afc-state-badge');
const afcMetrics = document.getElementById('afc-metrics');
const afcNotchEls = [
  document.getElementById('afc-notch-0'),
  document.getElementById('afc-notch-1'),
  document.getElementById('afc-notch-2'),
  document.getElementById('afc-notch-3'),
];

// SPA Views
const btnOpenMixer = document.getElementById('btn-open-mixer');
const btnBackFx = document.getElementById('btn-back-fx');
const mixerTracksContainer = document.getElementById('mixer-tracks-container');

function switchToView(viewId) {
  document.querySelectorAll('.spa-view').forEach((view) => {
    const isTarget = view.id === viewId;
    view.classList.toggle('inactive', !isTarget);
    view.setAttribute('aria-hidden', String(!isTarget));
  });
  const activeView = document.getElementById(viewId);
  if (activeView) activeView.focus();
}

if (btnOpenMixer) {
  btnOpenMixer.addEventListener('click', () => switchToView('view-mixer'));
}
if (btnBackFx) {
  btnBackFx.addEventListener('click', () => switchToView('view-fx'));
}

// Build 24 Horizontal LED Segments
const TOTAL_SEGMENTS = 24;
const ledSegments = [];

function buildMeterSegments() {
  if (!meterContainer) return;
  meterContainer.innerHTML = '';
  for (let i = 0; i < TOTAL_SEGMENTS; i += 1) {
    const seg = document.createElement('div');
    seg.className = 'meter-segment';
    if (i < 15) {
      seg.dataset.color = 'green';
    } else if (i < 19) {
      seg.dataset.color = 'yellow';
    } else if (i < 22) {
      seg.dataset.color = 'orange';
    } else {
      seg.dataset.color = 'red';
    }
    meterContainer.appendChild(seg);
    ledSegments.push(seg);
  }
}
buildMeterSegments();

// Traffic-Light Latency Indicator (GREEN / YELLOW / RED)
function updateLatencyTrafficLight(connected, latencyMs) {
  if (!statusBadge || !statusText) return;
  if (!connected) {
    statusBadge.className = 'latency-pill red';
    statusText.textContent = 'RED';
    return;
  }
  if (latencyMs <= 10.0) {
    statusBadge.className = 'latency-pill green';
    statusText.textContent = 'GREEN';
  } else if (latencyMs <= 22.0) {
    statusBadge.className = 'latency-pill yellow';
    statusText.textContent = 'YELLOW';
  } else {
    statusBadge.className = 'latency-pill red';
    statusText.textContent = 'RED';
  }
}

// Real-Time Feedback Detection & AFC Algorithm Telemetry UI
function updateAfcMonitorUI(afc) {
  if (!afc || !afcStateBadge || !afcMetrics) return;
  if (!state.fx.afcOn || afc.afc_enabled === false) {
    afcStateBadge.className = 'afc-badge off';
    afcStateBadge.textContent = 'AFC: OFF';
  } else if (afc.active_notches > 0) {
    afcStateBadge.className = 'afc-badge locked';
    afcStateBadge.textContent = `NOTCH LOCKED (${afc.active_notches}/4)`;
  } else if (afc.candidate_streak > 0 || afc.papr > 25.0) {
    afcStateBadge.className = 'afc-badge tracking';
    afcStateBadge.textContent = 'HOWL TRACKING';
  } else {
    afcStateBadge.className = 'afc-badge clear';
    afcStateBadge.textContent = 'AFC: CLEAR';
  }

  const paprStr = Number(afc.papr || 1.0).toFixed(1);
  const pkStr = afc.peak_freq_hz > 0 ? `${Math.round(afc.peak_freq_hz)}Hz` : '--Hz';
  const isoStr = Number(afc.iso_gain_db || 0).toFixed(1);
  afcMetrics.textContent = `PAPR: ${paprStr}/42 | PK: ${pkStr} | ISO: ${isoStr}dB`;

  const notches = Array.isArray(afc.notch_freqs_hz) ? afc.notch_freqs_hz : [0, 0, 0, 0];
  for (let i = 0; i < 4; i += 1) {
    const pill = afcNotchEls[i];
    if (!pill) continue;
    const hz = Math.round(notches[i] || 0);
    if (hz > 0) {
      pill.className = 'notch-pill active';
      pill.textContent = `N${i + 1}: ${hz}Hz`;
    } else {
      pill.className = 'notch-pill';
      pill.textContent = `N${i + 1}: IDLE`;
    }
  }
}

// Send FX / Mixer command over WebSocket or HTTP fallback
function sendFxCommand(param, val) {
  if (state.socket && state.socket.readyState === WebSocket.OPEN) {
    state.socket.send(JSON.stringify({
      type: 'fx',
      param,
      val,
    }));
  } else {
    fetch(`/api/fx?param=${encodeURIComponent(param)}&val=${encodeURIComponent(val)}`).catch(() => {});
  }
}

// Keep Screen Awake
async function requestWakeLock() {
  if ('wakeLock' in navigator) {
    try {
      state.wakeLock = await navigator.wakeLock.request('screen');
    } catch (err) {
      // Ignore wakeLock errors on unsupported browsers
    }
  }
}

// WebSocket Connection
function connectWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws`;

  state.socket = new WebSocket(wsUrl);
  state.socket.binaryType = 'arraybuffer';

  state.socket.onopen = () => {
    state.wasReplaced = false;
    updateLatencyTrafficLight(true, 2.7);
    requestWakeLock();

    state.socket.send(JSON.stringify({
      type: 'device_info',
      device: `${navigator.userAgentData?.platform || navigator.platform} (${navigator.userAgent.includes('Mobile') ? 'Mobile' : 'Desktop'})`,
    }));

    if (state.pingInterval) clearInterval(state.pingInterval);
    state.pingInterval = setInterval(() => {
      if (state.socket && state.socket.readyState === WebSocket.OPEN) {
        state.lastPingSent = performance.now();
        state.socket.send(JSON.stringify({
          type: 'ping',
          time: Date.now(),
          rtt: state.lastRtt,
        }));
      }
    }, 1000);
  };

  state.socket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);

      if (data.type === 'pong') {
        const rtt = Math.round((performance.now() - state.lastPingSent) * 10) / 10;
        state.lastRtt = rtt;
        if (telPing) telPing.textContent = `${rtt} ms`;
        const effectiveLat = typeof data.latency_ms === 'number' && data.latency_ms > 0 ? data.latency_ms : rtt * 0.5;
        updateLatencyTrafficLight(true, effectiveLat);
        if (data.afc) updateAfcMonitorUI(data.afc);
      } else if (data.type === 'transport') {
        updateTransportUI(data);
      } else if (data.type === 'handshake') {
        if (data.transport) updateTransportUI(data.transport);
        updateLatencyTrafficLight(true, 2.7);
        if (state.isStreaming && state.audioContext) {
          state.socket.send(JSON.stringify({
            type: 'device_info',
            device: `${navigator.userAgentData?.platform || navigator.platform} (${navigator.userAgent.includes('Mobile') ? 'Mobile' : 'Desktop'})`,
            sample_rate: state.audioContext.sampleRate,
          }));
        } else if (data.auto_start && !state.isStreaming) {
          startMicrophone();
        }
      } else if (data.type === 'start_mic') {
        if (!state.isStreaming) {
          startMicrophone();
        }
      } else if (data.type === 'replaced') {
        state.wasReplaced = true;
        if (state.isStreaming) {
          stopMicrophone();
        }
      }
    } catch (e) {
      // Binary frame
    }
  };

  state.socket.onclose = () => {
    if (state.pingInterval) {
      clearInterval(state.pingInterval);
      state.pingInterval = null;
    }
    updateLatencyTrafficLight(false, 999);
    if (telPing) telPing.textContent = '-- ms';
    if (!state.wasReplaced) {
      setTimeout(connectWebSocket, 1200);
    }
  };
}

function updateTransportUI(trans) {
  if (trans.tempo && transportTempo) {
    transportTempo.textContent = `${Math.round(Number(trans.tempo))} BPM`;
  }
  if (trans.beat && transportBeat) {
    transportBeat.textContent = `${Number(trans.beat).toFixed(1)}`;
  }

  if (trans.is_recording) {
    state.isRecordingAbleton = true;
    if (transportBadge) transportBadge.textContent = 'RECORDING';
    if (btnRecord) btnRecord.classList.add('recording');
    if (recordText) recordText.textContent = 'REC ACTIVE';
  } else {
    state.isRecordingAbleton = false;
    if (transportBadge) transportBadge.textContent = trans.is_playing ? 'PLAYING' : 'STOPPED';
    if (btnRecord) btnRecord.classList.remove('recording');
    if (recordText) recordText.textContent = 'REC CLIP';
  }
}

// AudioWorklet & Media Capture
async function startMicrophone() {
  try {
    const audioConstraints = {
      channelCount: { ideal: 1 },
      sampleRate: { ideal: 48000 },
      sampleSize: { ideal: 16 },
      latency: { exact: 0.0, ideal: 0.0 },
      echoCancellation: !state.isStudioMode,
      noiseSuppression: !state.isStudioMode,
      autoGainControl: !state.isStudioMode,
      googEchoCancellation: !state.isStudioMode,
      googAutoGainControl: !state.isStudioMode,
      googNoiseSuppression: !state.isStudioMode,
      googHighpassFilter: !state.isStudioMode,
    };

    try {
      state.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: audioConstraints,
        video: false,
      });
    } catch (constraintErr) {
      delete audioConstraints.latency.exact;
      state.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: audioConstraints,
        video: false,
      });
    }

    state.audioContext = new (window.AudioContext || window.webkitAudioContext)({
      sampleRate: 48000,
      latencyHint: 0,
    });

    const actualRate = state.audioContext.sampleRate;
    if (telRate) telRate.textContent = `${actualRate.toLocaleString()} Hz`;

    if (state.socket && state.socket.readyState === WebSocket.OPEN) {
      state.socket.send(JSON.stringify({
        type: 'device_info',
        device: `${navigator.userAgentData?.platform || navigator.platform} (${navigator.userAgent.includes('Mobile') ? 'Mobile' : 'Desktop'})`,
        sample_rate: actualRate,
      }));
    }

    await state.audioContext.audioWorklet.addModule(`/audio-worklet.js?v=${Date.now()}`);

    const sourceNode = state.audioContext.createMediaStreamSource(state.mediaStream);
    state.workletNode = new AudioWorkletNode(state.audioContext, 'airmic-processor');

    state.workletNode.port.postMessage({
      type: 'config',
      chunkSize: state.chunkSize,
      gain: state.gainLinear,
    });

    state.workletNode.port.onmessage = (event) => {
      if (!state.isStreaming || state.isMuted) return;

      const blockPeak = event.data.peak || 0;
      const blockRms = event.data.rms || 0;
      if (blockPeak >= state.livePeak) {
        state.livePeak = blockPeak;
      } else {
        state.livePeak *= 0.90;
      }
      state.liveRms = blockRms > state.liveRms ? blockRms : state.liveRms * 0.92 + blockRms * 0.08;

      const pcmBuffer = event.data.buffer;
      if (state.socket && state.socket.readyState === WebSocket.OPEN) {
        const header = new Uint8Array(4);
        state.packetSeq = (state.packetSeq + 1) & 0xFFFF;
        header[0] = (state.packetSeq >> 8) & 0xFF;
        header[1] = state.packetSeq & 0xFF;
        header[2] = 1;
        header[3] = 0;

        const combined = new Uint8Array(4 + pcmBuffer.byteLength);
        combined.set(header, 0);
        combined.set(new Uint8Array(pcmBuffer), 4);

        state.socket.send(combined.buffer);
        state.packetsSent += 1;
        if (telPackets && (state.packetsSent & 15) === 0) {
          telPackets.textContent = state.packetsSent.toLocaleString();
        }
      }
    };

    sourceNode.connect(state.workletNode);

    state.isStreaming = true;
    btnStream.classList.add('active');
    streamText.textContent = 'MIC LIVE';
    updateLatencyTrafficLight(true, 2.7);

    startMeterLoop();
  } catch (err) {
    console.error('Error starting microphone:', err);
  }
}

function stopMicrophone() {
  state.isStreaming = false;
  btnStream.classList.remove('active');
  streamText.textContent = 'START MIC';

  if (state.workletNode) {
    state.workletNode.disconnect();
    state.workletNode = null;
  }
  if (state.mediaStream) {
    state.mediaStream.getTracks().forEach((track) => track.stop());
    state.mediaStream = null;
  }
  if (state.audioContext) {
    state.audioContext.close();
    state.audioContext = null;
  }

  ledSegments.forEach((seg) => {
    seg.className = 'meter-segment';
  });
  clipLed.classList.remove('active');
  readoutPeak.textContent = '-∞';
  readoutRms.textContent = '-∞';
}

function startMeterLoop() {
  function renderMeter() {
    if (!state.isStreaming) return;

    const peak = state.livePeak;
    const rms = state.liveRms;
    state.livePeak *= 0.94;

    const peakDb = peak > 1e-4 ? 20 * Math.log10(peak) : -96;
    const rmsDb = rms > 1e-4 ? 20 * Math.log10(rms) : -96;

    readoutPeak.textContent = peakDb > -96 ? `${peakDb.toFixed(1)}` : '-∞';
    readoutRms.textContent = rmsDb > -96 ? `${rmsDb.toFixed(1)}` : '-∞';

    if (peak >= 0.98) {
      clipLed.classList.add('active');
    } else {
      clipLed.classList.remove('active');
    }

    const clampedPeak = Math.max(-48, Math.min(0, peakDb));
    const normalized = (clampedPeak + 48) / 48;
    const activeSegments = Math.round(normalized * TOTAL_SEGMENTS);

    for (let i = 0; i < TOTAL_SEGMENTS; i += 1) {
      if (i < activeSegments) {
        ledSegments[i].className = `meter-segment lit ${ledSegments[i].dataset.color}`;
      } else {
        ledSegments[i].className = 'meter-segment';
      }
    }

    requestAnimationFrame(renderMeter);
  }

  requestAnimationFrame(renderMeter);
}

// Momentary Reggae Dub Pads
function bindMomentaryPad(elementId, fxParam, activeLabel, idleLabel) {
  const pad = document.getElementById(elementId);
  if (!pad) return;

  const activate = (e) => {
    e.preventDefault();
    pad.classList.add('held');
    pad.textContent = activeLabel;
    sendFxCommand(fxParam, 1);
  };

  const release = (e) => {
    e.preventDefault();
    if (!pad.classList.contains('held')) return;
    pad.classList.remove('held');
    pad.textContent = idleLabel;
    sendFxCommand(fxParam, 0);
  };

  pad.addEventListener('pointerdown', activate);
  pad.addEventListener('pointerup', release);
  pad.addEventListener('pointercancel', release);
  pad.addEventListener('pointerleave', release);
}

bindMomentaryPad('pad-dub-throw', 'dub_throw', '🔥 DUB THROWING!', 'HOLD: DUB THROW');
bindMomentaryPad('pad-spring-splash', 'spring_splash', '🌊 SPLASHING!', 'HOLD: SPRING SPLASH');
bindMomentaryPad('pad-dub-horn', 'dub_horn', '📯 HORN FILTER ON!', 'HOLD: DUB HORN EQ');

const padDryCut = document.getElementById('pad-dry-cut');
if (padDryCut) {
  padDryCut.addEventListener('click', () => {
    state.fx.dryCut = !state.fx.dryCut;
    padDryCut.classList.toggle('dry-active', state.fx.dryCut);
    padDryCut.textContent = state.fx.dryCut ? 'DRY VOCAL (TAP FX)' : 'FX ACTIVE (TAP DRY)';
    sendFxCommand('bypass_all', state.fx.dryCut ? 1 : 0);
  });
}

// Echo Rhythm Subdivision Selector
document.querySelectorAll('.rate-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    const rate = parseInt(btn.dataset.rate || '0', 10);
    state.fx.echoRate = rate;
    document.querySelectorAll('.rate-btn').forEach((b) => {
      b.classList.toggle('active', b === btn);
    });
    sendFxCommand('echo_rate', rate);
  });
});

// Compact Reggae Macro Sliders
function bindFxSlider(sliderId, valId, fxParam, extraParam = null) {
  const slider = document.getElementById(sliderId);
  const valSpan = document.getElementById(valId);
  if (!slider) return;
  slider.addEventListener('input', (e) => {
    const pct = parseInt(e.target.value, 10);
    if (valSpan) valSpan.textContent = `${pct}%`;
    sendFxCommand(fxParam, pct);
    if (extraParam) sendFxCommand(extraParam, pct);
  });
}

bindFxSlider('slider-echo-mix', 'val-echo-mix', 'echo_mix');
bindFxSlider('slider-echo-fb', 'val-echo-fb', 'echo_fb');
bindFxSlider('slider-dub-filter', 'val-dub-filter', 'dub_filter');
bindFxSlider('slider-spring-wet', 'val-spring-wet', 'spring_wet');
bindFxSlider('slider-tube-warm', 'val-tube-warm', 'tube_warm', 'reggae_tone');
bindFxSlider('slider-gate-thresh', 'val-gate-thresh', 'gate_thresh');

// Gain Slider
if (sliderGain) {
  sliderGain.addEventListener('input', (e) => {
    const dbVal = parseFloat(e.target.value);
    gainLabel.textContent = `${dbVal > 0 ? '+' : ''}${dbVal.toFixed(1)} dB`;
    state.gainLinear = Math.pow(10, dbVal / 20);

    if (state.workletNode) {
      state.workletNode.port.postMessage({
        type: 'config',
        gain: state.gainLinear,
      });
    }
  });
}

// Compact 6-Unit FX Toggle Strip
function bindFxToggle(btnId, stateKey, activeClass, fxParam) {
  const btn = document.getElementById(btnId);
  if (!btn) return;
  btn.addEventListener('click', () => {
    state.fx[stateKey] = !state.fx[stateKey];
    const isOn = state.fx[stateKey];
    btn.classList.toggle(activeClass, isOn);
    sendFxCommand(fxParam, isOn ? 1 : 0);
  });
}

bindFxToggle('tog-gate', 'gateOn', 'active-green', 'gate_on');
bindFxToggle('tog-tune', 'tuneOn', 'active-purple', 'pitch_on');
bindFxToggle('tog-echo', 'echoOn', 'active-blue', 'echo_on');
bindFxToggle('tog-spring', 'springOn', 'active-teal', 'spring_on');
bindFxToggle('tog-warm', 'warmOn', 'active-orange', 'warm_on');
bindFxToggle('tog-afc', 'afcOn', 'active-pink', 'afc_on');

// Bottom Action Buttons
if (btnStream) {
  btnStream.addEventListener('click', () => {
    if (state.isStreaming) {
      stopMicrophone();
    } else {
      startMicrophone();
    }
  });
}

if (btnMute) {
  btnMute.addEventListener('click', () => {
    state.isMuted = !state.isMuted;
    btnMute.classList.toggle('muted', state.isMuted);
    muteText.textContent = state.isMuted ? 'MUTED' : 'MUTE';
  });
}

if (btnRecord) {
  btnRecord.addEventListener('click', () => {
    const newState = !state.isRecordingAbleton;
    state.isRecordingAbleton = newState;
    btnRecord.classList.toggle('recording', newState);
    recordText.textContent = newState ? 'REC ACTIVE' : 'REC CLIP';
    if (state.socket && state.socket.readyState === WebSocket.OPEN) {
      state.socket.send(JSON.stringify({
        type: 'remote_rec',
        state: newState,
      }));
    } else {
      sendFxCommand('remote_rec', newState ? 1 : 0);
    }
  });
}

// Build Secondary Ableton Session Mixer View (#view-mixer)
function buildMixerTracks() {
  if (!mixerTracksContainer) return;
  mixerTracksContainer.innerHTML = '';
  state.tracks.forEach((tr, idx) => {
    const card = document.createElement('div');
    card.className = 'mixer-track-card';

    const nameEl = document.createElement('div');
    nameEl.className = 'mixer-track-name';
    nameEl.style.color = tr.color;
    nameEl.textContent = `${tr.name} (${tr.vol}%)`;

    const fader = document.createElement('input');
    fader.type = 'range';
    fader.min = '0';
    fader.max = '100';
    fader.value = String(tr.vol);
    fader.addEventListener('input', () => {
      tr.vol = parseInt(fader.value, 10);
      nameEl.textContent = `${tr.name} (${tr.vol}%)`;
      sendFxCommand(`tr_vol_${idx}`, tr.vol);
    });

    const btnGroup = document.createElement('div');
    btnGroup.className = 'mixer-track-btns';

    const btnMuteTrack = document.createElement('button');
    btnMuteTrack.type = 'button';
    btnMuteTrack.className = `mix-btn ${tr.mute ? 'mute-on' : ''}`;
    btnMuteTrack.textContent = 'M';
    btnMuteTrack.addEventListener('click', () => {
      tr.mute = !tr.mute;
      btnMuteTrack.classList.toggle('mute-on', tr.mute);
      sendFxCommand(`tr_mute_${idx}`, tr.mute ? 1 : 0);
    });

    const btnSoloTrack = document.createElement('button');
    btnSoloTrack.type = 'button';
    btnSoloTrack.className = `mix-btn ${tr.solo ? 'solo-on' : ''}`;
    btnSoloTrack.textContent = 'S';
    btnSoloTrack.addEventListener('click', () => {
      tr.solo = !tr.solo;
      btnSoloTrack.classList.toggle('solo-on', tr.solo);
      sendFxCommand(`tr_solo_${idx}`, tr.solo ? 1 : 0);
    });

    const btnArmTrack = document.createElement('button');
    btnArmTrack.type = 'button';
    btnArmTrack.className = `mix-btn ${tr.arm ? 'arm-on' : ''}`;
    btnArmTrack.textContent = 'R';
    btnArmTrack.addEventListener('click', () => {
      tr.arm = !tr.arm;
      btnArmTrack.classList.toggle('arm-on', tr.arm);
      sendFxCommand(`tr_arm_${idx}`, tr.arm ? 1 : 0);
    });

    btnGroup.appendChild(btnMuteTrack);
    btnGroup.appendChild(btnSoloTrack);
    btnGroup.appendChild(btnArmTrack);

    card.appendChild(nameEl);
    card.appendChild(fader);
    card.appendChild(btnGroup);
    mixerTracksContainer.appendChild(card);
  });
}
buildMixerTracks();

// Legacy buffer & DSP mode listeners preserved for backward compatibility
const bufferMap = [
  { size: 128, label: '128 samples (~2.7 ms)' },
  { size: 256, label: '256 samples (~5.3 ms)' },
  { size: 512, label: '512 samples (~10.6 ms)' },
];
if (sliderBuffer) {
  sliderBuffer.addEventListener('input', (e) => {
    const idx = parseInt(e.target.value, 10) - 1;
    const config = bufferMap[idx] || bufferMap[0];
    state.chunkSize = config.size;
    if (bufferLabel) bufferLabel.textContent = config.label;
    if (state.workletNode) {
      state.workletNode.port.postMessage({
        type: 'config',
        chunkSize: state.chunkSize,
      });
    }
  });
}

if (modeStudio) {
  modeStudio.addEventListener('click', () => {
    state.isStudioMode = true;
    if (dspModeLabel) dspModeLabel.textContent = 'RAW STUDIO';
  });
}

if (modeSpeech) {
  modeSpeech.addEventListener('click', () => {
    state.isStudioMode = false;
    if (dspModeLabel) dspModeLabel.textContent = 'SPEECH DSP';
  });
}

// Start WebSocket connection and poll /api/status fallback for USB Fast-Track telemetry
connectWebSocket();

setInterval(() => {
  fetch('/api/status')
    .then((r) => r.json())
    .then((status) => {
      if (status && status.afc) {
        updateAfcMonitorUI(status.afc);
      }
      if (status && status.connected_clients > 0 && !state.isStreaming) {
        updateLatencyTrafficLight(true, status.latency_ms || 2.7);
      }
    })
    .catch(() => {});
}, 1000);

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') {
    if (!state.socket || state.socket.readyState === WebSocket.CLOSED || state.socket.readyState === WebSocket.CLOSING) {
      state.wasReplaced = false;
      connectWebSocket();
    }
    if (state.audioContext && state.audioContext.state === 'suspended') {
      state.audioContext.resume();
    }
  }
});

window.addEventListener('online', () => {
  if (!state.socket || state.socket.readyState === WebSocket.CLOSED || state.socket.readyState === WebSocket.CLOSING) {
    state.wasReplaced = false;
    connectWebSocket();
  }
});
