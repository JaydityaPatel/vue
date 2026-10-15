import { api, TOKEN_KEY } from '../api/client';
import type { InterviewSession } from '../api/interviews';
import type { OrbState } from '../components/Orb';
import { Microphone } from './microphone';
import { SpeechPlayback } from './playback';
import { parseMessage, type ClientMessage } from './protocol';

export interface VoiceEvents {
  session: (session: InterviewSession) => void;
  partial: (text: string) => void;
  state: (state: OrbState, stt: boolean) => void;
  level: (level: number) => void;
  connected: (connected: boolean) => void;
  error: (message: string) => void;
  introComplete?: () => void;
  codingReady?: () => void;
}
export class VoiceConnection {
  private mic = new Microphone();
  private socket?: WebSocket;
  private playback?: SpeechPlayback;
  private disposed = false;
  private muted = false;
  private speaking = false;
  private playbackPending = false;
  private listening = false;
  private finished = false;
  private ending = false;
  private turnId = '';
  private session?: InterviewSession;
  constructor(private id: string, private events: VoiceEvents, private channel: 'interview' | 'intro' = 'interview') {}
  async start() {
    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.AudioWorkletNode || !window.speechSynthesis) {
        throw new Error('Voice needs a browser with AudioWorklet and speech synthesis on HTTPS or localhost.');
      }
      const token = localStorage.getItem(TOKEN_KEY);
      if (!token) throw new Error('Please sign in again before starting voice.');
      await this.mic.open(pcm => {
        if (!this.listening || this.playbackPending || this.muted || this.disposed) return;
        if (this.socket?.readyState === WebSocket.OPEN) {
          if (this.socket.bufferedAmount > 16000 * 2 * 3) { this.fail('Audio connection is too slow. Reconnect to try again.'); return; }
          this.socket.send(pcm);
        }
      }, level => { if (!this.disposed) this.events.level(level); });
      if (this.disposed) return;
      const url = new URL(api.defaults.baseURL || 'http://localhost:8000', window.location.href);
      url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
      url.pathname = `${url.pathname.replace(/\/$/, '')}/ws/${this.channel}/${encodeURIComponent(this.id)}`;
      url.search = '';
      this.socket = new WebSocket(url);
      this.socket.onopen = () => { if (!this.disposed) { this.send({ type: 'auth', token }); this.events.connected(true); } };
      this.socket.onmessage = event => {
        if (this.disposed) return;
        try { this.receive(String(event.data)); }
        catch { this.fail('Invalid voice response. Reconnect to reload your saved interview.'); }
      };
      this.socket.onerror = () => this.fail('Voice connection failed. Check that the backend is running.');
      this.socket.onclose = () => {
        if (this.disposed) return;
        if (!this.finished) this.events.error('Voice disconnected. Reconnect to reload saved turns and replay the pending question.');
        this.dispose();
      };
    } catch (error) {
      if (!this.disposed) this.fail(error instanceof Error ? error.message : 'Could not start voice.');
    }
  }
  private send(message: ClientMessage) {
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify(message));
  }
  private receive(raw: string) {
    const message = parseMessage(raw);
    if (this.ending && message.type !== 'snapshot' && message.type !== 'error') return;
    switch (message.type) {
      case 'error': this.fail(message.message); break;
      case 'intro_complete': this.events.introComplete?.(); break;
      case 'snapshot':
        if (message.session.session_id !== this.id) throw new Error('Wrong session');
        this.session = message.session;
        this.finished = message.session.status !== 'in_progress';
        this.events.session(message.session); this.events.partial('');
        if (this.finished) { this.mic.enable(false); this.playback?.dispose(); this.events.state('idle', false); }
        break;
      case 'state':
        this.listening = message.state === 'listening';
        this.mic.enable(this.listening && !this.muted && !this.playbackPending);
        if (!this.speaking) this.events.state(message.state, message.stt_active);
        break;
      case 'transcript':
        if (message.turn_id === this.turnId) this.events.partial(message.text);
        break;
      case 'question_start':
        this.playback?.dispose();
        this.turnId = message.turn_id;
        this.playbackPending = true;
        this.listening = false;
        this.speaking = false;
        this.mic.enable(false);
        this.events.level(0);
        this.playback = new SpeechPlayback(() => {
          if (!this.disposed) { this.speaking = true; this.events.state('speaking', false); }
        }, () => {
          if (this.disposed) return;
          this.speaking = false;
          this.playbackPending = false;
          this.events.state('idle', false);
          this.send({ type: 'playback_done', turn_id: this.turnId });
          if (this.session?.current_topic_type === 'coding' && this.session.coding_status !== 'submitted') {
            this.events.codingReady?.();
          }
        }, error => this.fail(error));
        break;
      case 'question_chunk':
      case 'question_end':
        if (message.turn_id !== this.turnId || !this.playback) throw new Error('Out of order question');
        this.playback.push(message.text, message.type === 'question_end');
        break;
    }
  }
  mute(muted: boolean) {
    this.muted = muted;
    this.mic.enable(false);
    this.events.level(0);
    this.events.partial('');
    this.send({ type: 'mute', muted });
  }
  codingSubmitted() { this.send({ type: 'coding_submitted' }); }
  end() {
    this.ending = true;
    this.mic.enable(false);
    this.playback?.dispose();
    this.playbackPending = true;
    this.listening = false;
    this.events.state('idle', false);
    this.send({ type: 'end' });
  }
  private fail(message: string) {
    if (this.disposed) return;
    this.events.error(message);
    this.dispose();
  }
  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    this.mic.dispose(); this.playback?.dispose();
    if (this.socket) {
      this.socket.onopen = this.socket.onmessage = this.socket.onerror = this.socket.onclose = null;
      this.socket.close();
    }
    this.events.connected(false); this.events.state('idle', false); this.events.level(0);
  }
}
