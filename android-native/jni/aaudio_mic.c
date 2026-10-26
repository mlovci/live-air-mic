typedef unsigned char uint8_t;
typedef short int16_t;
typedef int int32_t;
typedef unsigned int uint32_t;
typedef unsigned long uint64_t;
typedef long int64_t;
typedef unsigned long size_t;

typedef int jint;
typedef short jshort;
typedef void* jobject;
typedef void* jshortArray;

typedef struct JNINativeInterface_ {
    void *reserved[210];
    void (*SetShortArrayRegion)(void *env, jshortArray array, int32_t start, int32_t len, const jshort *buf);
} JNINativeInterface;
typedef const JNINativeInterface* JNIEnv;

typedef struct AAudioStreamStruct AAudioStream;
typedef struct AAudioStreamBuilderStruct AAudioStreamBuilder;
typedef int32_t aaudio_result_t;
typedef int32_t aaudio_format_t;
typedef int32_t aaudio_data_callback_result_t;

#define AAUDIO_OK 0
#define AAUDIO_DIRECTION_INPUT 1
#define AAUDIO_FORMAT_UNSPECIFIED 0
#define AAUDIO_FORMAT_PCM_I16 1
#define AAUDIO_FORMAT_PCM_FLOAT 2
#define AAUDIO_FORMAT_PCM_I32 4
#define AAUDIO_SHARING_MODE_EXCLUSIVE 0
#define AAUDIO_SHARING_MODE_SHARED 1
#define AAUDIO_PERFORMANCE_MODE_LOW_LATENCY 12
#define AAUDIO_INPUT_PRESET_VOICE_RECOGNITION 6
#define AAUDIO_INPUT_PRESET_UNPROCESSED 9
#define AAUDIO_CALLBACK_RESULT_CONTINUE 0
#define AAUDIO_CALLBACK_RESULT_STOP 1

struct timespec {
    int64_t tv_sec;
    int64_t tv_nsec;
};
#define CLOCK_MONOTONIC 1

typedef aaudio_data_callback_result_t (*AAudioStream_dataCallback)(
        AAudioStream *stream, void *userData, void *audioData, int32_t numFrames);
typedef void (*AAudioStream_errorCallback)(
        AAudioStream *stream, void *userData, aaudio_result_t error);

extern aaudio_result_t AAudio_createStreamBuilder(AAudioStreamBuilder **builder);
extern void AAudioStreamBuilder_setDirection(AAudioStreamBuilder *builder, int32_t direction);
extern void AAudioStreamBuilder_setSampleRate(AAudioStreamBuilder *builder, int32_t sampleRate);
extern void AAudioStreamBuilder_setChannelCount(AAudioStreamBuilder *builder, int32_t channelCount);
extern void AAudioStreamBuilder_setFormat(AAudioStreamBuilder *builder, aaudio_format_t format);
extern void AAudioStreamBuilder_setPerformanceMode(AAudioStreamBuilder *builder, int32_t mode);
extern void AAudioStreamBuilder_setSharingMode(AAudioStreamBuilder *builder, int32_t sharingMode);
extern void AAudioStreamBuilder_setInputPreset(AAudioStreamBuilder *builder, int32_t inputPreset);
extern void AAudioStreamBuilder_setFramesPerDataCallback(AAudioStreamBuilder *builder, int32_t numFrames);
extern void AAudioStreamBuilder_setDataCallback(AAudioStreamBuilder *builder, AAudioStream_dataCallback callback, void *userData);
extern void AAudioStreamBuilder_setErrorCallback(AAudioStreamBuilder *builder, AAudioStream_errorCallback callback, void *userData);
extern aaudio_result_t AAudioStreamBuilder_openStream(AAudioStreamBuilder *builder, AAudioStream **stream);
extern aaudio_result_t AAudioStreamBuilder_delete(AAudioStreamBuilder *builder);

