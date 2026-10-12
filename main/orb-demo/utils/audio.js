/** Device-local FFT analysis. No audio is recorded or sent anywhere. */
export class AudioInput {
  constructor() {
    this.context = null;
    this.stream = null;
    this.analyser = null;
    this.source = null;
    this.generation = 0;
    this.bands = { bass: 0, mid: 0, high: 0, level: 0 };
    this.onEnded = null;
    this.simulating = false;
    this.simulationTime = 0;
  }

  startSimulation() {
    this.simulating = true;
    this.simulationTime = 0;
  }

  async start() {
    const generation = ++this.generation;
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('Microphone access needs HTTPS or localhost and a supported browser.');
    }
    const Context = window.AudioContext || window.webkitAudioContext;
    if (!Context) throw new Error('This browser does not support Web Audio.');
    // Create/resume synchronously from the user gesture (including Safari).
    const context = new Context();
    this.context = context;
    try {
      await context.resume();
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
        video: false,
      });
      if (generation !== this.generation) {
        stream.getTracks().forEach(track => track.stop());
        return false;
      }
      this.stream = stream;
      this.source = context.createMediaStreamSource(stream);
      this.analyser = context.createAnalyser();
      this.analyser.fftSize = 2048;
      this.analyser.smoothingTimeConstant = 0.65;
      this.analyser.minDecibels = -85;
      this.analyser.maxDecibels = -20;
      this.source.connect(this.analyser);
      // Deliberately never connect to destination: no microphone feedback.
      this.frequency = new Uint8Array(this.analyser.frequencyBinCount);
      this.waveform = new Float32Array(this.analyser.fftSize);
      stream.getTracks().forEach(track => track.addEventListener('ended', () => this.onEnded?.(), { once: true }));
      return true;
    } catch (error) {
      await this.stop();
      throw error;
    }
  }

  sample(dt) {
    const target = { bass: 0, mid: 0, high: 0, level: 0 };
    if (this.simulating) {
      this.simulationTime += dt;
      const t = this.simulationTime;
      // Rhythmic bass hits, voice-like mid phrases, and quick high details.
      // These feed the same smoothing and shader inputs as microphone analysis.
      const beat = Math.exp(-((t * 1.8) % 1) * 7);
      const phrase = (.5 + .5 * Math.sin(t * 1.3)) ** 2;
      target.bass = .12 + .72 * beat;
      target.mid = .12 + .58 * phrase * (.7 + .3 * Math.sin(t * 7.1) ** 2);
      target.high = .08 + .42 * (.5 + .5 * Math.sin(t * 12.7)) ** 4;
      target.level = Math.min(1, .14 + target.bass * .4 + target.mid * .55);
    } else if (this.analyser) {
      this.analyser.getByteFrequencyData(this.frequency);
      this.analyser.getFloatTimeDomainData(this.waveform);
      const band = (low, high) => {
        const hzPerBin = this.context.sampleRate / this.analyser.fftSize;
        const first = Math.max(1, Math.ceil(low / hzPerBin));
        const last = Math.min(this.frequency.length - 1, Math.floor(high / hzPerBin));
        let sum = 0;
        for (let i = first; i <= last; i++) sum += (this.frequency[i] / 255) ** 2;
        return Math.sqrt(sum / Math.max(1, last - first + 1));
      };
      target.bass = band(30, 250);
      target.mid = band(250, 2500);
      target.high = band(2500, 12000);
      let square = 0;
      for (const value of this.waveform) square += value * value;
      const rms = Math.sqrt(square / this.waveform.length);
      target.level = Math.min(1, Math.max(0, rms - 0.003) * 5);
    }
    for (const key of Object.keys(target)) {
      const rate = target[key] > this.bands[key] ? 12 : 3.5;
      this.bands[key] += (target[key] - this.bands[key]) * (1 - Math.exp(-dt * rate));
    }
    return this.bands;
  }

  async stop() {
    this.generation++;
    this.simulating = false;
    this.stream?.getTracks().forEach(track => track.stop());
    this.source?.disconnect();
    this.analyser?.disconnect();
    const context = this.context;
    this.stream = this.source = this.analyser = this.context = null;
    if (context && context.state !== 'closed') await context.close();
  }
}
