import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import type { InterviewSession, InterviewTurn } from '../api/interviews';
import RandomSetupPage from './RandomSetupPage';
import InterviewRoomPage from './InterviewRoomPage';

const { createInterview, getInterview, submitAnswer, generateReport } = vi.hoisted(() => ({
  createInterview: vi.fn(), getInterview: vi.fn(), submitAnswer: vi.fn(), generateReport: vi.fn(),
}));
vi.mock('../api/interviews', () => ({ createInterview, getInterview, submitAnswer, generateReport }));

const config = {
  role: 'Backend engineer', experience: 'Mid-level', skills: ['Python', 'React'],
  difficulty: 'Balanced' as const, interview_type: 'Mixed' as const, duration: 30,
};
const first: InterviewTurn = {
  id: 'turn-1', turn_index: 0, question_text: 'How do you validate an approach?',
  answer_text: null, action_taken: null, topic: 'Python',
  generated_by_model: 'mock-primary', provisional: false, score: null,
};
const initial: InterviewSession = {
  session_id: 'session-1', status: 'in_progress', config, started_at: '2026-10-12T09:00:00Z',
  completed_at: null, time_remaining: 1800, current_topic: 'Python', turns_on_current_topic: 0,
  topic_coverage: { Python: 'in_progress', React: 'not_started' }, turns: [first],
  completion_reason: null, report_generation: null,
};
const second: InterviewTurn = {
  ...first, id: 'turn-2', turn_index: 1, question_text: 'Which tradeoffs did you consider?',
  action_taken: 'follow_up',
};
const progressed: InterviewSession = {
  ...initial, turns_on_current_topic: 1,
  turns: [{ ...first, answer_text: 'I tested assumptions.' }, second],
};
const completed: InterviewSession = {
  ...initial, status: 'completed', completed_at: '2026-10-12T09:29:00Z',
  time_remaining: 0, completion_reason: 'time_limit',
  report_generation: { method: 'POST', url: '/interviews/session-1/report' },
  turns: [{ ...first, answer_text: 'I tested assumptions.' }],
};

function Destination() {
  const location = useLocation();
  return <div>Opened {location.pathname}; {location.state?.session?.first_question}</div>;
}
function setup() {
  render(<MemoryRouter initialEntries={['/interview/new/random']}><Routes>
    <Route path="/interview/new/random" element={<RandomSetupPage/>}/>
    <Route path="/interview/:sessionId" element={<Destination/>}/>
  </Routes></MemoryRouter>);
}
function room() {
  render(<MemoryRouter initialEntries={['/interview/session-1']}><Routes>
    <Route path="/interview/:sessionId" element={<InterviewRoomPage/>}/>
  </Routes></MemoryRouter>);
}

beforeEach(() => {
  vi.resetAllMocks();
  getInterview.mockResolvedValue(initial);
  createInterview.mockResolvedValue({
    session_id: 'session-1', first_question: first.question_text, next_question: first.question_text,
    turn_id: 'turn-1', is_complete: false,
  });
  submitAnswer.mockResolvedValue({
    session_id: 'session-1', next_question: second.question_text, turn_id: second.id, is_complete: false,
  });
});

