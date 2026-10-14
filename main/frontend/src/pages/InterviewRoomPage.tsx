import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { generateReport, getInterview, type InterviewReport, type InterviewSession } from '../api/interviews';
import Orb, { type OrbState } from '../components/Orb';
import TranscriptPanel from '../components/TranscriptPanel';
import { VoiceConnection } from '../voice/connection';
import { apiErrorMessage } from '../utils/errors';
import '../interview.css';


// A keyed child isolates microphone, socket, and in-flight work across routes.
export default function InterviewRoomPage() {
  const { sessionId = '' } = useParams();
  return <VoiceRoom key={sessionId} sessionId={sessionId} intro={false}/>;
}
export function IntroRoundPage() {
  const { sessionId = '' } = useParams();
  return <VoiceRoom key={`intro-${sessionId}`} sessionId={sessionId} intro/>;
}
function VoiceRoom({ sessionId, intro }: { sessionId: string; intro: boolean }) {
  const navigate = useNavigate();
  const [session, setSession] = useState<InterviewSession | null>(null);
  const [state, setState] = useState<OrbState>('idle');
  const [stt, setStt] = useState(false);
  const [level, setLevel] = useState(0);
  const [partial, setPartial] = useState('');
  const [connected, setConnected] = useState(false);
  const [starting, setStarting] = useState(false);
  const [muted, setMuted] = useState(false);
  const [ending, setEnding] = useState(false);
  const [error, setError] = useState('');
  const [report, setReport] = useState<InterviewReport | null>(null);
  const [reportBusy, setReportBusy] = useState(false);
  const connection = useRef<VoiceConnection>();
  const alive = useRef(false);
  const startingRef = useRef(false);
  const reportRef = useRef(false);
  const complete = session?.status === 'completed';
  const ended = session && session.status !== 'in_progress';
  useEffect(() => {
    alive.current = true;
    let active = true;
    getInterview(sessionId).then(value => { if (active) setSession(value); })
      .catch(cause => { if (active) setError(apiErrorMessage(cause, 'Could not load this interview.')); });
    return () => { active = false; alive.current = false; connection.current?.dispose(); };
  }, [sessionId]);

  async function start() {
    if (startingRef.current || connected) return;
    startingRef.current = true;
    setError(''); setStarting(true); setMuted(false); setEnding(false); setPartial('');
    connection.current?.dispose();
    const voice = new VoiceConnection(sessionId, {
      session: value => { if (alive.current) setSession(value); },
      state: (value, active) => { if (alive.current) { setState(value); setStt(active); } },
      level: value => { if (alive.current) setLevel(value); },
      partial: value => { if (alive.current) setPartial(value); },
      connected: value => { if (alive.current) { startingRef.current = false; setConnected(value); setStarting(false); setEnding(false); } },
      error: message => { if (alive.current) setError(message); },
      introComplete: () => { if (alive.current) navigate(`/interview/${sessionId}`, { replace: true }); },
    }, intro ? 'intro' : 'interview');
    connection.current = voice;
    await voice.start();
  }
  async function requestReport() {
    if (reportRef.current) return;
    reportRef.current = true; setReportBusy(true); setError('');
    try { const value = await generateReport(sessionId); if (alive.current) setReport(value); }
    catch (cause) { if (alive.current) setError(apiErrorMessage(cause, 'Could not generate the report. Please try again.')); }
    finally { reportRef.current = false; if (alive.current) setReportBusy(false); }
  }
  return <main className="page-content room-page voice-room">
    <header className="room-top"><div><div className="eyebrow">{intro ? 'QUICK INTRODUCTION' : 'YOUR PRACTICE ROOM'}</div>
      <h1>{session?.config.role || 'Open practice'}</h1></div><span>{session?.config.duration} min</span></header>
    {intro && <p className="voice-hint">A short warm-up before your tailored interview. Share a little about yourself; Vue is preparing the rest in the background.</p>}
    {intro && session?.preparation_status === 'preparing' && <p className="setup-note" role="status">Vue is preparing your tailored questions while you introduce yourself.</p>}
    {error && <p role="alert" className="interview-error">{error}</p>}
    {!session && error && <button className="button button-outline" onClick={async () => {
      setError('');
      try { const value = await getInterview(sessionId); if (alive.current) setSession(value); }
      catch { if (alive.current) setError('Could not load this interview.'); }
    }}>Reload interview</button>}
    {!session && !error && <p role="status">Loading interview...</p>}
    <section className="voice-grid">
      <div className="voice-stage"><Orb orbState={state} audioLevel={level} sttActive={stt}/>
        <p className="voice-state" role="status">{ended ? 'Interview ended' : starting ? 'Connecting…' : state}</p>
        <div className="voice-controls">
          {!connected && !ended && <button className="button button-primary" disabled={starting || !session} onClick={start}>{starting ? 'Connecting…' : 'Start voice'}</button>}
          {connected && !ended && <>
            <button className="button button-outline" aria-pressed={muted} disabled={ending} onClick={() => {
              const value = !muted; setMuted(value); connection.current?.mute(value);
            }}>{muted ? 'Unmute microphone' : 'Mute microphone'}</button>
            <button className="button button-outline" disabled={ending} onClick={() => {
              setEnding(true); connection.current?.end();
            }}>{ending ? 'Ending…' : 'End interview'}</button>
          </>}
        </div>
        {!connected && !ended && <p className="voice-hint">Allow microphone access to begin. Take your time; short pauses are welcome.</p>}
        {muted && !ended && <p className="voice-hint">Microphone muted. The unfinished utterance was discarded.</p>}
        {ended && <div className="voice-summary"><h2>{complete ? 'Interview complete' : 'Interview ended'}</h2>
          {complete && !report && <button className="button button-primary" disabled={reportBusy} onClick={requestReport}>{reportBusy ? 'Preparing report...' : 'Generate report'}</button>}
          {report && <section aria-label="Interview report"><h3>Your report</h3><p>Overall score: {report.overall_score.toFixed(2)} / 5</p><p>{report.summary}</p>
            {report.provisional && <p>This report is provisional because a fallback model contributed.</p>}
            <ul>{report.improvement_suggestions.map(item => <li key={item}>{item}</li>)}</ul></section>}
          <Link to="/interview/new/random">Start another interview</Link>
        </div>}
      </div>
      <TranscriptPanel turns={session?.turns || []} partial={partial}/>
    </section>
  </main>;
}