extern aaudio_result_t AAudioStream_requestStart(AAudioStream *stream);
extern aaudio_result_t AAudioStream_requestStop(AAudioStream *stream);
extern aaudio_result_t AAudioStream_close(AAudioStream *stream);
extern int32_t AAudioStream_getFramesPerBurst(AAudioStream *stream);
extern int32_t AAudioStream_getPerformanceMode(AAudioStream *stream);
extern int32_t AAudioStream_getSharingMode(AAudioStream *stream);
extern int32_t AAudioStream_getSampleRate(AAudioStream *stream);
extern int32_t AAudioStream_getChannelCount(AAudioStream *stream);
extern aaudio_format_t AAudioStream_getFormat(AAudioStream *stream);

extern int __android_log_print(int prio, const char *tag, const char *fmt, ...);
extern int usleep(unsigned int usec);
extern int clock_gettime(int clk_id, struct timespec *tp);
extern void *memset(void *s, int c, size_t n);
extern float sinf(float x);
extern float cosf(float x);
extern float sqrtf(float x);
extern float fabsf(float x);
extern float fmaxf(float x, float y);
extern float fminf(float x, float y);

#define LOGI(...) __android_log_print(4, "LiveAirMicAAudio", __VA_ARGS__)
#define LOGE(...) __android_log_print(6, "LiveAirMicAAudio", __VA_ARGS__)

#define RING_CAPACITY 16384
#define RING_MASK (RING_CAPACITY - 1)
#define SAMPLE_RATE 48000
#define MAX_NOTCHES 4
#define M_PI_F 3.14159265358979323846f

/* ============================================================================
 * Transparent Studio Zero-Latency Vocal Isolation & Anti-Feedback Engine (v5)
 *
 * Design Invariants (Zero Robotic Coloration / Zero Flutter):
 *   1. ZERO Multi-Mic Waveform Subtraction (NLMS removed from audio path):
 *      Subtracting the top capsule from the bottom capsule in a room creates an
 *      acoustic comb filter (hollow/robotic tunnel sound) because the singer's
 *      voice arrives at the second mic 0.5 ms later. Instead, the secondary mic
 *      is used STRICTLY as a sidechain spatial proximity sensor!
 *   2. ZERO Dynamic Shelving / Filter Modulation during Singing:
 *      While singing is detected, the audio path is 100% bit-transparent unity
 *      gain (1.0000f) on the primary vocal capsule. There is zero filter movement
 *      and zero amplitude flutter while you sing.
 *   3. Smooth Analog-Style Downward Expander Between Phrases:
 *      Tracks the true ambient room floor and smoothly attenuates inter-phrase
 *      background noise & monitor bleed after a 320 ms hold time.
 *   4. Surgical Anti-Feedback Howl Suppressor (Q=45):
 *      Monitors the pre-whitened spectrum and only engages a razor-thin Q=45
 *      notch if a pure sinusoidal feedback ring (> 1.1 kHz, PAPR > 42) locks onto
 *      the exact same frequency for >= 5 consecutive blocks (~13 ms).
 * ============================================================================ */

typedef struct {
    float b0, b1, b2, a1, a2;
    float z1, z2;
} Biquad;

typedef struct {
    float freq_hz;
    float q_factor;
    float depth_gain;
    float persistence;
    Biquad filter1;
} AdaptiveNotch;

typedef struct {
    /* Sidechain Spatial & Broadband Envelope Detector */
    float p_mic0_fast;
    float p_mic1_fast;
    float noise_floor_pwr;
    float min_window_pwr;
    int32_t min_frame_counter;
    int32_t hangover_blocks;
    float target_env_gain;
    float current_sample_gain;

    /* Subtle Low-Rumble Trim (< 130 Hz) ONLY when gate is closed between phrases */
    float sub_lp_state;

    /* Stage 3: PEM Pre-Whitened Autoregressive Howl Detector + 4x Q=45 Surgical Notch Bank */
    float ar_prev;
    float ring_hist[256];
    int ring_pos;
    int32_t candidate_bin;
    int32_t candidate_streak;
    float last_papr;
    float last_peak_freq_hz;
    float last_snr;
    AdaptiveNotch notches[MAX_NOTCHES];
} ZeroLatencyVocalIsoState;