describe('Random setup', () => {
  it('submits normalized config and navigates with server session data', async () => {
    setup();
    fireEvent.change(screen.getByLabelText(/target role/i), { target: { value: ' Backend engineer ' } });
    fireEvent.change(screen.getByLabelText(/skills or topics/i), { target: { value: ' Python, React, ' } });
    fireEvent.click(screen.getByRole('button', { name: /start practice/i }));
    await waitFor(() => expect(createInterview).toHaveBeenCalledWith(config));
    expect(await screen.findByText(/Opened \/interview\/session-1/)).toHaveTextContent(first.question_text);
  });

  it('keeps the form and shows an error on failure', async () => {
    createInterview.mockRejectedValue(new Error('offline'));
    setup();
    fireEvent.click(screen.getByRole('button', { name: /start practice/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not start');
    expect(screen.getByRole('button', { name: /start practice/i })).toBeEnabled();
  });

  it('prevents duplicate creates while preparing', async () => {
    createInterview.mockReturnValue(new Promise(() => {}));
    setup();
    fireEvent.click(screen.getByRole('button', { name: /start practice/i }));
    const busy = screen.getByRole('button', { name: /preparing your interview/i });
    expect(busy).toBeDisabled();
    fireEvent.click(busy);
    expect(createInterview).toHaveBeenCalledTimes(1);
  });
});

describe('Text interview room', () => {
  it('restores the saved question through GET after a page reload', async () => {
    room();
    expect(await screen.findByRole('heading', { name: first.question_text })).toBeInTheDocument();
    expect(getInterview).toHaveBeenCalledWith('session-1');
    expect(screen.getByLabelText('Your answer')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Submit answer' })).toBeDisabled();
  });

  it('submits text for the current turn and shows the next question and history', async () => {
    getInterview.mockResolvedValueOnce(initial).mockResolvedValue(progressed);
    room();
    fireEvent.change(await screen.findByLabelText('Your answer'), { target: { value: ' I tested assumptions. ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Submit answer' }));
    expect(await screen.findByRole('heading', { name: second.question_text })).toBeInTheDocument();
    expect(submitAnswer).toHaveBeenCalledWith('session-1', 'I tested assumptions.', 'turn-1');
    expect(screen.getByLabelText('Your answer')).toHaveValue('');
    expect(screen.getByText('I tested assumptions.')).toBeInTheDocument();
  });

  it('prevents duplicate answers during scoring', async () => {
    submitAnswer.mockReturnValue(new Promise(() => {}));
    room();
    fireEvent.change(await screen.findByLabelText('Your answer'), { target: { value: 'An answer' } });
    fireEvent.click(screen.getByRole('button', { name: 'Submit answer' }));
    expect(screen.getByRole('button', { name: /reviewing your answer/i })).toBeDisabled();
    expect(screen.getByLabelText('Your answer')).toBeDisabled();
    expect(submitAnswer).toHaveBeenCalledTimes(1);
  });

  it('shows completion and generates a real report through the API adapter', async () => {
    getInterview.mockResolvedValueOnce(initial).mockResolvedValue(completed);
    submitAnswer.mockResolvedValue({ next_question: null, turn_id: null, is_complete: true });
    generateReport.mockResolvedValue({
      id: 'report-1', session_id: 'session-1', summary: 'A clear explanation.',
      overall_score: 3.25, improvement_suggestions: ['Discuss an alternative.'],
      generated_by_model: 'mock-fallback', provisional: true,
    });
    room();
    fireEvent.change(await screen.findByLabelText('Your answer'), { target: { value: 'I tested assumptions.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Submit answer' }));
    expect(await screen.findByRole('heading', { name: 'Interview complete' })).toBeInTheDocument();
    expect(screen.queryByLabelText('Your answer')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Generate report' }));
    expect(await screen.findByText('A clear explanation.')).toBeInTheDocument();
    expect(generateReport).toHaveBeenCalledWith('session-1');
    expect(screen.getByText(/3.25 \/ 5/)).toBeInTheDocument();
    expect(screen.getByText(/report is provisional/i)).toBeInTheDocument();
  });

  it('retains an unaccepted draft and permits retry after reloading', async () => {
    submitAnswer.mockRejectedValue(new Error('network'));
    room();
    fireEvent.change(await screen.findByLabelText('Your answer'), { target: { value: 'Keep this draft' } });
    fireEvent.click(screen.getByRole('button', { name: 'Submit answer' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not confirm');
    expect(screen.getByLabelText('Your answer')).toHaveValue('Keep this draft');
    expect(screen.getByRole('button', { name: 'Submit answer' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Reload interview' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Submit answer' })).toBeEnabled());
    expect(screen.getByLabelText('Your answer')).toHaveValue('Keep this draft');
  });

  it('recovers after a saved answer followed by a failed GET without resubmission', async () => {
    getInterview.mockResolvedValueOnce(initial).mockRejectedValueOnce(new Error('network')).mockResolvedValue(progressed);
    room();
    fireEvent.change(await screen.findByLabelText('Your answer'), { target: { value: 'I tested assumptions.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Submit answer' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Your answer was saved');
    fireEvent.click(screen.getByRole('button', { name: 'Reload interview' }));
    expect(await screen.findByRole('heading', { name: second.question_text })).toBeInTheDocument();
    expect(screen.getByLabelText('Your answer')).toHaveValue('');
    expect(submitAnswer).toHaveBeenCalledTimes(1);
  });

  it('shows load errors with a reload action', async () => {
    getInterview.mockRejectedValueOnce(new Error('offline')).mockResolvedValue(initial);
    room();
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load');
    fireEvent.click(screen.getByRole('button', { name: 'Reload interview' }));
    expect(await screen.findByRole('heading', { name: first.question_text })).toBeInTheDocument();
  });

  it('can resume a completed session directly', async () => {
    getInterview.mockResolvedValue(completed);
    room();
    expect(await screen.findByRole('heading', { name: 'Interview complete' })).toBeInTheDocument();
    expect(submitAnswer).not.toHaveBeenCalled();
  });
});
