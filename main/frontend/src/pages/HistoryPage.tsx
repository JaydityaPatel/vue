import { useEffect, useState } from 'react';
import { ArrowRight, Clock3, TrendingDown, TrendingUp, Minus } from 'lucide-react';
import { Link } from 'react-router-dom';
import { getInterviewHistory, getRecurringWeaknesses, type InterviewHistoryItem, type WeaknessItem } from '../api/interviews';
import { PageHeading } from '../components/AppShell';

function dateLabel(value: string) { return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)); }

export default function HistoryPage() {
  const [sessions, setSessions] = useState<InterviewHistoryItem[]>([]);
  const [weaknesses, setWeaknesses] = useState<WeaknessItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  useEffect(() => {
    Promise.all([getInterviewHistory(), getRecurringWeaknesses()])
      .then(([history, weak]) => { setSessions(history.items); setWeaknesses(weak); })
      .catch(() => setError('Could not load your practice history. Please try again.'))
      .finally(() => setLoading(false));
  }, []);
  return <main className="page-content history-page"><PageHeading eyebrow="YOUR JOURNEY SO FAR" title="Practice history" description="See how your interviews and skills are developing over time."/>
    {error && <p role="alert" className="interview-error">{error}</p>}{loading && <p role="status">Loading your history…</p>}
    {!loading && !error && <>
      <section className="section-block"><div className="eyebrow"><span/>RECURRING WEAKNESSES</div><h2>Skills to revisit</h2>
        {weaknesses.length === 0 ? <div className="empty-panel glass-card weakness-empty"><span className="empty-icon"><Clock3 size={19}/></span><h3>No recurring weaknesses yet.</h3><p>Complete interviews with the same skill tags to see patterns and improvement here.</p></div> : <div className="weakness-list">{weaknesses.map(item=>{const TrendIcon=item.trend==='improving'?TrendingUp:item.trend==='declining'?TrendingDown:Minus;return <article className="glass-card weakness-card" key={item.skill_tag}><div><h3>{item.skill_tag}</h3><p>{item.session_count} sessions · {item.occurrence_count} scored turns</p><p>Technical {item.average_scores.technical_correctness.toFixed(2)} · Completeness {item.average_scores.completeness.toFixed(2)}</p></div><span className={`weakness-trend trend-${item.trend}`}><TrendIcon size={16}/>{item.trend}</span></article>})}</div>}
      </section>
      <section className="section-block"><div className="eyebrow"><span/>PAST PRACTICE</div><h2>Your sessions</h2>
        {sessions.length===0 ? <section className="empty-panel glass-card history-empty"><span className="empty-icon"><Clock3 size={19}/></span><h2>Nothing to look back on just yet.</h2><p>Each practice is a small step forward. Your first one can start whenever you are.</p><Link className="button button-primary" to="/interview/new">Start a practice <ArrowRight size={16}/></Link></section> : <div className="history-list">{sessions.map(session=><Link className="glass-card history-item" to={session.status==='completed'?`/interview/${session.session_id}/report`:`/interview/${session.session_id}`} key={session.session_id}><span className="history-date">{dateLabel(session.started_at)}</span><span className="history-mode">{session.mode} interview</span><span className={`history-status status-${session.status}`}>{session.status.replace('_',' ')}</span><span className="history-score">{session.overall_score == null ? '—' : `${session.overall_score.toFixed(2)} / 5`}</span><ArrowRight size={16}/></Link>)}</div>}
      </section>
    </>}
  </main>;
}