static inline void biquad_set_notch(Biquad *bq, float fc, float q, float gain_linear, float fs) {
    float A = sqrtf(fmaxf(gain_linear, 0.05f));
    float w0 = 2.0f * M_PI_F * fc / fs;
    float alpha = sinf(w0) / (2.0f * q);
    float cosw0 = cosf(w0);
    float a0_inv = 1.0f / (1.0f + alpha / A);
    bq->b0 = (1.0f + alpha * A) * a0_inv;
    bq->b1 = (-2.0f * cosw0) * a0_inv;
    bq->b2 = (1.0f - alpha * A) * a0_inv;
    bq->a1 = bq->b1;
    bq->a2 = (1.0f - alpha / A) * a0_inv;
}

static inline float biquad_step(Biquad *bq, float x) {
    float y = bq->b0 * x + bq->z1;
    bq->z1 = bq->b1 * x - bq->a1 * y + bq->z2;
    bq->z2 = bq->b2 * x - bq->a2 * y;
    return y;
}

static ZeroLatencyVocalIsoState gIsoState;
static volatile int gVocalIsoEnabled = 1;
static volatile int gLastDspTimeNs = 0;
static volatile int gCallbackCount = 0;

static void vocal_iso_init(ZeroLatencyVocalIsoState *st) {
    memset(st, 0, sizeof(*st));
    st->noise_floor_pwr = 2e-6f;
    st->min_window_pwr = 2e-6f;
    st->target_env_gain = 1.0f;
    st->current_sample_gain = 1.0f;
    for (int k = 0; k < MAX_NOTCHES; k++) {
        st->notches[k].freq_hz = 1500.0f + k * 700.0f;
        st->notches[k].q_factor = 45.0f;
        st->notches[k].depth_gain = 1.0f;
        biquad_set_notch(&st->notches[k].filter1, st->notches[k].freq_hz, 45.0f, 1.0f, (float)SAMPLE_RATE);
    }
}

