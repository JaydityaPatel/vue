import { beforeEach, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { VoiceConnection, type VoiceEvents } from './connection';
import { TOKEN_KEY } from '../api/client';
import type { InterviewSession } from '../api/interviews';
import InterviewRoomPage from '../pages/InterviewRoomPage';

const mic = vi.hoisted(() => ({ open: vi.fn(), enable: vi.fn(), dispose: vi.fn() }));
vi.mock('./microphone', () => ({ Microphone: vi.fn().mockImplementation(() => mic) }));
const apiCalls = vi.hoisted(() => ({ getInterview: vi.fn(), generateReport: vi.fn() }));
vi.mock('../api/interviews', () => apiCalls);
vi.mock('../components/Orb', () => ({ default: ({ orbState }: { orbState: string }) => <div data-testid="orb-state">{orbState}</div> }));

const snapshot: InterviewSession = {
  session_id: 's1', mode: 'random', status: 'in_progress', preparation_status: 'ready', started_at: '', completed_at: null,
  time_remaining: 1000, current_topic: 'Python', turns_on_current_topic: 0,
  topic_coverage: { Python: 'in_progress' }, completion_reason: null, report_generation: null,
  config: { role: 'Engineer', experience: 'Junior', skills: ['Python'], difficulty: 'Balanced', interview_type: 'Mixed', duration: 30 },
  turns: [{ id: 't1', turn_index: 0, question_text: 'Explain Python.', answer_text: null, action_taken: null,
    topic: 'Python', generated_by_model: 'mock', provisional: false, score: null }],
};
class FakeSocket {
  static OPEN = 1;
  static instances: FakeSocket[] = [];
  readyState = 1;
  bufferedAmount = 0;
  onopen?: () => void;
  onmessage?: (event: { data: string }) => void;
  onclose?: () => void;
  onerror?: () => void;
  send = vi.fn();
  close = vi.fn();
  constructor(public url: URL) { FakeSocket.instances.push(this); }
  receive(data: unknown) { this.onmessage?.({ data: JSON.stringify(data) }); }
}
class Utterance {
  lang = '';
  onstart?: () => void;
  onend?: () => void;
  onerror?: (error: unknown) => void;
  constructor(public text: string) {}
}
const speak = vi.fn();
function events(): VoiceEvents {
  return { session: vi.fn(), partial: vi.fn(), state: vi.fn(), level: vi.fn(), connected: vi.fn(), error: vi.fn() };
}
function question(socket: FakeSocket, id = 't1', text = 'Explain Python.') {
  socket.receive({ type: 'question_start', turn_id: id, text: '' });
  socket.receive({ type: 'question_chunk', turn_id: id, text });
  socket.receive({ type: 'question_end', turn_id: id, text: '' });
}
beforeEach(() => {
  vi.clearAllMocks(); FakeSocket.instances = [];
  mic.open.mockResolvedValue(undefined);
  vi.stubGlobal('WebSocket', FakeSocket);
  vi.stubGlobal('AudioWorkletNode', class {});
  vi.stubGlobal('SpeechSynthesisUtterance', Utterance);
  vi.stubGlobal('speechSynthesis', { speak, cancel: vi.fn() });
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia: vi.fn() } });
  localStorage.setItem(TOKEN_KEY, 'test-token');
  apiCalls.getInterview.mockResolvedValue(snapshot);
});

