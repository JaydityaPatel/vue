import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import {
  generateReport, getInterview, submitAnswer,
  type InterviewCreated, type InterviewReport, type InterviewSession,
} from '../api/interviews';
import { apiErrorMessage } from '../utils/errors';
import '../interview.css';

export default function InterviewRoomPage() {
  const { sessionId = '' } = useParams();
  const location = useLocation();
  const initial = (location.state as { session?: InterviewCreated } | null)?.session;
  const [session, setSession] = useState<InterviewSession | null>(null);
  const [answer, setAnswer] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [needsReload, setNeedsReload] = useState(false);
  const [error, setError] = useState('');
  const [report, setReport] = useState<InterviewReport | null>(null);
  const inFlight = useRef(false);
  const currentSessionId = useRef(sessionId);
  currentSessionId.current = sessionId;

  useEffect(() => {
    let active = true;
    setSession(null);
    setAnswer('');
    setReport(null);
    setError('');
    setBusy(false);
    setNeedsReload(false);
    setLoading(true);
    getInterview(sessionId).then(data => {
      if (active) setSession(data);
    }).catch(cause => {
      if (active) {
        setError(apiErrorMessage(cause, 'Could not load this interview.'));
        setNeedsReload(true);
      }
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [sessionId]);

  const complete = session?.status === 'completed';
  const pending = session?.turns.find(turn => turn.answer_text === null);
  const question = pending?.question_text || (loading && initial?.session_id === sessionId ? initial.first_question : null);

  async function reload() {
    if (inFlight.current) return;
    inFlight.current = true;
    setLoading(true);
    setError('');
    try {
      const data = await getInterview(sessionId);
      if (currentSessionId.current !== sessionId) return;
      const next = data.turns.find(turn => turn.answer_text === null);
      if (next?.id !== pending?.id) setAnswer('');
      setSession(data);
      setNeedsReload(false);
    } catch (cause) {
      if (currentSessionId.current === sessionId) setError(apiErrorMessage(cause, 'Could not reload this interview.'));
    } finally {
      inFlight.current = false;
      if (currentSessionId.current === sessionId) setLoading(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!pending || !answer.trim() || inFlight.current || needsReload) return;
    inFlight.current = true;
    setBusy(true);
    setError('');
    let saved = false;
    try {
      await submitAnswer(sessionId, answer.trim(), pending.id);
      saved = true;
      const data = await getInterview(sessionId);
      if (currentSessionId.current !== sessionId) return;
      setSession(data);
      setAnswer('');
    } catch (cause) {
      if (currentSessionId.current !== sessionId) return;
      setError(saved
        ? 'Your answer was saved. Reload the interview to see the next question.'
        : apiErrorMessage(cause, 'Could not confirm your answer. Reload the interview before trying again.'));
      // A lost response can follow a successful write. Reload before retrying
      // so the same answer can never be submitted to the next question.
      setNeedsReload(true);
    } finally {
      inFlight.current = false;
      if (currentSessionId.current === sessionId) setBusy(false);
    }
  }

  async function requestReport() {
    if (inFlight.current || !complete) return;
    inFlight.current = true;
    setBusy(true);
    setError('');
    try {
      const result = await generateReport(sessionId);
      if (currentSessionId.current === sessionId) setReport(result);
    } catch (cause) {
      if (currentSessionId.current === sessionId) setError(apiErrorMessage(cause, 'Could not generate the report. Please try again.'));
    } finally {
      inFlight.current = false;
      if (currentSessionId.current === sessionId) setBusy(false);
    }
  }

  return <main className="page-content room-page">
    <div className="room-top">
      <div><div className="eyebrow">YOUR PRACTICE ROOM</div><h1>{session?.config.role || 'Open practice'}</h1></div>
      {session && <div className="room-meta"><span>{complete ? 'COMPLETE' : 'IN PROGRESS'}</span><span>{session.config.duration} min</span></div>}
    </div>
    {error && <p role="alert" className="interview-error">{error}</p>}
    {needsReload && <button className="button button-outline" onClick={reload} disabled={loading}>Reload interview</button>}
    {loading && <p role="status">Loading interview...</p>}
    <section className="room-grid text-interview-grid">
      <div className="glass-card text-interview-panel">
        {complete ? <>
          <h2>Interview complete</h2>
          <p>{session.completion_reason === 'time_limit' ? 'Your practice time is up. Your last answer has been evaluated.' : 'You have finished the planned topics.'}</p>
          {!report && <button className="button button-primary" onClick={requestReport} disabled={busy}>{busy ? 'Preparing report...' : 'Generate report'}</button>}
          {report && <section aria-label="Interview report">
            <h3>Your report</h3><p>Overall score: {report.overall_score.toFixed(2)} / 5</p>
            <p>{report.summary}</p>
            {report.provisional && <p>This report is provisional because a fallback model contributed to its evaluation.</p>}
            <ul>{report.improvement_suggestions.map(suggestion => <li key={suggestion}>{suggestion}</li>)}</ul>
          </section>}
          <Link className="button button-outline" to="/interview/new/random">Start another interview</Link>
        </> : question ? <>
          <div className="eyebrow">{session?.current_topic || 'YOUR FIRST QUESTION'}</div>
          <h2 className="interview-question">{question}</h2>
          <form onSubmit={submit} aria-busy={busy}>
            <label className="field-label" htmlFor="answer">Your answer</label>
            <textarea className="text-input" id="answer" rows={8} maxLength={20000} value={answer}
              onChange={event => setAnswer(event.target.value)} disabled={busy || loading || needsReload}
              placeholder="Take your time and explain your thinking."/>
            <button className="button button-primary" type="submit" disabled={busy || loading || needsReload || !answer.trim()}>
              {busy ? 'Reviewing your answer...' : 'Submit answer'}
            </button>
          </form>
        </> : !loading && !error ? <p>No unanswered question is available.</p> : null}
      </div>
      <aside className="transcript-panel glass-card text-transcript">
        <div className="transcript-heading"><h2>Conversation</h2><span>{session?.turns.length || 0} questions</span></div>
        <ol className="interview-history">{session?.turns.map(turn => <li key={turn.id}>
          <h3>Question {turn.turn_index + 1} · {turn.topic}</h3>
          <p>{turn.question_text}</p>
          {turn.answer_text !== null && <><h4>Your answer</h4><p className="candidate-answer">{turn.answer_text}</p></>}
          {complete && turn.score && <p><strong>Feedback:</strong> {turn.score.feedback}</p>}
        </li>)}</ol>
      </aside>
    </section>
  </main>;
}