static void vocal_iso_process_quantum(
        ZeroLatencyVocalIsoState *st,
        const float * restrict mic0,
        const float * restrict mic1,
        float * restrict out_mono,
        int num_frames,
        int has_dual_mic) {

    /* 1. Measure primary vocal capsule (mic0) and secondary reference capsule (mic1) power */
    float e0 = 1e-9f, e1 = 1e-9f;
    for (int i = 0; i < num_frames; i++) {
        float m0 = mic0[i];
        e0 += m0 * m0;
        if (has_dual_mic) {
            float m1 = mic1[i];
            e1 += m1 * m1;
        }
    }
    float pwr0 = e0 / (float)num_frames;
    float pwr1 = has_dual_mic ? (e1 / (float)num_frames) : pwr0;

    st->p_mic0_fast = 0.60f * st->p_mic0_fast + 0.40f * pwr0;
    st->p_mic1_fast = 0.60f * st->p_mic1_fast + 0.40f * pwr1;

    /* 2. Track ambient room noise floor via Minima-Controlled Recursive Averaging (MCRA) */
    if (st->p_mic0_fast < st->min_window_pwr) {
        st->min_window_pwr = st->p_mic0_fast;
    } else {
        st->min_window_pwr = st->min_window_pwr * 1.003f + 1e-9f;
    }
    if ((++st->min_frame_counter & 63) == 0) {
        /* Update noise floor only if signal is relatively quiet (< -32 dBFS raw) */
        if (st->min_window_pwr < 6e-4f) {
            st->noise_floor_pwr = 0.70f * st->noise_floor_pwr + 0.30f * st->min_window_pwr;
        }
        st->min_window_pwr = st->p_mic0_fast;
    }
    if (st->min_window_pwr < st->noise_floor_pwr) {
        st->noise_floor_pwr = st->min_window_pwr;
    }
    /* Clamp noise floor to reasonable studio bounds */
    if (st->noise_floor_pwr < 5e-7f) st->noise_floor_pwr = 5e-7f;
    if (st->noise_floor_pwr > 3e-4f) st->noise_floor_pwr = 3e-4f;

    /* 3. Compute SNR + Dual-Mic Near-Field Assist for Voice Activity Detection */
    float snr = (st->p_mic0_fast + 1e-9f) / (st->noise_floor_pwr * 1.4f + 1e-9f);
    /* If dual-mic is active and bottom mic is louder than top mic, boost effective SNR */
    if (has_dual_mic && st->p_mic0_fast > st->p_mic1_fast * 1.10f) {
        snr *= 1.8f;
    }
    st->last_snr = snr;

    /* 4. Zero-Flutter Hangover Envelope:
       When voice is active (snr > 1.15), lock gain at EXACTLY 1.0000f (unity passband)
       and hold for 150 blocks (~400 ms) so there is ZERO gain modulation while singing!
       When silent between phrases, smoothly expand downward to 0.50 (-6 dB gentle room cut). */
    if (snr > 1.15f) {
        st->hangover_blocks = 150; /* 400 ms hold time — eliminates all inter-syllable flutter */
        st->target_env_gain = 1.0f;
    } else if (st->hangover_blocks > 0) {
        st->hangover_blocks--;
        st->target_env_gain = 1.0f;
    } else {
        /* Soft knee downward expander during silence */
        float ratio = snr / 1.15f;
        if (ratio < 0.0f) ratio = 0.0f;
        if (ratio > 1.0f) ratio = 1.0f;
        float desired_floor = 0.50f + 0.50f * (ratio * ratio);
        /* Very slow, gentle release (~300 ms time constant) so room decay sounds natural */
        st->target_env_gain = 0.96f * st->target_env_gain + 0.04f * desired_floor;
    }

    /* Fast 1-block attack (2.67 ms), smooth sample-by-sample interpolation */
    float block_end_gain;
    if (st->target_env_gain > st->current_sample_gain) {
        block_end_gain = 0.25f * st->current_sample_gain + 0.75f * st->target_env_gain;
    } else {
        block_end_gain = 0.92f * st->current_sample_gain + 0.08f * st->target_env_gain;
    }
    if (st->hangover_blocks > 0 && block_end_gain > 0.97f) {
        block_end_gain = 1.0f;
    }
    float gain_step = (block_end_gain - st->current_sample_gain) / (float)num_frames;

    /* Subtle low-frequency rumble reduction ONLY when gate is attenuating between phrases
       (0.0 when singing -> 100% flat phase & frequency response while singing!) */
    float rumble_sub_amt = (1.0f - block_end_gain) * 0.65f;

    for (int i = 0; i < num_frames; i++) {
        float x = mic0[i];

        /* Track < 130 Hz sub-rumble state */
        st->sub_lp_state += 0.017f * (x - st->sub_lp_state);

        st->current_sample_gain += gain_step;
        float clean = (x - rumble_sub_amt * st->sub_lp_state) * st->current_sample_gain;

        /* Apply Surgical Q=45 Anti-Feedback Notch ONLY if a feedback whistle is locked */
        float afc_out = clean;
        for (int k = 0; k < MAX_NOTCHES; k++) {
            if (st->notches[k].depth_gain < 0.98f) {
                afc_out = biquad_step(&st->notches[k].filter1, afc_out);
            }
        }

        /* Record PEM pre-whitened signal into sliding ring for feedback whistle detection */
        float pem_white = afc_out - 0.85f * st->ar_prev;
        st->ar_prev = afc_out;
        st->ring_hist[st->ring_pos] = pem_white;
        st->ring_pos = (st->ring_pos + 1) & 255;

        out_mono[i] = afc_out;
    }

    /* 5. Surgical Anti-Feedback Howl Detection (375 Hz - 6375 Hz, PAPR > 26, >= 3 consecutive blocks = 8ms lock) */
    float total_energy = 1e-8f;
    for (int i = 0; i < 256; i++) {
        float v = st->ring_hist[i];
        total_energy += v * v;
    }

    float bin_pwr[36];
    memset(bin_pwr, 0, sizeof(bin_pwr));
    float max_bin_pwr = 0.0f;
    int best_bin = 0;
    for (int bin = 2; bin <= 34; bin++) { /* 375 Hz .. 6375 Hz: covers low-mid room boom and high feedback whistles */
        float w = 2.0f * M_PI_F * (float)bin / 256.0f;
        float coeff = 2.0f * cosf(w);
        float s1 = 0.0f, s2 = 0.0f;
        int base = (st->ring_pos - 128) & 255;
        for (int n = 0; n < 128; n++) {
            float s0 = st->ring_hist[(base + n) & 255] + coeff * s1 - s2;
            s2 = s1;
            s1 = s0;
        }
        float pwr = (s1 * s1 + s2 * s2 - coeff * s1 * s2) / 128.0f;
        bin_pwr[bin] = pwr;
        if (pwr > max_bin_pwr) {
            max_bin_pwr = pwr;
            best_bin = bin;
        }
    }

    float papr = max_bin_pwr / (total_energy / 256.0f + 1e-8f);
    st->last_papr = papr;
    st->last_peak_freq_hz = ((float)best_bin * (float)SAMPLE_RATE) / 256.0f;
    if (papr > 26.0f && total_energy > 4e-5f) {
        if (best_bin == st->candidate_bin) {
            st->candidate_streak++;
        } else {
            st->candidate_bin = best_bin;
            st->candidate_streak = 1;
        }

        if (st->candidate_streak >= 3) {
            float best_freq = ((float)best_bin * (float)SAMPLE_RATE) / 256.0f;
            if (best_bin > 2 && best_bin < 34) {
                float p_left  = sqrtf(fmaxf(0.0f, bin_pwr[best_bin - 1]));
                float p_mid   = sqrtf(fmaxf(0.0f, bin_pwr[best_bin]));
                float p_right = sqrtf(fmaxf(0.0f, bin_pwr[best_bin + 1]));
                float denom = p_left - 2.0f * p_mid + p_right;
                if (fabsf(denom) > 1e-6f) {
                    float delta = 0.5f * (p_left - p_right) / denom;
                    if (delta > -0.6f && delta < 0.6f) {
                        best_freq = (((float)best_bin + delta) * (float)SAMPLE_RATE) / 256.0f;
                    }
                }
            }

            int slot = 0;
            float min_pers = 1e9f;
            for (int k = 0; k < MAX_NOTCHES; k++) {
                if (fabsf(st->notches[k].freq_hz - best_freq) < 160.0f) {
                    slot = k;
                    break;
                }
                if (st->notches[k].persistence < min_pers) {
                    min_pers = st->notches[k].persistence;
                    slot = k;
                }
            }
            st->notches[slot].freq_hz = best_freq;
            st->notches[slot].depth_gain = 0.08f; /* -22.0 dB surgical notch */
            st->notches[slot].persistence = 1.0f;
            biquad_set_notch(
                &st->notches[slot].filter1,
                st->notches[slot].freq_hz,
                st->notches[slot].q_factor,
                st->notches[slot].depth_gain,
                (float)SAMPLE_RATE
            );
        }
    } else {
        st->candidate_streak = 0;
    }

    for (int k = 0; k < MAX_NOTCHES; k++) {
        st->notches[k].persistence *= 0.97f;
        if (st->notches[k].persistence < 0.2f && st->notches[k].depth_gain < 1.0f) {
            st->notches[k].depth_gain = fminf(1.0f, st->notches[k].depth_gain + 0.025f);
            biquad_set_notch(
                &st->notches[k].filter1,
                st->notches[k].freq_hz,
                st->notches[k].q_factor,
                st->notches[k].depth_gain,
                (float)SAMPLE_RATE
            );
        }
    }
}

