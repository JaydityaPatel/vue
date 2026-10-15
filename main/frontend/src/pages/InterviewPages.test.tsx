import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { Link, MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import type { InterviewSession, InterviewTurn } from '../api/interviews';
import RandomSetupPage from './RandomSetupPage';
import InterviewRoomPage from './InterviewRoomPage';
import { IntroRoundPage } from './InterviewRoomPage';
import UploadSetupPage from './UploadSetupPage';
import ReportPage from './ReportPage';
import type { VoiceEvents } from '../voice/connection';
const voice = vi.hoisted(() => ({ events: null as VoiceEvents | null, instances: [] as VoiceEvents[], start: vi.fn(), dispose: vi.fn(), mute: vi.fn(), end: vi.fn(), codingSubmitted: vi.fn() }));
vi.mock('../components/Orb', () => ({ default: ({ orbState, audioLevel }: { orbState: string; audioLevel: number }) => <div data-testid="orb" data-state={orbState} data-audio-level={audioLevel}/> }));
vi.mock('../voice/connection', () => ({ VoiceConnection: vi.fn().mockImplementation((_id, events) => {
  voice.events = events; voice.instances.push(events);
  return { start: voice.start, dispose: voice.dispose, mute: voice.mute, end: voice.end, codingSubmitted: voice.codingSubmitted };
}) }));
vi.mock('./CodingWorkspacePage', () => ({ CodingWorkspace: ({ onSubmitted }: { onSubmitted: () => void }) => <section aria-label="coding-workspace"><h2>Embedded coding workspace</h2><button onClick={onSubmitted}>Submit coding exercise</button></section> }));

const { createInterview, createDocumentInterview, getInterview, submitAnswer, generateReport } = vi.hoisted(() => ({
  createInterview: vi.fn(), createDocumentInterview: vi.fn(), getInterview: vi.fn(), submitAnswer: vi.fn(), generateReport: vi.fn(),
}));
vi.mock('../api/interviews', () => ({ createInterview, createDocumentInterview, getInterview, submitAnswer, generateReport }));

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
  session_id: 'session-1', mode: 'random', status: 'in_progress', preparation_status: 'ready', config, started_at: '2026-10-12T09:00:00Z',
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
function upload(mode: 'resume' | 'job' = 'resume') {
  render(<MemoryRouter initialEntries={[`/interview/new/${mode}`]}><Routes>
    <Route path="/interview/new/:mode" element={<UploadSetupPage/>}/>
    <Route path="/interview/:sessionId/intro" element={<Destination/>}/>
    <Route path="/interview/:sessionId" element={<Destination/>}/>
  </Routes></MemoryRouter>);
}
function room() {
  render(<MemoryRouter initialEntries={['/interview/session-1']}><Routes>
    <Route path="/interview/:sessionId" element={<InterviewRoomPage/>}/>
  </Routes></MemoryRouter>);
}

beforeEach(() => {
  vi.clearAllMocks();
  voice.instances = [];
  voice.start.mockImplementation(async () => { voice.events?.connected(true); });
  getInterview.mockReset();
  createInterview.mockReset();
  createDocumentInterview.mockReset();
  getInterview.mockResolvedValue(initial);
  createInterview.mockResolvedValue({
    session_id: 'session-1', first_question: first.question_text, next_question: first.question_text,
    turn_id: 'turn-1', is_complete: false,
  });
  createDocumentInterview.mockResolvedValue({
    session_id: 'document-session', first_question: 'A resume question?', next_question: 'A resume question?',
    turn_id: 'turn-doc', is_complete: false,
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

describe('Resume and job setup', () => {
  it('uploads a PDF resume, shows preparation, and navigates to the shared room', async () => {
    createDocumentInterview.mockReturnValue(new Promise(resolve => setTimeout(() => resolve({
      session_id: 'document-session', first_question: 'A resume question?', next_question: 'A resume question?',
      turn_id: 'turn-doc', is_complete: false,
    }), 30)));
    upload('resume');
    fireEvent.change(screen.getByLabelText(/your resume/i), { target: { files: [new File(['pdf bytes'], 'resume.pdf', { type: 'application/pdf' })] } });
    fireEvent.click(screen.getByRole('button', { name: /continue to practice/i }));
    expect(await screen.findByRole('status')).toHaveTextContent(/vue is preparing your interview/i);
    await waitFor(() => expect(createDocumentInterview).toHaveBeenCalledOnce());
    const data = createDocumentInterview.mock.calls[0][0] as FormData;
    expect(data.get('mode')).toBe('resume');
    expect((data.get('resume_file') as File).name).toBe('resume.pdf');
    expect(await screen.findByText(/Opened \/interview\/document-session\/intro/)).toHaveTextContent('A resume question?');
  });
  it('sends a job description and shows parsing errors without navigating', async () => {
    createDocumentInterview.mockRejectedValueOnce(Object.assign(new Error('Request failed'), {
      isAxiosError: true, response: { data: { detail: 'Scanned PDFs are not supported.' } },
    }));
    upload('job');
    fireEvent.change(screen.getByLabelText(/your resume/i), { target: { files: [new File(['pdf'], 'resume.pdf', { type: 'application/pdf' })] } });
    fireEvent.change(screen.getByLabelText(/paste the job description/i), { target: { value: 'Requires Kubernetes' } });
    fireEvent.click(screen.getByRole('button', { name: /continue to practice/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Scanned PDFs are not supported.');
    const data = createDocumentInterview.mock.calls[0][0] as FormData;
    expect(data.get('mode')).toBe('job');
    expect(data.get('jd_text')).toBe('Requires Kubernetes');
    expect(screen.getByRole('button', { name: /continue to practice/i })).toBeEnabled();
  });
  it('requires a resume and a job description before uploading', () => {
    upload('job');
    fireEvent.click(screen.getByRole('button', { name: /continue to practice/i }));
    expect(screen.getByRole('alert')).toHaveTextContent('Choose your resume PDF');
    expect(createDocumentInterview).not.toHaveBeenCalled();
  });

  it('labels the intro round and moves into the shared room when the server completes it', async () => {
    getInterview.mockResolvedValue({ ...initial, mode: 'resume', preparation_status: 'preparing', turns: [], topic_coverage: {} });
    render(<MemoryRouter initialEntries={['/interview/session-1/intro']}><Routes>
      <Route path="/interview/:sessionId/intro" element={<IntroRoundPage/>}/>
      <Route path="/interview/:sessionId" element={<div>main interview room</div>}/>
    </Routes></MemoryRouter>);
    expect(await screen.findByText(/quick introduction/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /start voice/i }));
    await waitFor(() => expect(voice.start).toHaveBeenCalled());
    act(() => voice.events?.introComplete?.());
    expect(await screen.findByText('main interview room')).toBeInTheDocument();
  });
});

describe('Voice interview room', () => {
  it('restores saved history and requests a gesture before microphone access', async () => {
    room();
    expect(await screen.findByText(first.question_text)).toBeInTheDocument();
    expect(getInterview).toHaveBeenCalledWith('session-1');
    expect(screen.queryByLabelText('Your answer')).not.toBeInTheDocument();
    expect(voice.start).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Start voice' }));
    await waitFor(() => expect(voice.start).toHaveBeenCalledTimes(1));
  });

  it('swaps to coding and back inside the same voice room and keeps its socket connection', async () => {
    room();
    await screen.findByText(first.question_text);
    fireEvent.click(screen.getByRole('button', { name: /start voice/i }));
    await waitFor(() => expect(voice.start).toHaveBeenCalled());
    act(() => voice.events?.session({ ...initial, current_topic: 'Coding Exercise', current_topic_type: 'coding', coding_status: 'in_progress' }));
    act(() => voice.events?.codingReady?.());
    expect(await screen.findByRole('region', { name: 'coding-workspace' })).toBeInTheDocument();
    expect(screen.queryByTestId('orb')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Submit coding exercise' }));
    expect(await screen.findByTestId('orb')).toBeInTheDocument();
    expect(voice.codingSubmitted).toHaveBeenCalledOnce();
    expect(voice.instances).toHaveLength(1);
  });
  it('updates transcript and speaking state from voice events', async () => {
    room();
    await screen.findByText(first.question_text);
    fireEvent.click(screen.getByRole('button', { name: 'Start voice' }));
    await waitFor(() => expect(voice.events).not.toBeNull());
    act(() => { voice.events!.partial('I test'); voice.events!.state('listening', false); voice.events!.level(.6); });
    expect(screen.getByText('I test')).toBeInTheDocument();
    expect(screen.getByTestId('orb')).toHaveAttribute('data-audio-level', '0.6');
    act(() => { voice.events!.session(progressed); voice.events!.partial(''); voice.events!.state('speaking', false); });
    expect(screen.getByText(second.question_text)).toBeInTheDocument();
    expect(screen.getByText('I tested assumptions.')).toBeInTheDocument();
    expect(screen.queryByText('I test')).not.toBeInTheDocument();
    expect(screen.getByTestId('orb')).toHaveAttribute('data-state', 'speaking');
    expect(submitAnswer).not.toHaveBeenCalled();
  });
  it('mutes and ends through the voice connection', async () => {
    room(); await screen.findByText(first.question_text);
    fireEvent.click(screen.getByRole('button', { name: 'Start voice' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Mute microphone' }));
    expect(voice.mute).toHaveBeenCalledWith(true);
    fireEvent.click(screen.getByRole('button', { name: 'Unmute microphone' }));
    expect(voice.mute).toHaveBeenLastCalledWith(false);
    fireEvent.click(screen.getByRole('button', { name: 'End interview' }));
    expect(voice.end).toHaveBeenCalledOnce();
    expect(screen.getByRole('button', { name: 'Ending…' })).toBeDisabled();
  });
  it('prevents duplicate starts while the socket is connecting', async () => {
    voice.start.mockResolvedValue(undefined);
    room(); await screen.findByText(first.question_text);
    fireEvent.click(screen.getByRole('button', { name: 'Start voice' }));
    expect(screen.getByRole('button', { name: 'Connecting…' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Connecting…' }));
    expect(voice.start).toHaveBeenCalledOnce();
  });
  it('generates a report for a restored completed session', async () => {
    getInterview.mockResolvedValue(completed);
    generateReport.mockResolvedValue({
      id: 'report-1', session_id: 'session-1', summary: 'A clear explanation.',
      overall_score: 3.25, improvement_suggestions: ['Discuss an alternative.'],
      generated_by_model: 'mock-fallback', provisional: true,
    });
    room();
    expect(await screen.findByRole('heading', { name: 'Interview complete' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Generate report' }));
    expect(await screen.findByText('A clear explanation.')).toBeInTheDocument();
    expect(generateReport).toHaveBeenCalledWith('session-1');
    expect(screen.getByText(/3.25 \/ 5/)).toBeInTheDocument();
    expect(screen.getByText(/report is provisional/i)).toBeInTheDocument();
  });
  it('recovers a failed initial load', async () => {
    getInterview.mockRejectedValueOnce(new Error('offline')).mockResolvedValue(initial);
    room();
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load');
    fireEvent.click(screen.getByRole('button', { name: 'Reload interview' }));
    expect(await screen.findByText(first.question_text)).toBeInTheDocument();
  });
  it('disposes the old connection and ignores its late events on route changes', async () => {
    const other = { ...initial, session_id: 'session-2', turns: [{ ...first, question_text: 'Second session question.' }] };
    getInterview.mockResolvedValueOnce(initial).mockResolvedValue(other);
    const view = render(<MemoryRouter initialEntries={['/interview/session-1']}>
      <Link to="/interview/session-2">Open second session</Link>
      <Routes><Route path="/interview/:sessionId" element={<InterviewRoomPage/>}/></Routes>
    </MemoryRouter>);
    await screen.findByText(first.question_text);
    fireEvent.click(screen.getByRole('button', { name: 'Start voice' }));
    const oldEvents = voice.events!;
    fireEvent.click(screen.getByRole('link', { name: 'Open second session' }));
    await screen.findByText('Second session question.');
    expect(voice.dispose).toHaveBeenCalled();
    act(() => { oldEvents.partial('Stale transcript'); oldEvents.session(progressed); oldEvents.state('speaking', false); });
    expect(screen.queryByText('Stale transcript')).not.toBeInTheDocument();
    expect(screen.queryByText(second.question_text)).not.toBeInTheDocument();
    expect(screen.getByTestId('orb')).toHaveAttribute('data-state', 'idle');
    view.unmount();
  });
});

describe('Coding report', () => {
  it('renders real dimension scores and turn-by-turn concepts', async () => {
    generateReport.mockResolvedValueOnce({ id: 'r-real', session_id: 'session-1', summary: 'Reasoning was sound.', overall_score: 4,
      improvement_suggestions: ['Add retry backoff on API reliability (turn t-1).'], generated_by_model: 'mock', provisional: false,
      dimension_breakdown: { technical_correctness: 4.2, completeness: 3.8, communication: 4.1, problem_solving: 3.9 },
      turns: [{ id: 't-1', turn_index: 0, question: 'How do you handle failures?', answer: 'I add retries.', topic: 'API reliability', topic_type: 'discussion',
        expected_concepts: ['backoff', 'jitter'], missing_concepts: ['jitter'], skill_tags: ['API reliability'],
        scores: { technical_correctness: 4, completeness: 3, communication: 4, problem_solving: 4 }, feedback: 'Explain backoff.', tests_passed: null, tests_total: null }],
    });
    render(<MemoryRouter initialEntries={['/interview/session-1/report']}><Routes>
      <Route path="/interview/:sessionId/report" element={<ReportPage/>}/><Route path="/interview/:sessionId" element={<div/>}/>
    </Routes></MemoryRouter>);
    expect(await screen.findByText('4.20 / 5')).toBeInTheDocument();
    expect(screen.getByText('How do you handle failures?')).toBeInTheDocument();
    expect(screen.getByText((_content, element) => element?.tagName === 'P' && element.textContent?.includes('To strengthen:') === true)).toHaveTextContent('jitter');
  });

  it('shows coding breakdown only when report includes coding turns', async () => {
    generateReport.mockResolvedValueOnce({ id: 'r1', session_id: 'session-1', summary: 'Good work.', overall_score: 3.7,
      improvement_suggestions: ['Discuss tradeoffs.'], generated_by_model: 'mock', provisional: false,
      coding_breakdown: { problems_solved: 1, problems_total: 2, tests_passed: 6, tests_total: 8, complexity_correct: 1, complexity_total: 2 } });
    const view = render(<MemoryRouter initialEntries={['/interview/session-1/report']}><Routes>
      <Route path="/interview/:sessionId/report" element={<ReportPage/>}/>
      <Route path="/interview/:sessionId" element={<div/>}/>
    </Routes></MemoryRouter>);
    expect(await screen.findByRole('region', { name: 'Coding round breakdown' })).toHaveTextContent('1/2 problems solved');
    view.unmount();

    generateReport.mockResolvedValueOnce({ id: 'r2', session_id: 'session-1', summary: 'Nice.', overall_score: 4,
      improvement_suggestions: ['Keep going.'], generated_by_model: 'mock', provisional: false, coding_breakdown: null });
    render(<MemoryRouter initialEntries={['/interview/session-1/report']}><Routes>
      <Route path="/interview/:sessionId/report" element={<ReportPage/>}/>
      <Route path="/interview/:sessionId" element={<div/>}/>
    </Routes></MemoryRouter>);
    await waitFor(() => expect(generateReport).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole('region', { name: 'Coding round breakdown' })).not.toBeInTheDocument();
  });
});
