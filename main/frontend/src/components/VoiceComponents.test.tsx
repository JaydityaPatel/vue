import { expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import Orb, { orbAppearance, type OrbState } from './Orb';
import TranscriptPanel from './TranscriptPanel';
import type { InterviewTurn } from '../api/interviews';

const { canvas } = vi.hoisted(() => ({ canvas: vi.fn() }));
vi.mock('@react-three/fiber', () => ({ Canvas: (props: unknown) => { canvas(props); return <canvas data-testid="canvas"/>; } }));

it('mounts, reflects every state and amplitude, and unmounts', () => {
  const view = render(<Orb orbState="idle" audioLevel={0} size={320}/>);
  for (const state of ['idle', 'listening', 'thinking', 'speaking'] as OrbState[]) {
    view.rerender(<Orb orbState={state} audioLevel={.6} size={320} sttActive={state === 'thinking'}/>);
    const orb = screen.getByRole('img');
    expect(orb).toHaveAttribute('data-state', state);
    expect(orb).toHaveClass(`orb-${state}`);
    expect(orb).toHaveAttribute('data-audio-level', '0.6');
    expect(orb).toHaveStyle({ width: '320px' });
    expect(screen.getByTestId('canvas')).toBeInTheDocument();
  }
  expect(orbAppearance('thinking').speed).toBeGreaterThan(orbAppearance('listening').speed);
  view.rerender(<Orb orbState="thinking" audioLevel={99} sttActive/>);
  expect(screen.getByRole('img')).toHaveAttribute('data-audio-level', '1');
  expect(canvas.mock.calls[canvas.mock.calls.length - 1][0]).toMatchObject({ dpr: 1, frameloop: 'never' });
  view.unmount();
  expect(screen.queryByTestId('canvas')).not.toBeInTheDocument();
});

it('attributes saved and partial turns in order and scrolls to new text', () => {
  const scroll = vi.fn();
  Element.prototype.scrollIntoView = scroll;
  const first: InterviewTurn = { id: 't', turn_index: 0, question_text: 'Question one?', answer_text: 'Answer one.',
    action_taken: null, topic: 'Python', generated_by_model: 'test', provisional: false, score: null };
  const view = render(<TranscriptPanel turns={[first]} partial=""/>);
  expect(screen.getAllByRole('heading', { level: 3 }).map(node => node.textContent)).toEqual(['Vue', 'You']);
  view.rerender(<TranscriptPanel turns={[first, { ...first, id: 't2', question_text: 'Question two?', answer_text: null }]} partial="Thinking aloud"/>);
  const log = screen.getByRole('log');
  expect([...log.querySelectorAll('p')].map(node => node.textContent)).toEqual(['Question one?', 'Answer one.', 'Question two?', 'Thinking aloud']);
  expect(scroll).toHaveBeenCalledTimes(2);
});