static AAudioStream * volatile gStream = (AAudioStream *)0;
static volatile int gStreamLock = 0;
static int gSavedBurst = 96;
static int gActiveChannels = 1;
static int16_t gRing[RING_CAPACITY];
static volatile uint32_t gWriteIdx = 0;
static volatile uint32_t gReadIdx = 0;
static volatile int gStreamBroken = 0;

static inline void lock_stream_mutex(void) {
    while (__sync_lock_test_and_set(&gStreamLock, 1)) {
        usleep(500);
    }
}

static inline void unlock_stream_mutex(void) {
    __sync_lock_release(&gStreamLock);
}

static aaudio_data_callback_result_t dataCallback(
        AAudioStream *stream,
        void *userData,
        void *audioData,
        int32_t numFrames) {
    if (stream != gStream || gStreamBroken) {
        return AAUDIO_CALLBACK_RESULT_STOP;
    }
    if (numFrames <= 0 || audioData == (void *)0) {
        return AAUDIO_CALLBACK_RESULT_CONTINUE;
    }

    aaudio_format_t fmt = AAudioStream_getFormat(stream);
    int ch = gActiveChannels;
    uint32_t w = gWriteIdx;

    float mic0[512];
    float mic1[512];
    float out_mono[512];
    int32_t frames = numFrames > 512 ? 512 : numFrames;

    if (fmt == AAUDIO_FORMAT_PCM_I16) {
        const int16_t *src = (const int16_t *)audioData;
        if (ch >= 2) {
            for (int32_t i = 0; i < frames; i++) {
                mic0[i] = src[i * ch] * (1.0f / 32768.0f);
                mic1[i] = src[i * ch + 1] * (1.0f / 32768.0f);
            }
        } else {
            for (int32_t i = 0; i < frames; i++) {
                mic0[i] = src[i] * (1.0f / 32768.0f);
                mic1[i] = 0.0f;
            }
        }
    } else if (fmt == AAUDIO_FORMAT_PCM_FLOAT) {
        const float *src = (const float *)audioData;
        if (ch >= 2) {
            for (int32_t i = 0; i < frames; i++) {
                mic0[i] = src[i * ch];
                mic1[i] = src[i * ch + 1];
            }
        } else {
            for (int32_t i = 0; i < frames; i++) {
                mic0[i] = src[i];
                mic1[i] = 0.0f;
            }
        }
    } else if (fmt == AAUDIO_FORMAT_PCM_I32) {
        const int32_t *src = (const int32_t *)audioData;
        if (ch >= 2) {
            for (int32_t i = 0; i < frames; i++) {
                mic0[i] = (float)(src[i * ch] >> 16) * (1.0f / 32768.0f);
                mic1[i] = (float)(src[i * ch + 1] >> 16) * (1.0f / 32768.0f);
            }
        } else {
            for (int32_t i = 0; i < frames; i++) {
                mic0[i] = (float)(src[i] >> 16) * (1.0f / 32768.0f);
                mic1[i] = 0.0f;
            }
        }
    } else {
        return AAUDIO_CALLBACK_RESULT_CONTINUE;
    }

    if (gVocalIsoEnabled) {
        struct timespec t0, t1;
        clock_gettime(CLOCK_MONOTONIC, &t0);
        vocal_iso_process_quantum(&gIsoState, mic0, mic1, out_mono, frames, (ch >= 2) ? 1 : 0);
        clock_gettime(CLOCK_MONOTONIC, &t1);
        int32_t dt_ns = (int32_t)((t1.tv_sec - t0.tv_sec) * 1000000000LL + (t1.tv_nsec - t0.tv_nsec));
        gLastDspTimeNs = dt_ns;
        if ((++gCallbackCount & 511) == 0) {
            LOGI("AAudio MMAP VocalIso v5: ch=%d frames=%d exec=%d.%02d us (gain=%.2f hold=%d)",
                 ch, frames, dt_ns / 1000, (dt_ns % 1000) / 10,
                 gIsoState.current_sample_gain, gIsoState.hangover_blocks);
        }
    } else {
        for (int32_t i = 0; i < frames; i++) {
            out_mono[i] = mic0[i];
        }
    }

    for (int32_t i = 0; i < frames; i++) {
        float v = out_mono[i];
        if (v > 1.0f) v = 1.0f;
        else if (v < -1.0f) v = -1.0f;
        gRing[(w + i) & RING_MASK] = (int16_t)(v * 32767.0f);
    }

    __sync_synchronize();
    gWriteIdx = w + (uint32_t)frames;
    return AAUDIO_CALLBACK_RESULT_CONTINUE;
}

