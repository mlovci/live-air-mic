/**
 * LiveAirMic AudioWorkletProcessor.
 * Runs on the dedicated high-priority WebAudio rendering thread.
 * Captures Float32 microphone samples, chunks them into configurable block sizes,
 * converts to 16-bit linear PCM, and transfers ArrayBuffers with zero copy to the main thread.
 */

class AirMicProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this.chunkSize = 128; // 128 samples @ 48kHz = 2.67ms (1 WebAudio render quantum)
        this.sampleBuffer = new Float32Array(this.chunkSize);
        this.bufferIndex = 0;
        this.gain = 1.0;

        this.port.onmessage = (event) => {
            const data = event.data;
            if (data.type === 'config') {
                if (data.chunkSize && data.chunkSize >= 64) {
                    this.chunkSize = data.chunkSize;
                    this.sampleBuffer = new Float32Array(this.chunkSize);
                    this.bufferIndex = 0;
                }
                if (typeof data.gain === 'number') {
                    this.gain = data.gain;
                }
            }
        };
    }

    process(inputs, outputs, parameters) {
        const input = inputs[0];
        if (!input || input.length === 0) {
            return true;
        }

        const channelData = input[0]; // Channel 0 (Mono)
        const inputLength = channelData.length;

        let blockPeak = 0;
        let blockSumSq = 0;

        for (let i = 0; i < inputLength; i++) {
            const gained = channelData[i] * this.gain;
            const absVal = Math.abs(gained);
            if (absVal > blockPeak) blockPeak = absVal;
            blockSumSq += gained * gained;

            this.sampleBuffer[this.bufferIndex++] = gained;

            if (this.bufferIndex >= this.chunkSize) {
                // Convert Float32 to Int16
                const int16Buffer = new Int16Array(this.chunkSize);
                for (let j = 0; j < this.chunkSize; j++) {
                    const sample = Math.max(-1.0, Math.min(1.0, this.sampleBuffer[j]));
                    int16Buffer[j] = sample < 0 ? sample * 0x8000 : sample * 0x7FFF;
                }

                // Transfer memory to worker/main thread with zero-copy + instantaneous peak/rms
                this.port.postMessage(
                    {
                        type: 'audio_chunk',
                        buffer: int16Buffer.buffer,
                        samples: this.chunkSize,
                        peak: blockPeak,
                        rms: Math.sqrt(blockSumSq / inputLength)
                    },
                    [int16Buffer.buffer]
                );

                this.bufferIndex = 0;
            }
        }

        return true;
    }
}

registerProcessor('airmic-processor', AirMicProcessor);
