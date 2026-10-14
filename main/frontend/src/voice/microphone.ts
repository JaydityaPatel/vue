export class Microphone {
  private context?: AudioContext;
  private stream?: MediaStream;
  private source?: MediaStreamAudioSourceNode;
  private analyser?: AnalyserNode;
  private worklet?: AudioWorkletNode;
  private sink?: GainNode;
  private frame = 0;
  private active = false;
  private disposed = false;

  async open(onPCM: (frame: ArrayBuffer) => void, onLevel: (level: number) => void) {
    this.context = new AudioContext();
    await this.context.resume();
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: {
      channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true,
    } });
    if (this.disposed) { this.dispose(); return; }
    this.stream.getAudioTracks().forEach(track => { track.enabled = false; });
    await this.context.audioWorklet.addModule(`${import.meta.env.BASE_URL}audio/pcm-worklet.js`);
    if (this.disposed) { this.dispose(); return; }
    this.source = this.context.createMediaStreamSource(this.stream);
    this.analyser = this.context.createAnalyser();
    this.analyser.fftSize = 256;
    this.worklet = new AudioWorkletNode(this.context, 'pcm-capture', { channelCount: 1, channelCountMode: 'explicit' });
    this.worklet.port.onmessage = event => { if (this.active && !this.disposed) onPCM(event.data); };
    this.sink = this.context.createGain();
    this.sink.gain.value = 0;
    this.source.connect(this.analyser).connect(this.worklet).connect(this.sink).connect(this.context.destination);
    const samples = new Float32Array(this.analyser.fftSize);
    const tick = () => {
      if (this.disposed) return;
      this.analyser!.getFloatTimeDomainData(samples);
      const rms = Math.sqrt(samples.reduce((sum, value) => sum + value * value, 0) / samples.length);
      onLevel(this.active ? Math.min(1, rms * 5) : 0);
      this.frame = requestAnimationFrame(tick);
    };
    this.frame = requestAnimationFrame(tick);
  }
  enable(enabled: boolean) {
    if (this.active === (enabled && !this.disposed)) return;
    this.active = enabled && !this.disposed;
    this.stream?.getAudioTracks().forEach(track => { track.enabled = this.active; });
    this.worklet?.port.postMessage({ enabled: this.active });
  }
  dispose() {
    this.disposed = true;
    this.active = false;
    cancelAnimationFrame(this.frame);
    this.stream?.getTracks().forEach(track => track.stop());
    this.source?.disconnect(); this.analyser?.disconnect(); this.worklet?.disconnect(); this.sink?.disconnect();
    if (this.worklet) this.worklet.port.onmessage = null;
    if (this.context && this.context.state !== 'closed') void this.context.close();
  }
}