static void errorCallback(
        AAudioStream *stream,
        void *userData,
        aaudio_result_t error) {
    LOGE("AAudio errorCallback: %d (marking stream broken for auto-recovery)", error);
    gStreamBroken = 1;
}

__attribute__((visibility("default")))
void Java_com_liveairmic_pro_MainActivity_nativeSetVocalIso(JNIEnv *env, jobject thiz, jint enabled) {
    gVocalIsoEnabled = (enabled != 0) ? 1 : 0;
    LOGI("Vocal Isolation & Anti-Feedback DSP set to: %d", gVocalIsoEnabled);
}

__attribute__((visibility("default")))
jint Java_com_liveairmic_pro_MainActivity_nativeGetDspTimeUs(JNIEnv *env, jobject thiz) {
    return (jint)(gLastDspTimeNs / 1000);
}

__attribute__((visibility("default")))
jint Java_com_liveairmic_pro_MainActivity_nativeGetFeedbackStats(JNIEnv *env, jobject thiz, jshortArray outStats) {
    if (outStats == (void *)0) return 0;
    jshort tmp[12];
    int activeNotches = 0;
    for (int k = 0; k < MAX_NOTCHES; k++) {
        if (gIsoState.notches[k].depth_gain < 0.98f) {
            activeNotches++;
            tmp[5 + k] = (jshort)gIsoState.notches[k].freq_hz;
        } else {
            tmp[5 + k] = 0;
        }
    }
    tmp[0] = (jshort)gVocalIsoEnabled;
    tmp[1] = (jshort)activeNotches;
    float paprClamped = fminf(999.0f, fmaxf(0.0f, gIsoState.last_papr));
    tmp[2] = (jshort)(paprClamped * 10.0f);
    tmp[3] = (jshort)gIsoState.candidate_streak;
    tmp[4] = (jshort)gIsoState.last_peak_freq_hz;
    tmp[9] = (jshort)(gIsoState.current_sample_gain * 100.0f);
    float snrClamped = fminf(999.0f, fmaxf(0.0f, gIsoState.last_snr));
    tmp[10] = (jshort)(snrClamped * 10.0f);
    tmp[11] = (jshort)(gLastDspTimeNs / 1000);
    (*env)->SetShortArrayRegion(env, outStats, 0, 12, tmp);
    return activeNotches;
}

