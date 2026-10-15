import type { InterviewSession } from '../api/interviews';
export type ServerMessage =
  | { type: 'snapshot'; session: InterviewSession }
  | { type: 'state'; state: 'idle' | 'listening' | 'thinking'; stt_active: boolean }
  | { type: 'transcript'; turn_id: string; text: string; final: boolean }
  | { type: 'question_start' | 'question_chunk' | 'question_end'; turn_id: string; text: string }
  | { type: 'intro_complete' }
  | { type: 'error'; message: string };
export type ClientMessage = { type: 'auth'; token: string } | { type: 'playback_done'; turn_id: string }
  | { type: 'mute'; muted: boolean } | { type: 'end' } | { type: 'coding_submitted' };

export function parseMessage(raw: string): ServerMessage {
  const m = JSON.parse(raw);
  if (!m || typeof m !== 'object') throw new Error('Invalid voice message');
  const text = (key: string) => typeof m[key] === 'string';
  const valid = m.type === 'snapshot' ? m.session && typeof m.session.session_id === 'string' && Array.isArray(m.session.turns)
    : m.type === 'state' ? ['idle', 'listening', 'thinking'].includes(m.state) && typeof m.stt_active === 'boolean'
    : m.type === 'transcript' ? text('turn_id') && text('text') && typeof m.final === 'boolean'
    : ['question_start', 'question_chunk', 'question_end'].includes(m.type) ? text('turn_id') && text('text')
    : m.type === 'intro_complete' ? true
    : m.type === 'error' && text('message');
  if (!valid) throw new Error('Invalid voice message');
  return m as ServerMessage;
}
