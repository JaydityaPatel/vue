import { SentenceBuffer } from './sentences';

/** One utterance at a time avoids browser queue races and gates mic on actual end. */
export class SpeechPlayback {
  private buffer = new SentenceBuffer();
  private queue: string[] = [];
  private utterance?: SpeechSynthesisUtterance;
  private finished = false;
  private stopped = false;
  private acknowledged = false;
  constructor(private onStart: () => void, private onDone: () => void, private onError: (message: string) => void) {}
  push(text: string, final = false) {
    if (this.stopped) return;
    this.queue.push(...this.buffer.push(text, final));
    this.finished = final;
    this.pump();
  }
  private pump() {
    if (this.stopped || this.utterance) return;
    const text = this.queue.shift();
    if (!text) {
      if (this.finished && !this.acknowledged) { this.acknowledged = true; this.onDone(); }
      return;
    }
    const utterance = new SpeechSynthesisUtterance(text);
    this.utterance = utterance; // Keep a strong reference until onend.
    utterance.lang = 'en-US';
    utterance.onstart = () => { if (!this.stopped) this.onStart(); };
    utterance.onend = () => { if (!this.stopped) { this.utterance = undefined; this.pump(); } };
    utterance.onerror = event => { if (!this.stopped) this.onError(`Speech playback failed (${event.error}). Reconnect to replay the question.`); };
    window.speechSynthesis.speak(utterance);
  }
  dispose() {
    this.stopped = true;
    if (this.utterance) this.utterance.onstart = this.utterance.onend = this.utterance.onerror = null;
    this.queue = [];
    window.speechSynthesis?.cancel();
  }
}