it('authenticates without a URL token and gates PCM until speech ends and server permits listening', async () => {
  const callbacks = events();
  const connection = new VoiceConnection('s1', callbacks);
  await connection.start();
  const socket = FakeSocket.instances[0]; socket.onopen!();
  expect(socket.url.search).toBe('');
  expect(JSON.parse(socket.send.mock.calls[0][0])).toEqual({ type: 'auth', token: 'test-token' });
  question(socket);
  const pcm = mic.open.mock.calls[0][0] as (data: ArrayBuffer) => void;
  pcm(new ArrayBuffer(1024));
  expect(socket.send).toHaveBeenCalledOnce();
  const utterance = speak.mock.calls[0][0] as Utterance;
  expect(callbacks.state).not.toHaveBeenCalledWith('speaking', false);
  utterance.onstart!();
  expect(callbacks.state).toHaveBeenLastCalledWith('speaking', false);
  utterance.onend!();
  expect(JSON.parse(socket.send.mock.calls[1][0])).toEqual({ type: 'playback_done', turn_id: 't1' });
  expect(mic.enable).not.toHaveBeenCalledWith(true);
  socket.receive({ type: 'state', state: 'listening', stt_active: false });
  expect(mic.enable).toHaveBeenLastCalledWith(true);
  pcm(new ArrayBuffer(1024));
  expect(socket.send.mock.calls[2][0]).toBeInstanceOf(ArrayBuffer);
  connection.mute(true);
  expect(mic.enable).toHaveBeenLastCalledWith(false);
  connection.dispose();
  expect(mic.dispose).toHaveBeenCalledOnce();
  expect(socket.close).toHaveBeenCalledOnce();
});

it('does not replay late questions after End and closes on malformed messages', async () => {
  const callbacks = events();
  const connection = new VoiceConnection('s1', callbacks);
  await connection.start(); const socket = FakeSocket.instances[0]; socket.onopen!();
  connection.end(); question(socket);
  expect(speak).not.toHaveBeenCalled();
  socket.receive({ type: 'state' });
  expect(callbacks.error).toHaveBeenCalled();
  expect(mic.dispose).toHaveBeenCalledOnce();
});

it('cleans up a permission request that resolves after leaving the room', async () => {
  let resolve!: () => void;
  mic.open.mockImplementationOnce(() => new Promise<void>(done => { resolve = done; }));
  const connection = new VoiceConnection('s1', events());
  const started = connection.start(); connection.dispose(); resolve(); await started;
  expect(FakeSocket.instances).toHaveLength(0);
  expect(mic.dispose).toHaveBeenCalledOnce();
});

it('integrates mocked WebSocket transcript, saved turns and real speech events with the room', async () => {
  const view = render(<MemoryRouter initialEntries={['/interview/s1']}><Routes>
    <Route path="/interview/:sessionId" element={<InterviewRoomPage/>}/>
  </Routes></MemoryRouter>);
  await screen.findByText('Explain Python.');
  fireEvent.click(screen.getByRole('button', { name: 'Start voice' }));
  await waitFor(() => expect(FakeSocket.instances).toHaveLength(1));
  const socket = FakeSocket.instances[0];
  act(() => { socket.onopen!(); question(socket); });
  act(() => { (speak.mock.calls[0][0] as Utterance).onstart!(); });
  expect(screen.getByTestId('orb-state')).toHaveTextContent('speaking');
  act(() => {
    (speak.mock.calls[0][0] as Utterance).onend!();
    socket.receive({ type: 'state', state: 'listening', stt_active: false });
    socket.receive({ type: 'transcript', turn_id: 't1', text: 'I test assumptions', final: false });
  });
  expect(screen.getByText('I test assumptions')).toBeInTheDocument();
  act(() => {
    socket.receive({ type: 'snapshot', session: { ...snapshot, turns: [
      { ...snapshot.turns[0], answer_text: 'I test assumptions.' },
      { ...snapshot.turns[0], id: 't2', turn_index: 1, question_text: 'Which tradeoffs?' },
    ] } });
    question(socket, 't2', 'Which tradeoffs?');
    (speak.mock.calls[1][0] as Utterance).onstart!();
  });
  expect(screen.getByText('I test assumptions.')).toBeInTheDocument();
  expect(screen.getByText('Which tradeoffs?')).toBeInTheDocument();
  expect(screen.getByTestId('orb-state')).toHaveTextContent('speaking');
  view.unmount();
  expect(mic.dispose).toHaveBeenCalledOnce();
});