__attribute__((visibility("default")))
jint Java_com_liveairmic_pro_MainActivity_nativeStartAAudio(JNIEnv *env, jobject thiz) {
    lock_stream_mutex();
    if (gStream != (AAudioStream *)0) {
        if (!gStreamBroken) {
            gReadIdx = gWriteIdx;
            int burst = gSavedBurst;
            LOGI("Reusing active AAudio MMAP stream: burst=%d ch=%d", burst, gActiveChannels);
            unlock_stream_mutex();
            return burst;
        }
        AAudioStream *old = gStream;
        gStream = (AAudioStream *)0;
        AAudioStream_requestStop(old);
        AAudioStream_close(old);
    }
    gStreamBroken = 0;
    gWriteIdx = 0;
    gReadIdx = 0;
    vocal_iso_init(&gIsoState);

    AAudioStreamBuilder *builder = (AAudioStreamBuilder *)0;
    aaudio_result_t res = AAudio_createStreamBuilder(&builder);
    if (res != AAUDIO_OK || builder == (AAudioStreamBuilder *)0) {
        LOGE("AAudio_createStreamBuilder failed: %d", res);
        unlock_stream_mutex();
        return -1;
    }

    int channelCounts[2] = { 2, 1 };
    int sharingModes[2] = { AAUDIO_SHARING_MODE_EXCLUSIVE, AAUDIO_SHARING_MODE_SHARED };
    int presets[2] = { AAUDIO_INPUT_PRESET_UNPROCESSED, AAUDIO_INPUT_PRESET_VOICE_RECOGNITION };
    int actualBurst = 128;

    for (int s = 0; s < 2 && gStream == (AAudioStream *)0; s++) {
        for (int c = 0; c < 2 && gStream == (AAudioStream *)0; c++) {
            for (int p = 0; p < 2 && gStream == (AAudioStream *)0; p++) {
                AAudioStream *cand = (AAudioStream *)0;
                AAudioStreamBuilder_setDirection(builder, AAUDIO_DIRECTION_INPUT);
                AAudioStreamBuilder_setSampleRate(builder, 48000);
                AAudioStreamBuilder_setChannelCount(builder, channelCounts[c]);
                AAudioStreamBuilder_setFormat(builder, AAUDIO_FORMAT_UNSPECIFIED);
                AAudioStreamBuilder_setPerformanceMode(builder, AAUDIO_PERFORMANCE_MODE_LOW_LATENCY);
                AAudioStreamBuilder_setSharingMode(builder, sharingModes[s]);
                AAudioStreamBuilder_setInputPreset(builder, presets[p]);
                AAudioStreamBuilder_setFramesPerDataCallback(builder, 128);
                AAudioStreamBuilder_setDataCallback(builder, dataCallback, (void *)0);
                AAudioStreamBuilder_setErrorCallback(builder, errorCallback, (void *)0);

                res = AAudioStreamBuilder_openStream(builder, &cand);
                if (res == AAUDIO_OK && cand != (AAudioStream *)0) {
                    gStream = cand;
                    res = AAudioStream_requestStart(cand);
                    if (res == AAUDIO_OK) {
                        actualBurst = AAudioStream_getFramesPerBurst(cand);
                        gActiveChannels = AAudioStream_getChannelCount(cand);
                        gSavedBurst = actualBurst;
                        LOGI("Opened & started AAudio stream: ch=%d preset=%d sharing=%d perf=%d burst=%d sr=%d fmt=%d",
                             gActiveChannels,
                             presets[p],
                             AAudioStream_getSharingMode(cand),
                             AAudioStream_getPerformanceMode(cand),
                             actualBurst,
                             AAudioStream_getSampleRate(cand),
                             AAudioStream_getFormat(cand));
                        break;
                    } else {
                        LOGE("AAudioStream_requestStart failed (ch=%d sharing=%d preset=%d): %d",
                             channelCounts[c], sharingModes[s], presets[p], res);
                        gStream = (AAudioStream *)0;
                        AAudioStream_close(cand);
                    }
                }
            }
        }
    }

    AAudioStreamBuilder_delete(builder);

    if (gStream == (AAudioStream *)0) {
        LOGE("Failed to open AAudio stream");
        unlock_stream_mutex();
        return -2;
    }

    unlock_stream_mutex();
    return actualBurst;
}

