import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SentenceBuffer } from './sentences';
import { parseMessage } from './protocol';
import { SpeechPlayback } from './playback';

describe('sentence chunks', () => {
  it('never speaks an unfinished word or sentence across token boundaries', () => {
    const buffer = new SentenceBuffer();
    expect(buffer.push('Tell me about your proj')).toEqual([]);
    expect(buffer.push('ect.')).toEqual([]);
    expect(buffer.push(' What did you learn? An')).toEqual(['Tell me about your project.', 'What did you learn?']);
    expect(buffer.push('y tradeoffs', true)).toEqual(['Any tradeoffs']);
  });
  it('keeps decimals, abbreviations, quotes and acronyms intact', () => {
    const buffer = new SentenceBuffer();
    const input = 'Dr. Smith used Python 3.12 in the U.S. office. "Why?" Tell me more.';
    const result: string[] = [];
    for (const character of input) result.push(...buffer.push(character));
    result.push(...buffer.push('', true));
    expect(result).toEqual(['Dr. Smith used Python 3.12 in the U.S. office.', '"Why?"', 'Tell me more.']);
  });
  it('flushes exactly once and ignores empty input', () => {
    const buffer = new SentenceBuffer();
    expect(buffer.push('  ', true)).toEqual([]);
    expect(buffer.push('No punctuation', true)).toEqual(['No punctuation']);
    expect(buffer.push('', true)).toEqual([]);
  });
});

describe('server protocol', () => {
  it.each([
    { type: 'state', state: 'thinking', stt_active: true },
    { type: 'transcript', text: 'Hello', turn_id: 't', final: false },
    { type: 'question_start', turn_id: 't', text: '' },
    { type: 'question_chunk', turn_id: 't', text: 'Question?' },
    { type: 'question_end', turn_id: 't', text: '' },
    { type: 'error', message: 'Try again' },
  ])('accepts valid $type', message => expect(parseMessage(JSON.stringify(message))).toEqual(message));
  it.each(['null', '{', '{}', '{"type":"state","state":"speaking"}', '{"type":"transcript","text":"hello"}'])('rejects malformed %s', raw => {
    expect(() => parseMessage(raw)).toThrow();
  });
});

class Utterance {
  lang = '';
  onstart?: () => void;
  onend?: () => void;
  onerror?: (event: { error: string }) => void;
  constructor(public text: string) {}
}
describe('speech playback', () => {
  const speak = vi.fn();
  const cancel = vi.fn();
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal('SpeechSynthesisUtterance', Utterance);
    vi.stubGlobal('speechSynthesis', { speak, cancel });
  });
  it('reports speaking only at actual start and listening only after the final end', () => {
    const start = vi.fn(), done = vi.fn(), error = vi.fn();
    const playback = new SpeechPlayback(start, done, error);
    playback.push('First sentence. Sec');
    expect(speak).toHaveBeenCalledOnce();
    expect(start).not.toHaveBeenCalled();
    const first = speak.mock.calls[0][0] as Utterance;
    first.onstart!();
    expect(start).toHaveBeenCalledOnce();
    playback.push('ond sentence.', true);
    expect(speak).toHaveBeenCalledOnce();
    first.onend!();
    expect(speak).toHaveBeenCalledTimes(2);
    expect(done).not.toHaveBeenCalled();
    (speak.mock.calls[1][0] as Utterance).onend!();
    expect(done).toHaveBeenCalledOnce();
    expect(error).not.toHaveBeenCalled();
  });
  it('cancels on disposal and never acknowledges failed speech', () => {
    const done = vi.fn(), error = vi.fn();
    const playback = new SpeechPlayback(vi.fn(), done, error);
    playback.push('Hello.', true);
    const utterance = speak.mock.calls[0][0] as Utterance;
    utterance.onerror!({ error: 'not-allowed' });
    expect(error).toHaveBeenCalledWith(expect.stringContaining('not-allowed'));
    playback.dispose();
    expect(cancel).toHaveBeenCalledOnce();
    expect(utterance.onend).toBeNull();
    expect(done).not.toHaveBeenCalled();
  });
});
