// Capture only; inference and application state stay off the audio render thread.
class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.enabled = false;
    this.reset();
    this.port.onmessage = ({ data }) => { this.enabled = data.enabled; this.reset(); };
  }
  reset() {
    this.frame = new Int16Array(512);
    this.index = 0;
    this.weight = 0;
    this.sum = 0;
  }
  process(inputs) {
    const channels = inputs[0];
    if (!this.enabled || !channels?.length) return true;
    const ratio = sampleRate / 16000;
    for (let i = 0; i < channels[0].length; i++) {
      let sample = 0;
      for (const channel of channels) sample += channel[i] / channels.length;
      let remaining = 1;
      while (remaining > 1e-8) {
        const weight = Math.min(remaining, ratio - this.weight);
        this.sum += sample * weight;
        this.weight += weight;
        remaining -= weight;
        if (this.weight >= ratio - 1e-8) {
          const value = Math.max(-1, Math.min(1, this.sum / ratio));
          this.frame[this.index++] = Math.round(value * (value < 0 ? 32768 : 32767));
          this.weight = this.sum = 0;
          if (this.index === 512) {
            // Explicit little endian independent of host typed-array layout.
            const buffer = new ArrayBuffer(1024);
            const view = new DataView(buffer);
            for (let j = 0; j < 512; j++) view.setInt16(j * 2, this.frame[j], true);
            this.port.postMessage(buffer, [buffer]);
            this.index = 0;
          }
        }
      }
    }
    return true;
  }
}
registerProcessor('pcm-capture', PCMProcessor);