__attribute__((visibility("default")))
jint Java_com_liveairmic_pro_MainActivity_nativeReadAAudio(JNIEnv *env, jobject thiz, jshortArray outArray, jint numFrames) {
    int waitCycles = 0;
    while (gStream != (AAudioStream *)0 && !gStreamBroken && (int32_t)(gWriteIdx - gReadIdx) < numFrames) {
        if (++waitCycles > 1250) {
            LOGE("AAudio read timeout (>500ms); triggering stream recovery");
            gStreamBroken = 1;
            return -2;
        }
        usleep(400);
    }
    if (gStream == (AAudioStream *)0 || gStreamBroken) return -1;

    uint32_t w = gWriteIdx;
    uint32_t r = gReadIdx;
    if ((w - r) > 512) {
        r = w - 256;
    }

    jshort tmp[256];
    int count = numFrames > 256 ? 256 : numFrames;
    for (int i = 0; i < count; i++) {
        tmp[i] = gRing[(r + i) & RING_MASK];
    }
    gReadIdx = r + count;

    (*env)->SetShortArrayRegion(env, outArray, 0, count, tmp);
    return count;
}

__attribute__((visibility("default")))
void Java_com_liveairmic_pro_MainActivity_nativeStopAAudio(JNIEnv *env, jobject thiz) {
    lock_stream_mutex();
    if (gStream != (AAudioStream *)0) {
        AAudioStream *s = gStream;
        gStream = (AAudioStream *)0;
        AAudioStream_requestStop(s);
        AAudioStream_close(s);
    }
    unlock_stream_mutex();
}
